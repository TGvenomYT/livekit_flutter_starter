#!/bin/bash
# Launch LiveKit with node-ip pinned to the Mac's CURRENT LAN IP.
#
# Why: LiveKit advertises node-ip as the address the phone should send WebRTC
# media (UDP 7882) to. If it's stale/wrong, signaling connects but media never
# does — the exact "connects then times out" symptom. Computing it fresh at
# every launch (and restarting on IP change via netwatch) keeps media correct.

LIVEKIT_BIN="$(command -v livekit-server || echo /opt/homebrew/bin/livekit-server)"

# Prefer Wi-Fi (en0), fall back to en1 (Ethernet/dongle). Absolute path to
# ipconfig so we don't depend on launchd's PATH.
IP="$(/usr/sbin/ipconfig getifaddr en0 2>/dev/null)"
[ -z "$IP" ] && IP="$(/usr/sbin/ipconfig getifaddr en1 2>/dev/null)"

if [ -z "$IP" ]; then
  # No network yet — start anyway and let netwatch restart us once an IP appears.
  echo "$(date '+%H:%M:%S') no LAN IP yet; starting without node-ip"
  exec "$LIVEKIT_BIN" --dev --bind 0.0.0.0
fi

echo "$(date '+%H:%M:%S') starting livekit with node-ip $IP"
exec "$LIVEKIT_BIN" --dev --bind 0.0.0.0 --node-ip "$IP"
