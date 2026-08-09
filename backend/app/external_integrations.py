"""Credential-gated production HTTP contracts for Meta OAuth and payment webhooks."""
from __future__ import annotations
import base64, hashlib, hmac, json, secrets
from dataclasses import dataclass
from urllib.parse import urlencode
import httpx
from .config import settings
from .providers import ProviderConfigurationError, ProviderFailure
@dataclass(frozen=True)
class OAuthState: value:str
def meta_ready():
 if not (settings.meta_app_id and settings.meta_app_secret and settings.meta_redirect_uri): raise ProviderConfigurationError('META_APP_ID, META_APP_SECRET and META_REDIRECT_URI are required')
def meta_state(secret:str, workspace_id:str)->str:
 nonce=secrets.token_urlsafe(24); body=f'{workspace_id}.{nonce}'; sig=hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest();return base64.urlsafe_b64encode(f'{body}.{sig}'.encode()).decode()
def verify_meta_state(secret:str,value:str)->str:
 try:
  body,sig=base64.urlsafe_b64decode(value.encode()).decode().rsplit('.',1)
  if not hmac.compare_digest(sig,hmac.new(secret.encode(),body.encode(),hashlib.sha256).hexdigest()):raise ValueError
  return body.split('.',1)[0]
 except Exception as e: raise ValueError('Invalid Meta OAuth state') from e
def meta_authorize_url(state:str)->str:
 meta_ready(); return 'https://www.facebook.com/v20.0/dialog/oauth?'+urlencode({'client_id':settings.meta_app_id,'redirect_uri':settings.meta_redirect_uri,'state':state,'scope':'instagram_basic,instagram_manage_insights,pages_show_list'})
async def exchange_meta_code(code:str)->dict:
 meta_ready()
 try:
  async with httpx.AsyncClient(timeout=20) as c:
   r=await c.get('https://graph.facebook.com/v20.0/oauth/access_token',params={'client_id':settings.meta_app_id,'client_secret':settings.meta_app_secret,'redirect_uri':settings.meta_redirect_uri,'code':code});r.raise_for_status();return r.json()
 except httpx.HTTPError as e:raise ProviderFailure(f'Meta OAuth exchange failed: {e}') from e
def verify_payment_signature(payload:bytes,signature:str|None,secret:str)->None:
 expected=hmac.new(secret.encode(),payload,hashlib.sha256).hexdigest()
 if not signature or not hmac.compare_digest(expected,signature):raise ValueError('Invalid payment webhook signature')
def payment_provider_ready(provider:str):
 keys={'stripe':(settings.stripe_secret_key,settings.stripe_webhook_secret),'payme':(settings.payme_key,), 'click':(settings.click_secret_key,)}
 if provider not in keys or not all(keys[provider]): raise ProviderConfigurationError(f'Credentials for payment provider {provider} are required')
