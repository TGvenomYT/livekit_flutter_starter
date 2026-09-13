#!/bin/bash
# Watch the LAN IP; when it changes, restart LiveKit so node-ip stays correct.
# This is what makes the system survive DHCP lease changes / network switches
# without a manual restart. Runs forever under launchd (KeepAlive).

LABEL="com.jarvis.livekit"
UID_="$(id -u)"
LAST=""

current_ip() {
  /usr/sbin/ipconfig getifaddr en0 2>/dev/null || /usr/sbin/ipconfig getifaddr en1 2>/dev/null
}

while true; do
  IP="$(current_ip)"
  if [ "$IP" != "$LAST" ]; then
    if [ -n "$LAST" ]; then
      echo "$(date '+%H:%M:%S') LAN IP changed: '$LAST' -> '$IP'; restarting $LABEL"
      /bin/launchctl kickstart -k "gui/${UID_}/${LABEL}" 2>/dev/null
    fi
    LAST="$IP"
  fi
  sleep 15
done
