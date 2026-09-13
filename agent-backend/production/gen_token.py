#!/usr/bin/env python3
"""Generate a long-lived LiveKit token for the phone app.

Reads LIVEKIT_API_KEY/SECRET from agent-backend/.env (defaults to the dev
key/secret). Prints the JWT on stdout. A 10-year TTL means the token never
expires in practice, so the app never suffers a "token expired" outage.

Usage: python gen_token.py [room] [identity] [days]
"""
import os
import sys
from datetime import timedelta

from dotenv import load_dotenv
from livekit import api

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, "..", ".env"))

room = sys.argv[1] if len(sys.argv) > 1 else "my-room"
identity = sys.argv[2] if len(sys.argv) > 2 else "niranjan-phone"
days = int(sys.argv[3]) if len(sys.argv) > 3 else 3650

key = os.getenv("LIVEKIT_API_KEY", "devkey")
secret = os.getenv("LIVEKIT_API_SECRET", "secret")

token = (
    api.AccessToken(key, secret)
    .with_identity(identity)
    .with_name("Niranjan")
    .with_grants(api.VideoGrants(room_join=True, room=room))
    .with_ttl(timedelta(days=days))
    .to_jwt()
)
print(token)
