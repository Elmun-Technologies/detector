from __future__ import annotations
import json, subprocess
from dataclasses import dataclass
from pathlib import Path
ALLOWED_CONTENT_TYPES={'video/mp4','video/quicktime','video/x-msvideo','application/octet-stream'}; ALLOWED_SUFFIXES={'.mp4','.mov','.avi'}
class VideoValidationError(ValueError):pass
@dataclass(frozen=True)
class VideoMetadata:
 duration_seconds:float|None=None; width:int|None=None; height:int|None=None; has_audio:bool|None=None; vertical:bool|None=None; silence_seconds:float|None=None
def validate_upload(filename,content_type,size_bytes,max_upload_bytes):
 if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:raise VideoValidationError('Faqat MP4, MOV yoki AVI video qabul qilinadi.')
 if content_type and content_type not in ALLOWED_CONTENT_TYPES:raise VideoValidationError('Faylning Content-Type qiymati video formatiga mos emas.')
 if size_bytes<=0:raise VideoValidationError('Bo‘sh faylni tahlil qilib bo‘lmaydi.')
 if size_bytes>max_upload_bytes:raise VideoValidationError(f'Fayl hajmi {max_upload_bytes//(1024*1024)} MB limitdan oshgan.')
def probe_video(path:Path)->VideoMetadata:
 try:out=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(path)],capture_output=True,check=True,text=True,timeout=20)
 except (FileNotFoundError,subprocess.CalledProcessError,subprocess.TimeoutExpired):return VideoMetadata()
 try:
  data=json.loads(out.stdout); streams=data.get('streams',[]); v=next((s for s in streams if s.get('codec_type')=='video'),{}); w=v.get('width');h=v.get('height'); d=data.get('format',{}).get('duration')
  return VideoMetadata(round(float(d),2) if d else None,w,h,any(s.get('codec_type')=='audio' for s in streams),bool(w and h and h>=w))
 except (ValueError,TypeError,json.JSONDecodeError):return VideoMetadata()
def detect_silence(path:Path)->float|None:
 """Return total silencedetect duration; None means ffmpeg is unavailable."""
 try:r=subprocess.run(['ffmpeg','-i',str(path),'-af','silencedetect=noise=-35dB:d=0.4','-f','null','-'],capture_output=True,text=True,timeout=120)
 except (FileNotFoundError,subprocess.TimeoutExpired):return None
 import re
 return round(sum(float(x) for x in re.findall(r'silence_duration: ([0-9.]+)',r.stderr)),2)
