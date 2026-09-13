#!/bin/bash
# Remove the Jarvis launchd agents (stops auto-start). Leaves code + plists on
# disk unless --purge is given.
UID_="$(id -u)"
LA="$HOME/Library/LaunchAgents"
for L in com.jarvis.livekit com.jarvis.voiceserver com.jarvis.agent com.jarvis.netwatch; do
  launchctl bootout "gui/${UID_}/${L}" 2>/dev/null && echo "booted out $L" || echo "$L not loaded"
  if [ "${1:-}" = "--purge" ]; then rm -f "$LA/${L}.plist" && echo "  removed $LA/${L}.plist"; fi
done
echo "Done. (Services stopped; run install.sh to bring them back.)"
