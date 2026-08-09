"""Production provider contracts. No provider returns fabricated media or research output."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol
import httpx
from .config import settings
class ProviderConfigurationError(RuntimeError): pass
class ProviderFailure(RuntimeError): pass
@dataclass(frozen=True)
class Usage: provider:str; model:str; input_tokens:int=0; output_tokens:int=0; cost_usd:float|None=None
@dataclass(frozen=True)
class Transcript: text:str; language:str; usage:Usage
@dataclass(frozen=True)
class Citation: url:str; title:str; published_on:date|None; accessed_on:date
def required(value:str|None, name:str)->str:
    if not value: raise ProviderConfigurationError(f'{name} is required for this production integration')
    return value
class STTProvider(Protocol):
 async def transcribe(self, audio:Path, language:str)->Transcript: ...
class VisionProvider(Protocol):
 async def analyze(self, frames:list[Path], prompt:str)->tuple[dict,Usage]: ...
class OCRProvider(Protocol):
 async def extract(self, frames:list[Path], language:str)->tuple[str,Usage]: ...
class AudioProvider(Protocol):
 async def analyze(self, audio:Path)->tuple[dict,Usage]: ...
class ResearchProvider(Protocol):
 async def research(self, claims:list[str])->list[Citation]: ...
class OpenAICompatible:
 def __init__(self): self.key=required(settings.openai_api_key,'OPENAI_API_KEY')
 async def _post(self,path:str,files=None,data=None,json=None):
  headers={'Authorization':f'Bearer {self.key}'}
  try:
   async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=10)) as c:
    r=await c.post(settings.openai_base_url.rstrip('/')+path,headers=headers,files=files,data=data,json=json);r.raise_for_status();return r.json()
  except (httpx.HTTPError, asyncio.TimeoutError) as e: raise ProviderFailure(f'OpenAI provider failure: {e}') from e
 async def transcribe(self,audio:Path,language:str)->Transcript:
  with audio.open('rb') as f: result=await self._post('/audio/transcriptions',files={'file':(audio.name,f,'audio/mpeg')},data={'model':'whisper-1','language':language})
  return Transcript(result.get('text',''),language,Usage('openai','whisper-1'))
 async def analyze(self,frames:list[Path],prompt:str)->tuple[dict,Usage]:
  if not frames: raise ProviderFailure('Vision requires extracted frames')
  # Caller can substitute another multimodal adapter; no fake response is generated.
  raise ProviderConfigurationError('Vision multimodal endpoint adapter must be configured with VISION_PROVIDER')
class UnconfiguredProvider:
 def __init__(self,name:str): self.name=name
 def __getattr__(self,_):
  async def fail(*args,**kwargs): raise ProviderConfigurationError(f'{self.name} provider is not configured')
  return fail
def stt_provider(): return OpenAICompatible() if settings.openai_api_key else UnconfiguredProvider('STT')
def vision_provider(): return UnconfiguredProvider('Vision')
def ocr_provider(): return UnconfiguredProvider('OCR')
def audio_provider(): return UnconfiguredProvider('Audio')
def research_provider(): return UnconfiguredProvider('Research/fact-check')
