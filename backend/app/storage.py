"""Private object storage adapters. Keys are generated server-side and downloads use short-lived URLs."""
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from .config import settings
class Storage:
 def put(self, source:Path, name:str)->str: raise NotImplementedError
 def download(self, key:str, destination:Path)->Path: raise NotImplementedError
 def delete(self,key:str)->None: raise NotImplementedError
class LocalStorage(Storage):
 def put(self,source,name):
  key=f'{uuid4()}-{Path(name).name}'; target=settings.uploads_dir/key; target.parent.mkdir(parents=True,exist_ok=True); source.replace(target); return key
 def download(self,key,destination):
  import shutil; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(settings.uploads_dir/key,destination); return destination
 def delete(self,key): (settings.uploads_dir/key).unlink(missing_ok=True)
class S3Storage(Storage):
 def __init__(self):
  import boto3
  self.client=boto3.client('s3',endpoint_url=settings.s3_endpoint,aws_access_key_id=settings.s3_access_key,aws_secret_access_key=settings.s3_secret_key)
 def put(self,source,name):
  key=f'videos/{uuid4()}-{Path(name).name}'; self.client.upload_file(str(source),settings.s3_bucket,key,ExtraArgs={'ACL':'private'}); source.unlink(missing_ok=True); return key
 def download(self,key,destination):
  destination.parent.mkdir(parents=True,exist_ok=True); self.client.download_file(settings.s3_bucket,key,str(destination)); return destination
 def delete(self,key): self.client.delete_object(Bucket=settings.s3_bucket,Key=key)
def get_storage()->Storage: return S3Storage() if settings.storage_backend=='s3' else LocalStorage()
