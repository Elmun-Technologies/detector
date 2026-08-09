"""Evidence / fact policy.

Every claim in a report must be labelled with where it came from, and nothing
that leaves the API may contain a secret, a raw provider payload or a server
filesystem path.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.config import settings
from app.evidence import (
    EvidenceKind,
    EvidencePolicyError,
    assert_clean,
    citation,
    evidence,
    insufficient,
    is_stale,
    redact,
    today,
)
from app.providers import Transcript, TranscriptSegment, Usage, UsageLedger
from app.reporting import ReportInputs, build_report
from app.schemas import VideoContext
from conftest import override, restore


def test_evidence_kinds_are_the_documented_five():
    assert {kind.value for kind in EvidenceKind} == {
        'verified_fact',
        'account_history',
        'external_source',
        'ai_inference',
        'insufficient_data',
    }


def test_external_claim_without_a_citation_is_demoted_to_insufficient_data():
    item = evidence('benchmark', EvidenceKind.EXTERNAL_SOURCE, 'Bozor benchmarki', 'Reels o‘rtacha retention 45%.')
    assert item.kind == 'insufficient_data'
    assert 'manba' in item.detail

    sourced = evidence(
        'benchmark',
        EvidenceKind.EXTERNAL_SOURCE,
        'Bozor benchmarki',
        'Reels o‘rtacha retention 45%.',
        citations=[citation('https://example.com/report', 'Reels benchmark 2026', published_on=today())],
    )
    assert sourced.kind == 'external_source'
    assert sourced.citations[0].accessed_on == today()


def test_citations_are_marked_stale_after_the_configured_window():
    fresh = citation('https://example.com/a', 'Fresh', published_on=today() - timedelta(days=5))
    old = citation('https://example.com/b', 'Old', published_on=today() - timedelta(days=settings.stale_evidence_days + 10))
    assert fresh.stale is False
    assert old.stale is True
    assert is_stale(None) is False
    assert is_stale(date(2000, 1, 1), max_age_days=10) is True

    item = evidence('benchmark', EvidenceKind.EXTERNAL_SOURCE, 'Eski manba', 'Eski hisobot.', citations=[old])
    assert item.stale is True, 'a stale citation makes the whole evidence entry stale'


def test_insufficient_data_is_explicit_not_a_guess():
    item = insufficient('prediction', 'Tarix yetarli emas', 'O‘rtacha ko‘rish soni berilmagan.')
    assert item.kind == 'insufficient_data'
    assert item.citations == []


def test_redact_removes_secrets_raw_payloads_and_inline_media():
    payload = {
        'api_key': 'sk-live-secret',
        'authorization': 'Bearer abc',
        'nested': {'password': 'hunter2', 'raw_response': {'choices': [{'text': 'x'}]}},
        'items': [{'token': 'tg-token', 'ok': 1}],
        'thumbnail': 'data:image/jpeg;base64,AAAA',
        'blob': b'\x00\x01\x02',
        'kept': 'visible',
    }
    cleaned = redact(payload)
    assert cleaned['api_key'] == '[redacted]'
    assert cleaned['authorization'] == '[redacted]'
    assert cleaned['nested']['password'] == '[redacted]'
    assert 'raw_response' not in cleaned['nested']
    assert cleaned['items'][0]['token'] == '[redacted]'
    assert cleaned['thumbnail'] == '[inline media removed]'
    assert cleaned['blob'] == '[3 bytes]'
    assert cleaned['kept'] == 'visible'
    assert_clean(cleaned)


@pytest.mark.parametrize(
    'payload',
    [
        {'provider_response': {'id': 'chatcmpl-1'}},
        {'report': {'debug': {'raw': 'body'}}},
        {'settings': {'api_key': 'sk-live'}},
        {'items': [{'image_url': 'https://cdn/x.jpg'}]},
        {'preview': 'data:image/png;base64,QUJD'},
    ],
)
def test_assert_clean_blocks_leaky_payloads(payload):
    with pytest.raises(EvidencePolicyError):
        assert_clean(payload)


def test_assert_clean_allows_already_redacted_values():
    assert_clean({'api_key': '[redacted]', 'token': None, 'report': {'scores': {'viral_score': 71}}})


def _inputs(**overrides) -> ReportInputs:
    base = {
        'context': VideoContext(title='Evidence test', account={'account_type': 'expert'}),
        'provider_mode': 'demo',
        'language': 'uz',
        'usage': UsageLedger(),
    }
    base.update(overrides)
    return ReportInputs(**base)


def test_report_labels_every_signal_and_never_claims_unmeasured_facts():
    report = build_report(_inputs())
    kinds = {item.kind for item in report.evidence}
    assert kinds <= {'verified_fact', 'account_history', 'external_source', 'ai_inference', 'insufficient_data'}
    signals = {item.signal: item for item in report.evidence}
    # No media was analysed and no history was supplied: both must say so.
    assert signals['media'].kind == 'insufficient_data'
    assert signals['prediction'].kind == 'insufficient_data'
    assert signals['scoring'].kind == 'ai_inference'
    assert report.prediction.basis == 'insufficient_data'
    assert report.prediction.expected_views is None


def test_account_history_prediction_is_labelled_account_history():
    context = VideoContext(
        title='History',
        account={'account_type': 'expert', 'average_views': 9000, 'best_views': 40000},
    )
    report = build_report(_inputs(context=context))
    prediction_evidence = next(item for item in report.evidence if item.signal == 'prediction')
    assert prediction_evidence.kind == 'account_history'
    assert report.prediction.basis == 'account_history'
    assert report.prediction.low_views <= report.prediction.expected_views <= report.prediction.high_views


def test_transcript_is_a_verified_fact_and_timeline_probability_is_inference():
    transcript = Transcript(
        text='bir ikki uch to‘rt besh',
        language='uz',
        segments=[TranscriptSegment(start_seconds=0.0, end_seconds=2.0, text='bir ikki')],
        usage=Usage(kind='stt', provider='openai', model='whisper-1', mode='production'),
    )
    context = VideoContext(title='T', duration_seconds=6, account={'account_type': 'expert'})
    report = build_report(_inputs(context=context, transcript=transcript))
    transcript_evidence = next(item for item in report.evidence if item.signal == 'transcript')
    assert transcript_evidence.kind == 'verified_fact'
    assert report.timeline, 'timeline must exist when a duration is known'
    assert all(entry.evidence_kind == 'ai_inference' for entry in report.timeline)


def test_report_payload_survives_the_outbound_policy_check():
    report = build_report(_inputs())
    assert_clean(report.model_dump(mode='json'))


def test_demo_narrative_is_refused_when_demo_providers_are_disabled():
    from app.providers import ProviderConfigurationError

    previous = override(allow_demo_providers=False)
    try:
        with pytest.raises(ProviderConfigurationError):
            build_report(_inputs(provider_mode='unconfigured'))
    finally:
        restore(previous)
