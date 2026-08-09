import hashlib, hmac
import pytest
from app import external_integrations as ext
from app.providers import ProviderConfigurationError, UnconfiguredProvider

def test_meta_state_is_signed_and_tamper_proof():
    state=ext.meta_state('state-secret','workspace-1')
    assert ext.verify_meta_state('state-secret',state)=='workspace-1'
    with pytest.raises(ValueError): ext.verify_meta_state('wrong',state)

def test_payment_webhook_signature_contract():
    body=b'{"event":"paid"}'; sig=hmac.new(b'payment-secret',body,hashlib.sha256).hexdigest()
    ext.verify_payment_signature(body,sig,'payment-secret')
    with pytest.raises(ValueError): ext.verify_payment_signature(body,'bad','payment-secret')

def test_unconfigured_ai_provider_never_fakes_output():
    import asyncio
    async def call():
        await UnconfiguredProvider('Vision').analyze([], 'x')
    with pytest.raises(ProviderConfigurationError):
        asyncio.run(call())
