import os
import urllib.request
import numpy as np
import soundfile as sf
import io
from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import Response, JSONResponse
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro
import uvicorn
import tempfile
import asyncio

app = FastAPI()

# Configuration
KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin"

KOKORO_MODEL_FILE = "kokoro-v1.0.onnx"
KOKORO_VOICES_FILE = "voices-v1.0.bin"

def download_if_not_exists(url, filename):
    if not os.path.exists(filename):
        print(f"Downloading {filename}...")
        urllib.request.urlretrieve(url, filename)
        print(f"Downloaded {filename}")

# Download models
download_if_not_exists(KOKORO_MODEL_URL, KOKORO_MODEL_FILE)
download_if_not_exists(KOKORO_VOICES_URL, KOKORO_VOICES_FILE)

# Initialize models
print("Initializing STT (Whisper)...")
# Using a much smaller, faster distilled model to drastically reduce STT latency on CPU
whisper_model = WhisperModel("distil-small.en", device="cpu", compute_type="int8")

print("Initializing TTS (Kokoro)...")
kokoro_model = Kokoro(KOKORO_MODEL_FILE, KOKORO_VOICES_FILE)

# ── STT vocabulary biasing ──────────────────────────────────────────────────
# The agent writes the user's known proper nouns (SIH, SafeSphere, myserver, …)
# to hotwords.txt via memory_store. We feed them to Whisper as decoding hints so
# domain words are transcribed correctly instead of being heard as look-alikes
# (this is what stops "SIH" turning into "NIH"). Re-read on change (cheap).
HOTWORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotwords.txt")
_hotwords_cache = {"mtime": 0.0, "value": None}


def get_hotwords():
    try:
        mtime = os.path.getmtime(HOTWORDS_FILE)
        if mtime != _hotwords_cache["mtime"]:
            with open(HOTWORDS_FILE, "r") as f:
                text = f.read().strip()
            _hotwords_cache["value"] = text or None
            _hotwords_cache["mtime"] = mtime
    except OSError:
        return None
    return _hotwords_cache["value"]

@app.post("/v1/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    language: str = Form("en"),
):
    content = await file.read()

    hotwords = get_hotwords()

    def _transcribe() -> str:
        # Low-latency settings for real-time voice:
        #   beam_size=1                -> greedy decode, ~3-5x faster than beam 5
        #   language="en"              -> skip language auto-detection
        #   vad_filter                 -> drop leading/trailing silence
        #   condition_on_previous_text -> stops cross-utterance hallucination loops
        #   hotwords                   -> bias decoding toward the user's vocab
        #   BytesIO input              -> no temp-file disk round-trip per utterance
        segments, _ = whisper_model.transcribe(
            io.BytesIO(content),
            beam_size=1,
            language=language or "en",
            vad_filter=True,
            condition_on_previous_text=False,
            without_timestamps=True,
            hotwords=hotwords,
        )
        return " ".join(seg.text for seg in segments).strip()

    text = await asyncio.to_thread(_transcribe)
    return JSONResponse(content={"text": text})


from pydantic import BaseModel
from fastapi.responses import Response, JSONResponse, StreamingResponse

class SpeechRequest(BaseModel):
    model: str
    input: str
    voice: str = "af_heart"
    response_format: str = "wav"

@app.post("/v1/audio/speech")
async def create_speech(request: SpeechRequest):
    voice = request.voice
    if not voice.startswith("af_") and not voice.startswith("am_"):
        voice = "af_heart" # fallback
        
    print(f"TTS Request: {request.input} with voice {voice}, format {request.response_format}")
    
    if request.response_format == "pcm":
        async def pcm_stream():
            try:
                async for audio_data, _ in kokoro_model.create_stream(
                    text=request.input,
                    voice=voice,
                    speed=1.0,
                    lang="en-us"
                ):
                    pcm_bytes = (audio_data * 32767).astype(np.int16).tobytes()
                    yield pcm_bytes
            except Exception as e:
                print(f"Streaming error: {e}")

        return StreamingResponse(pcm_stream(), media_type="audio/pcm")
    else:
        audio_data, sample_rate = kokoro_model.create(
            text=request.input,
            voice=voice,
            speed=1.0,
            lang="en-us"
        )
        
        # Save to memory buffer
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sample_rate, format='wav')
        buffer.seek(0)
        
        return Response(content=buffer.read(), media_type="audio/wav")

if __name__ == "__main__":
    print("Starting Local Native Voice Server on port 8005...")
    uvicorn.run(app, host="127.0.0.1", port=8005)
