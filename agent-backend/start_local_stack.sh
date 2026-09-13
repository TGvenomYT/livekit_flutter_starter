#!/bin/bash
# ============================================================================
# start_local_stack.sh — Launches all local services for the Jarvis agent
# ============================================================================
# Services:
#   1. LiveKit Server         (ws://localhost:7880)
#   2. Kokoro-FastAPI (TTS)   (http://localhost:8880)
#   3. Faster-Whisper-Server  (http://localhost:8000)
#   4. Ollama                 (http://localhost:11434) — assumed already running
#   5. Python Agent Backend
# ============================================================================

set -e

echo "=========================================="
echo "  Jarvis Local Agent Stack Launcher"
echo "=========================================="

# ── 1. LiveKit Server ──────────────────────────────────────────────────────
echo ""
echo "[1/4] Starting LiveKit Server (dev mode)..."
livekit-server --dev --bind 0.0.0.0 --node-ip 192.168.1.25 &
LIVEKIT_PID=$!
echo "  → LiveKit Server PID: $LIVEKIT_PID (ws://192.168.1.25:7880)"
sleep 2

# ── 2. Local Voice Server (TTS + STT) ──────────────────────────────────────
echo ""
echo "[2/4] Starting Native Python Voice Server (TTS on 8005)..."
source venv/bin/activate
python local_voice_server.py &
VOICE_PID=$!
echo "  → Voice Server PID: $VOICE_PID"

# ── 3. Check Ollama ───────────────────────────────────────────────────────
echo ""
echo "[3/4] Checking Ollama..."
# Keep the model resident so the prefix cache stays warm between turns
# (Ollama evicts after 5 min by default, which reintroduces cold-start latency).
export OLLAMA_KEEP_ALIVE=24h
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  ✅ Ollama is running on localhost:11434 (model: gemma4-agent:12b-mlx)"
else
    echo "  ⚠ Ollama does not seem to be running. Start it with: ollama serve"
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  All services launched!"
echo "=========================================="
echo "  LiveKit Server:              ws://localhost:7880"
echo "  Voice Server (STT+TTS):      http://localhost:8005"
echo "  Ollama (gemma4-agent:12b):   http://localhost:11434"
echo ""
echo "  Next: cd agent-backend && source venv/bin/activate && python agent.py start"
echo "=========================================="

# Wait for LiveKit to keep script alive
wait $LIVEKIT_PID
