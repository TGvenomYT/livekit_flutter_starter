import asyncio
import logging

import aiohttp
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai, silero
from dotenv import load_dotenv

import memory_store

load_dotenv()
logger = logging.getLogger("jarvis")

# ============================================================================
# LOCAL VOICE AI AGENT — Fully offline on Mac (M-series, 24 GB)
# ============================================================================
# LLM:  gemma4-agent:12b-mlx via Ollama   (localhost:11434)  — measured agentic
#       winner on this box; num_ctx 32768 baked in, thinking disabled for voice.
# STT:  faster-whisper (distil-small.en)  (localhost:8005)   — local_voice_server
# TTS:  Kokoro ONNX (streaming PCM)        (localhost:8005)   — local_voice_server
# Tools: OpenCode (non-blocking shell + file read/write), gated to explicit asks
# ============================================================================

OLLAMA_BASE = "http://localhost:11434"
LLM_MODEL = "gemma4-agent:12b-mlx"
VOICE_BASE = "http://localhost:8005/v1"

# The single source of truth for the agent's behaviour. Written to make the
# model CONVERSATIONAL-FIRST: it must answer from its own knowledge and only
# reach for a tool when the user explicitly asks it to act on the computer.
INSTRUCTIONS = """You are Jarvis, a fast, sharp, local voice assistant running privately on Niranjan's Mac.

HOW YOU THINK
- You are a highly capable generalist: reasoning, math, coding, writing, explanations, planning, general knowledge. Answer these DIRECTLY from your own knowledge. You almost never need a tool for them.
- Decide, then answer. Don't hedge, don't over-explain, don't list every option. Give the single best answer and move on.

WHEN TO USE TOOLS (rarely)
- Only use a tool when the user explicitly asks you to DO something on this computer: run a command, check the system, or read/write a specific file.
- If a question can be answered by thinking or from knowledge, answer it directly. Never call a tool "just in case."
- For a genuinely long-running command, start it in the background and say you'll report back — don't make the user wait in silence.

HOW YOU SPEAK (this is voice)
- Keep replies short and natural, the way a person talks. One or two sentences for most things.
- Plain spoken text only: no markdown, no bullet points, no code fences, no emojis. Say symbols and numbers as words when it reads more naturally.
- Never mention that you are an AI model, a voice bot, or a LiveKit agent. You're just Jarvis.

MEMORY AND HEARING THINGS RIGHT
- You have a long-term memory. Save lasting facts with the remember tool when the user asks you to remember something or tells you a durable detail. Look things up with the recall tool only when you need a past detail you don't already have.
- Speech-to-text is imperfect. If a word sounds like a garbled version of a name or project you know (for example you hear "NIH", "sigh", or "S I H" but the user means SIH), assume the known term and act on THAT — never go off and search for the misheard word. Use the glossary below to anchor what you hear.
"""


async def warmup_llm() -> None:
    """Load the model and pin it in memory so the first real turn is fast.

    Sends no num_ctx so Ollama uses the model's baked-in 32768; keep_alive keeps
    the prefix cache warm across idle gaps (default would evict after 5 min).
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "think": False,
                    "keep_alive": "24h",
                    "options": {"num_predict": 1},
                },
                timeout=aiohttp.ClientTimeout(total=180),
            ) as r:
                await r.read()
        logger.info("LLM warmed up and pinned (%s)", LLM_MODEL)
    except Exception as e:  # non-fatal: agent still works, first turn just slower
        logger.warning("LLM warmup failed (%s): %s", LLM_MODEL, e)


async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Warm the model while we finish wiring up the pipeline.
    warmup_task = asyncio.create_task(warmup_llm())

    # ── LLM: Ollama, gemma4-agent:12b-mlx ───────────────────────────────────
    #   reasoning_effort="none" → this is THE latency fix. gemma4 is a thinking
    #     model; left on, it burns ~900-1900 hidden reasoning tokens BEFORE
    #     every answer (measured), adding 10-40s per turn. Ollama's OpenAI
    #     endpoint ignores `think` but honours `reasoning_effort:"none"`, which
    #     drops a simple reply to ~20-80 tokens. Tool-gating is unaffected.
    #   temperature   → low-ish for steady decisions and clean tool-gating
    #   parallel_tool_calls=False → one action at a time, cleaner for voice
    ollama_llm = openai.LLM(
        base_url=f"{OLLAMA_BASE}/v1",
        api_key="ollama",
        model=LLM_MODEL,
        temperature=0.5,
        parallel_tool_calls=False,
        extra_body={"reasoning_effort": "none"},
    )

    # ── STT: local faster-whisper (distil-small.en) ─────────────────────────
    local_stt = openai.STT(
        model="whisper-1",
        language="en",
        api_key="not-needed",
        base_url=VOICE_BASE,
    )

    # ── TTS: local Kokoro (streaming PCM) ───────────────────────────────────
    local_tts = openai.TTS(
        model="tts-1",
        voice="af_heart",
        api_key="not-needed",
        base_url=VOICE_BASE,
        response_format="pcm",
    )

    # ── VAD: snappier endpointing than the 0.55 s default ───────────────────
    vad = silero.VAD.load(min_silence_duration=0.45)

    # ── Memory: materialise the local store + hotwords.txt, load the glossary ─
    memory_store.ensure_initialised()
    glossary = memory_store.glossary_text()
    instructions = (
        INSTRUCTIONS
        + "\n\nKNOWN PEOPLE, PROJECTS, AND TERMS (treat these as ground truth "
        "and use them to interpret unclear speech):\n"
        + glossary
    )

    # ── Tools (non-blocking, gated to explicit requests) ────────────────────
    from async_opencode import AsyncOpenCodeTools
    from memory_tools import MemoryTools
    tools_impl = AsyncOpenCodeTools()
    memory_impl = MemoryTools()

    agent = Agent(
        instructions=instructions,
        tools=llm.find_function_tools(tools_impl) + llm.find_function_tools(memory_impl),
    )

    # ── Session: this is where the latency knobs live in livekit 1.x ────────
    session = AgentSession(
        stt=local_stt,
        llm=ollama_llm,
        tts=local_tts,
        vad=vad,
        preemptive_generation=True,   # start generating before end-of-turn is confirmed
        min_endpointing_delay=0.4,    # respond quickly once the user pauses
        max_endpointing_delay=3.0,
        min_interruption_words=2,     # ignore stray one-word noise as an interruption
        max_tool_steps=3,
    )

    # Let tools trigger proactive speech (e.g. background task finished).
    tools_impl.session = session

    await warmup_task
    await session.start(agent=agent, room=ctx.room)

    await session.say("Jarvis online. What can I do for you?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
