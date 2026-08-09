from __future__ import annotations
import base64, hashlib, hmac, time
from collections import defaultdict, deque
from fastapi import HTTPException, Request
from cryptography.fernet import Fernet
from .config import settings
_hits=defaultdict(deque)
def rate_limit(request:Request):
 key=request.client.host if request.client else 'unknown'; now=time.time(); q=_hits[key]
 while q and q[0]<now-60:q.popleft()
 if len(q)>=settings.rate_limit_per_minute: raise HTTPException(429,'Too many requests')
 q.append(now)
def cipher():
 if not settings.encryption_key: raise RuntimeError('ENCRYPTION_KEY is required before connecting Instagram')
 return Fernet(settings.encryption_key.encode())
def encrypt_token(token:str)->str:return cipher().encrypt(token.encode()).decode()
def decrypt_token(value:str)->str:return cipher().decrypt(value.encode()).decode()
def verify_telegram_webapp(init_data:str)->bool:
 # Telegram HMAC validation boundary; do not trust client-provided user/workspace IDs.
 if not settings.telegram_bot_token:return False
 pairs=dict(x.split('=',1) for x in init_data.split('&') if '=' in x); check=pairs.pop('hash',None)
 payload='\n'.join(f'{k}={v}' for k,v in sorted(pairs.items())); key=hmac.new(b'WebAppData',settings.telegram_bot_token.encode(),hashlib.sha256).digest()
 return bool(check) and hmac.compare_digest(hmac.new(key,payload.encode(),hashlib.sha256).hexdigest(),check)
def hash_ip(ip:str|None)->str|None:return hashlib.sha256(ip.encode()).hexdigest() if ip else None
