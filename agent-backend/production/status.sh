#!/bin/bash
# Quick health view of the Jarvis production stack.
UID_="$(id -u)"
HOSTNAME_LOCAL="$(scutil --get LocalHostName).local"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"

echo "LAN IP: ${IP:-none}   mDNS: ${HOSTNAME_LOCAL}   app URL: ws://${HOSTNAME_LOCAL}:7880"
echo ""
printf "%-24s %-10s %s\n" "SERVICE" "STATE" "PID"
for L in com.jarvis.livekit com.jarvis.voiceserver com.jarvis.agent com.jarvis.netwatch; do
  info="$(launchctl print "gui/${UID_}/${L}" 2>/dev/null)"
  if [ -z "$info" ]; then
    printf "%-24s %-10s %s\n" "$L" "MISSING" "-"
  else
    pid="$(echo "$info" | awk '/pid = /{print $3; exit}')"
    state="$(echo "$info" | awk '/state = /{print $3; exit}')"
    printf "%-24s %-10s %s\n" "$L" "${state:-?}" "${pid:-none}"
  fi
done
echo ""
echo "Ports:"; lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | grep -E ':(7880|8005)' | awk '{print "  "$1, $9}'
echo "LiveKit node-ip (media):"; lsof -nP -iUDP 2>/dev/null | grep -i livekit | awk '{print "  "$9}' | head -1
echo "Ollama model:"; ollama ps 2>/dev/null | tail -n +2 | awk '{print "  "$1, $6, $7}'