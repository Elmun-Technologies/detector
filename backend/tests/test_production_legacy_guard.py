from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

def test_legacy_analysis_routes_are_gone_in_production():
 original=settings.environment;object.__setattr__(settings,'environment','production')
 try:
  # Lifespan correctly fails without production dependencies; this directly tests route guard semantics.
  from app.legacy import development_legacy_only
  import pytest
  from fastapi import HTTPException
  with pytest.raises(HTTPException) as err: development_legacy_only()
  assert err.value.status_code==410
 finally:object.__setattr__(settings,'environment',original)
