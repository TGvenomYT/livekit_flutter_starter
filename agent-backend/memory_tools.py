"""Long-term memory tools for Jarvis (local, offline).

Deliberately just two tools so they don't reintroduce tool-spam: the model was
already tuned to answer from its own knowledge and only reach for a tool on an
explicit request.
"""

import asyncio

from livekit.agents import llm

import memory_store


class MemoryTools:
    @llm.function_tool(
        description=(
            "Save something to long-term memory so you remember it in future "
            "conversations. Use when the user says to remember something, or "
            "tells you a lasting fact, preference, name, or project detail. Pass "
            "the thing to remember as a short, self-contained sentence."
        )
    )
    async def remember(self, fact: str) -> str:
        await asyncio.to_thread(memory_store.add_fact, fact)
        return "Got it, I'll remember that."

    @llm.function_tool(
        description=(
            "Look something up in long-term memory. Use ONLY when the user asks "
            "what you remember, or refers to a past detail you don't already "
            "have in this conversation. Returns matching stored notes."
        )
    )
    async def recall(self, query: str) -> str:
        hits = await asyncio.to_thread(memory_store.search, query)
        if not hits:
            return "I don't have anything about that in memory."
        return "Here's what I remember: " + " | ".join(hits)
