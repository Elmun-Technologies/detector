from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .schemas import ScoreBreakdown, VideoContext


BASE_WEIGHTS: dict[str, float] = {
    "hook": 0.15,
    "retention": 0.20,
    "share": 0.15,
    "save": 0.10,
    "rewatch": 0.10,
    "visual": 0.08,
    "audio": 0.05,
    "clarity": 0.07,
    "audience_fit": 0.05,
    "cta": 0.05,
}

# The first version deliberately makes weights explicit and inspectable.
# In production these can be learned per workspace after enough post-factum data.
ACCOUNT_WEIGHT_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "entertainment": {"share": 0.04, "rewatch": 0.03, "save": -0.04, "cta": -0.03},
    "expert": {"save": 0.04, "retention": 0.02, "share": -0.02, "rewatch": -0.02, "cta": -0.02},
    "education": {"save": 0.05, "clarity": 0.03, "share": -0.03, "rewatch": -0.03, "cta": -0.02},
    "product": {"cta": 0.05, "audience_fit": 0.02, "rewatch": -0.04, "save": -0.03},
    "local_business": {"cta": 0.05, "audience_fit": 0.03, "rewatch": -0.04, "share": -0.02, "save": -0.02},
    "b2b": {"clarity": 0.04, "save": 0.03, "cta": 0.02, "rewatch": -0.05, "share": -0.04},
}

HOOK_MARKERS = ("nega", "xato", "sir", "to‘xt", "to'xt", "savol", "?", "3 ta", "5 ta", "2026", "hech kim")
VALUE_MARKERS = ("qadam", "checklist", "cheklist", "formula", "usul", "qanday", "3 ta", "5 ta", "ro‘yxat", "ro'yxat")
CTA_MARKERS = ("saql", "ulash", "izoh", "komment", "obuna", "kuzat", "yozing", "direct", "havola")
EMOTION_MARKERS = ("hayrat", "xato", "hech kim", "aslida", "ammo", "natija", "oldin", "keyin")


@dataclass(frozen=True)
class RawSignals:
    """Signals sourced from processing workers or a model gateway.

    Values are normalized to 0–100 before arriving here. The deterministic
    fallback below intentionally avoids fabricating data that was not observed.
    """

    hook: int
    retention: int
    share: int
    save: int
    rewatch: int
    visual: int
    audio: int
    clarity: int
    audience_fit: int
    cta: int
    confidence: int


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def normalized_weights(account_type: str) -> dict[str, float]:
    weights = dict(BASE_WEIGHTS)
    for metric, change in ACCOUNT_WEIGHT_ADJUSTMENTS.get(account_type, {}).items():
        weights[metric] += change
    total = sum(weights.values())
    return {metric: weight / total for metric, weight in weights.items()}


def infer_signals(context: VideoContext) -> RawSignals:
    """Produce an honest, deterministic fallback for a text-only request.

    This is not a replacement for Vision/STT/Audio models. It keeps the MVP
    useful for manually entered ideas and, importantly, lowers confidence when
    video-derived evidence is unavailable.
    """

    transcript = (context.transcript or "").lower()
    title = (context.title or "").lower()
    topic = (context.topic or "").lower()
    text = " ".join((title, topic, transcript))
    duration = context.duration_seconds

    has_hook = any(marker in text[:220] for marker in HOOK_MARKERS)
    has_value = any(marker in text for marker in VALUE_MARKERS)
    has_cta = any(marker in text[-300:] for marker in CTA_MARKERS)
    has_emotion = any(marker in text for marker in EMOTION_MARKERS)
    has_specific_audience = bool(context.audience and len(context.audience.strip()) > 12)
    vertical = context.width and context.height and context.height > context.width

    hook = 62 + (14 if has_hook else -9) + (5 if title else 0)
    clarity = 60 + (13 if has_value else -6) + (7 if len(text.split()) > 18 else 0)
    cta = 51 + (23 if has_cta else -10)
    save = 54 + (20 if has_value else -8) + (7 if context.objective == "save" else 0)
    share = 51 + (11 if has_emotion else 0) + (7 if context.objective == "share" else 0)
    audience_fit = 55 + (18 if has_specific_audience else 0) + (7 if context.account.niche else 0)
    visual = 58 + (18 if vertical else -5) + (7 if context.has_subtitles else 0)
    audio = 62 if transcript else 42

    if duration is None:
        retention = 56
        rewatch = 56
    elif duration <= 12:
        retention, rewatch = 79, 70
    elif duration <= 35:
        retention, rewatch = 68, 62
    elif duration <= 60:
        retention, rewatch = 58, 52
    else:
        retention, rewatch = 46, 42

    fields_provided = sum(
        bool(value)
        for value in (
            context.title, context.topic, context.transcript, context.duration_seconds,
            context.width, context.height, context.audience, context.account.niche,
        )
    )
    confidence = 30 + fields_provided * 7 + (10 if transcript else 0)
    return RawSignals(
        hook=clamp(hook), retention=clamp(retention), share=clamp(share),
        save=clamp(save), rewatch=clamp(rewatch), visual=clamp(visual),
        audio=clamp(audio), clarity=clamp(clarity), audience_fit=clamp(audience_fit),
        cta=clamp(cta), confidence=clamp(confidence),
    )


def score(context: VideoContext, observed: Mapping[str, int] | None = None) -> ScoreBreakdown:
    inferred = infer_signals(context)
    values = {
        "hook": inferred.hook,
        "retention": inferred.retention,
        "share": inferred.share,
        "save": inferred.save,
        "rewatch": inferred.rewatch,
        "visual": inferred.visual,
        "audio": inferred.audio,
        "clarity": inferred.clarity,
        "audience_fit": inferred.audience_fit,
        "cta": inferred.cta,
    }
    if observed:
        for name, value in observed.items():
            if name in values:
                values[name] = clamp(value)

    weights = normalized_weights(context.account.account_type)
    viral_score = clamp(sum(values[metric] * weights[metric] for metric in weights))
    # Only observed multimodal fields should materially raise confidence.
    observed_count = len(set(observed or {}).intersection(values))
    confidence = clamp(inferred.confidence + observed_count * 4)

    return ScoreBreakdown(
        viral_score=viral_score,
        hook_score=values["hook"],
        retention_score=values["retention"],
        visual_score=values["visual"],
        audio_score=values["audio"],
        share_score=values["share"],
        save_score=values["save"],
        rewatch_score=values["rewatch"],
        clarity_score=values["clarity"],
        audience_fit_score=values["audience_fit"],
        cta_score=values["cta"],
        confidence=confidence,
    )
