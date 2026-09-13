"""Local, fully-offline memory for Jarvis.

One JSON file is the single source of truth for two things:

  1. TERMS  — proper nouns (people, projects, acronyms) with a short meaning.
              These are written to `hotwords.txt`, which the voice server feeds
              to Whisper as decoding hints, AND injected into the LLM's system
              prompt as a glossary. This is what stops "SIH" being heard as
              "NIH": the transcriber is biased toward the real word, and if it
              still slips, the LLM knows what the user actually means.
  2. FACTS  — freeform things to remember across sessions.

No daemon, no network, no Tailscale — it's a file next to the agent.
"""

import json
import os
import re
import threading
import time
from typing import Dict, List

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(_DIR, "jarvis_memory.json")
HOTWORDS_PATH = os.path.join(_DIR, "hotwords.txt")

_lock = threading.Lock()

# Seeded from Niranjan's known projects so the very first session already
# recognises these names. Edit freely — `remember` adds more at runtime.
SEED_TERMS: Dict[str, str] = {
    "SIH": "Smart India Hackathon 2026 flood-management project; productised as SafeSphere with the Flatline Mesh victim-detection system.",
    "SafeSphere": "Niranjan's flood/disaster victim-detection product at safesphere.me — the SIH project.",
    "Flatline Mesh": "The three-layer victim-detection system inside SafeSphere.",
    "myserver": "Niranjan's homelab server at 192.168.1.10 running Docker, self-hosted Supabase, and the devops agent.",
    "Jarvis": "This local voice assistant, running offline on Niranjan's Mac.",
    "Niranjan": "The user and owner of this system.",
    "agentkit": "Niranjan's tool gateway at ~/agent-tools that exposes tools over MCP.",
    "Cortex": "Niranjan's local-LLM personal assistant daemon.",
    "Exotel": "Telephony provider used by the Hotel Calling Agent.",
    "Blackwall": "Niranjan's homelab-scoped recon/pentest agent.",
    "CWC": "Central Water Commission — its flood gauge API feeds SafeSphere's Layer 1.",
    "KPRIET": "Niranjan's college (KPR Institute, Arasur).",
}


def _default() -> Dict:
    return {"terms": dict(SEED_TERMS), "facts": []}


def load() -> Dict:
    with _lock:
        if not os.path.exists(STORE_PATH):
            data = _default()
            _save_unlocked(data)
            return data
        try:
            with open(STORE_PATH, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = _default()
            _save_unlocked(data)
            return data
    # Backfill any seed terms the user hasn't overridden (non-destructive).
    changed = False
    for k, v in SEED_TERMS.items():
        if k not in data.get("terms", {}):
            data.setdefault("terms", {})[k] = v
            changed = True
    data.setdefault("facts", [])
    if changed:
        save(data)
    return data


def _save_unlocked(data: Dict) -> None:
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE_PATH)
    _write_hotwords_unlocked(data)


def save(data: Dict) -> None:
    with _lock:
        _save_unlocked(data)


# ── writes ──────────────────────────────────────────────────────────────────
def add_term(term: str, meaning: str) -> None:
    data = load()
    data["terms"][term.strip()] = meaning.strip()
    save(data)


def add_fact(text: str) -> None:
    text = text.strip()
    if not text:
        return
    data = load()
    data["facts"].append({"text": text, "ts": time.time()})
    # Auto-promote proper nouns/acronyms in the fact into the hotword vocab
    # so newly-mentioned names get recognised by STT next time too.
    for token in _proper_nouns(text):
        data["terms"].setdefault(token, "(mentioned by the user)")
    save(data)


# ── reads ───────────────────────────────────────────────────────────────────
def search(query: str, limit: int = 5) -> List[str]:
    """Keyword search over terms + facts. Offline, no embeddings needed."""
    data = load()
    q_words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1}
    scored = []
    for term, meaning in data["terms"].items():
        hay = f"{term} {meaning}".lower()
        score = sum(1 for w in q_words if w in hay)
        if term.lower() in query.lower():
            score += 3
        if score:
            scored.append((score, f"{term}: {meaning}"))
    for fact in data["facts"]:
        hay = fact["text"].lower()
        score = sum(1 for w in q_words if w in hay)
        if score:
            scored.append((score, fact["text"]))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for _, text in scored[:limit]]


def glossary_text() -> str:
    """Formatted term list for the system prompt."""
    data = load()
    lines = [f"- {t}: {m}" for t, m in data["terms"].items()]
    return "\n".join(lines)


def hotwords_list() -> List[str]:
    data = load()
    words = set()
    for term in data["terms"]:
        words.add(term)
        for tok in term.split():
            words.add(tok)
    return sorted(words)


# ── helpers ─────────────────────────────────────────────────────────────────
def _proper_nouns(text: str) -> List[str]:
    # Acronyms (SIH, CWC, APK) and Capitalised words that aren't sentence starts.
    acronyms = re.findall(r"\b[A-Z]{2,}\b", text)
    caps = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)
    stop = {"The", "This", "That", "When", "What", "Then", "They", "Remember", "Jarvis"}
    return list({*acronyms, *[c for c in caps if c not in stop]})


def _write_hotwords_unlocked(data: Dict) -> None:
    words = set()
    for term in data.get("terms", {}):
        words.add(term)
        for tok in term.split():
            words.add(tok)
    tmp = HOTWORDS_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(" ".join(sorted(words)))
    os.replace(tmp, HOTWORDS_PATH)


def ensure_initialised() -> None:
    """Called at agent startup: materialise the store + hotwords.txt on disk."""
    load()


if __name__ == "__main__":
    ensure_initialised()
    print("store:", STORE_PATH)
    print("hotwords:", HOTWORDS_PATH)
    print("glossary:\n" + glossary_text())
    print("\nhotwords:", " ".join(hotwords_list()))
