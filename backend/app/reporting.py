"""Report composition.

Takes measured media artifacts plus AI provider output and produces the
persisted :class:`AnalysisReport`: scores, a second-by-second timeline, an
improved hook/script/CTA, an editor brief, a prediction range and the evidence
list that explains where every claim came from.

The narrative parts (hooks, script, CTA, editor brief) come from the LLM
provider in production. The deterministic Uzbek fallback text is only allowed
when the pipeline runs in demo mode; :func:`build_report` refuses to fabricate
it otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import settings
from .evidence import EvidenceKind, evidence, insufficient
from .media import MediaBundle
from .providers import (
    AudioAnalysis,
    LLMReport,
    OCRResult,
    ProviderConfigurationError,
    Transcript,
    UsageLedger,
    VisionResult,
    resolve_language,
)
from .schemas import (
    AnalysisReport,
    Evidence,
    MediaSummary,
    PredictionRange,
    ProviderUsageSummary,
    Segment,
    ThumbnailCandidate,
    TimelineSecond,
    VideoContext,
)
from .scoring import clamp, score


@dataclass
class ReportInputs:
    context: VideoContext
    bundle: MediaBundle | None = None
    transcript: Transcript | None = None
    ocr: OCRResult | None = None
    vision: VisionResult | None = None
    audio: AudioAnalysis | None = None
    llm: LLMReport | None = None
    usage: UsageLedger = field(default_factory=UsageLedger)
    provider_mode: str = 'demo'
    language: str = 'uz'
    thumbnail_keys: dict[float, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- measured signals
def observed_signals(inputs: ReportInputs) -> dict[str, int]:
    """Convert measured media facts into 0–100 signal overrides."""
    bundle = inputs.bundle
    observed: dict[str, int] = {}
    if bundle is None:
        return observed

    probe = bundle.probe
    # Visual pacing: roughly one meaningful change every 2–4 seconds reads well.
    rate = bundle.scene_change_rate
    if rate is not None:
        if rate <= 0.02:
            visual = 45
        elif rate < 0.15:
            visual = 62
        elif rate <= 0.6:
            visual = 82
        else:
            visual = 68
        if probe.is_vertical:
            visual += 6
        if (probe.height or 0) >= 1080:
            visual += 4
        observed['visual'] = clamp(visual)

    # Audio: silence share is measured, so the audio signal is not a guess.
    if probe.has_audio:
        ratio = bundle.speech_ratio
        if ratio is not None:
            observed['audio'] = clamp(40 + ratio * 55)
    else:
        observed['audio'] = 25

    # Retention: long dead air early in the video is the strongest measured risk.
    if probe.duration_seconds:
        penalty = 0
        early_silence = sum(
            window.duration_seconds for window in bundle.silences if window.start_seconds < 5
        )
        penalty += min(18, int(early_silence * 6))
        if bundle.silence_seconds and probe.duration_seconds:
            penalty += min(12, int(bundle.silence_seconds / probe.duration_seconds * 25))
        if penalty:
            base = observed.get('retention', 70)
            observed['retention'] = clamp(base - penalty)

    if inputs.transcript and inputs.transcript.text:
        words = len(inputs.transcript.text.split())
        if probe.duration_seconds:
            wpm = words / max(probe.duration_seconds / 60, 0.01)
            # 120–190 wpm is comfortable for short-form Uzbek/Russian speech.
            observed['clarity'] = clamp(85 if 110 <= wpm <= 200 else 62)

    if inputs.vision and isinstance(inputs.vision.observations, dict):
        quality = inputs.vision.observations.get('visual_quality')
        if isinstance(quality, (int, float)):
            observed['visual'] = clamp((observed.get('visual', int(quality)) + int(quality)) / 2)

    if inputs.audio and isinstance(inputs.audio.metrics, dict):
        clarity = inputs.audio.metrics.get('clarity')
        if isinstance(clarity, (int, float)):
            observed['audio'] = clamp((observed.get('audio', int(clarity)) + int(clarity)) / 2)

    return observed


# --------------------------------------------------------------------------- timeline
def _label_for(second: int, duration: float) -> str:
    if second < 3:
        return 'hook'
    if second < max(5.0, duration * 0.18):
        return 'context'
    if second < max(10.0, duration * 0.55):
        return 'value'
    if second < max(16.0, duration * 0.8):
        return 'proof'
    return 'cta'


def build_timeline(inputs: ReportInputs, scores) -> list[TimelineSecond]:
    """One entry per second with measured flags and an estimated retention curve."""
    bundle = inputs.bundle
    duration = (bundle.probe.duration_seconds if bundle else None) or inputs.context.duration_seconds or 0
    total = int(math.ceil(min(duration, settings.max_duration_seconds)))
    if total <= 0:
        return []

    scenes = [scene.timestamp_seconds for scene in (bundle.scene_changes if bundle else [])]
    silences = bundle.silences if bundle else []
    segments = inputs.transcript.segments if inputs.transcript else ()

    timeline: list[TimelineSecond] = []
    for second in range(total):
        start, end = float(second), float(second + 1)
        scene_change = any(start <= stamp < end for stamp in scenes)
        silent = any(window.start_seconds < end and window.end_seconds > start for window in silences)
        speech = any(item.start_seconds < end and item.end_seconds > start for item in segments)

        label = _label_for(second, duration)
        estimate = scores.hook_score if second < 3 else scores.retention_score
        estimate -= min(22, int(second * 0.45))  # natural decay
        if scene_change:
            estimate += 5
        if silent:
            estimate -= 9
        if speech:
            estimate += 3
        if label == 'cta':
            estimate = int((estimate + scores.cta_score) / 2)

        notes: list[str] = []
        if silent:
            notes.append('jimlik oynasi o‘lchandi')
        if scene_change:
            notes.append('kadr/sahna o‘zgarishi o‘lchandi')
        if not speech and segments:
            notes.append('bu soniyada nutq segmenti yo‘q')

        timeline.append(
            TimelineSecond(
                second=second,
                retention_probability=clamp(estimate),
                scene_change=scene_change,
                silence=silent,
                speech=speech,
                label=label,
                note='; '.join(notes) or None,
                # The flags above are measured; the probability itself is a model estimate.
                evidence_kind='ai_inference',
            )
        )
    return timeline


def build_segments(inputs: ReportInputs, timeline: list[TimelineSecond], scores) -> list[Segment]:
    """Aggregate the per-second timeline into the five review blocks."""
    if not timeline:
        return []
    order = ['hook', 'context', 'value', 'proof', 'cta']
    titles = {
        'hook': 'Hook signali',
        'context': 'Kontekst',
        'value': 'Asosiy qiymat',
        'proof': 'Dalil yoki misol',
        'cta': 'CTA',
    }
    issues = {
        'hook': 'Birinchi 1–3 soniyada va’da yoki muammo tez anglashilishi kerak.',
        'context': 'Kontekst cho‘zilsa, tomoshabin asosiy foydaga yetmasdan chiqib ketishi mumkin.',
        'value': 'Bu qismda vizual yangilanish va qisqa fikrlar retentionni ushlab turadi.',
        'proof': 'Amaliy misol ishonchni oshiradi; u bo‘lmasa foyda umumiy ko‘rinib qolishi mumkin.',
        'cta': 'Umumiy CTA video mazmuni bilan bog‘lanmasa, keyingi harakat ehtimoli past bo‘ladi.',
    }
    recommendations = {
        'hook': 'Natija, muammo yoki qarama-qarshilikni birinchi kadr va birinchi subtitrga olib chiqing.',
        'context': 'Salomlashuv va takror gaplarni kesing; asosiy qiymatga bir gap bilan o‘ting.',
        'value': 'Har 2–3 soniyada B-roll, zoom, ekran yozuvi yoki subtitr urg‘usini almashtiring.',
        'proof': 'Natija, oldin-keyin, screenshot yoki aniq misolni shu yerga joylashtiring.',
        'cta': 'Faqat bitta harakatni so‘rang va foydalanuvchiga uni bajarish sababini bering.',
    }

    segments: list[Segment] = []
    for label in order:
        entries = [entry for entry in timeline if entry.label == label]
        if not entries:
            continue
        average = int(sum(entry.retention_probability for entry in entries) / len(entries))
        silent_seconds = sum(1 for entry in entries if entry.silence)
        issue = issues[label]
        if silent_seconds >= 2:
            issue = f'{issue} O‘lchangan jimlik: {silent_seconds} soniya.'
        segments.append(
            Segment(
                start_time=float(entries[0].second),
                end_time=float(entries[-1].second + 1),
                title=titles[label],
                state='strong' if average >= 72 else ('good' if average >= 60 else 'risk'),
                retention_probability=average,
                issue=issue,
                recommendation=recommendations[label],
            )
        )
    return segments


# --------------------------------------------------------------------------- prediction
def build_prediction(inputs: ReportInputs, scores) -> PredictionRange:
    account = inputs.context.account
    average = account.average_views
    best = account.best_views
    if not average:
        return PredictionRange(
            basis='insufficient_data',
            confidence=min(35, scores.confidence),
            note=(
                'Akkaunt tarixidagi o‘rtacha ko‘rish soni berilmagani uchun ko‘rish oralig‘i hisoblanmadi. '
                'Insights ma’lumotini ulang yoki o‘rtacha ko‘rishni kiriting.'
            ),
        )
    factor = 0.55 + (scores.viral_score / 100) * 1.15
    expected = int(average * factor)
    low = int(expected * 0.55)
    high = int(max(expected * 1.9, (best or average) * 0.9))
    return PredictionRange(
        basis='account_history',
        low_views=low,
        expected_views=expected,
        high_views=high,
        confidence=scores.confidence,
        note=(
            'Oraliq akkauntning o‘z tarixidagi o‘rtacha va eng yaxshi natijaga nisbatan hisoblangan; '
            'bu kafolat emas, ehtimoliy diapazon.'
        ),
    )


# --------------------------------------------------------------------------- evidence
def build_evidence(inputs: ReportInputs, scores, prediction: PredictionRange) -> list[Evidence]:
    items: list[Evidence] = []
    bundle = inputs.bundle
    if bundle:
        probe = bundle.probe
        items.append(
            evidence(
                'media',
                EvidenceKind.VERIFIED_FACT,
                'Media o‘lchovlari',
                (
                    f'FFprobe: {probe.video_codec or "?"} {probe.width}x{probe.height} '
                    f'({probe.aspect_ratio or "?"}), {probe.duration_seconds or 0:.2f}s, '
                    f'audio: {"bor" if probe.has_audio else "yo‘q"}.'
                ),
                confidence=99,
            )
        )
        items.append(
            evidence(
                'visual',
                EvidenceKind.VERIFIED_FACT,
                'Sahna o‘zgarishlari',
                f'{len(bundle.scene_changes)} ta sahna o‘zgarishi aniqlandi (FFmpeg scene detection).',
                confidence=90,
            )
        )
        if probe.has_audio:
            items.append(
                evidence(
                    'audio',
                    EvidenceKind.VERIFIED_FACT,
                    'Jimlik tahlili',
                    f'Jami {bundle.silence_seconds:.2f}s jimlik; nutq ulushi: {bundle.speech_ratio}.',
                    confidence=90,
                )
            )
        else:
            items.append(insufficient('audio', 'Audio yo‘q', 'Faylda audio oqim topilmadi, audio signali o‘lchanmadi.'))
    else:
        items.append(
            insufficient(
                'media',
                'Media tahlil qilinmadi',
                'FFmpeg/FFprobe natijasi mavjud emas, shuning uchun vizual va audio signallar o‘lchanmadi.',
            )
        )

    if inputs.transcript and inputs.transcript.text:
        items.append(
            evidence(
                'transcript',
                EvidenceKind.VERIFIED_FACT,
                'Transkript',
                f'{len(inputs.transcript.text.split())} so‘z, til: {inputs.transcript.language} '
                f'({inputs.transcript.usage.provider}).',
                confidence=85,
            )
        )
    else:
        items.append(
            insufficient('transcript', 'Transkript yo‘q', 'Nutqdan matn olinmadi; matnga bog‘liq baholar cheklangan.')
        )

    if inputs.ocr and inputs.ocr.text:
        items.append(
            evidence('on_screen_text', EvidenceKind.VERIFIED_FACT, 'Ekrandagi matn',
                     f'OCR {len(inputs.ocr.blocks)} blok matn topdi.', confidence=80)
        )

    if prediction.basis == 'account_history':
        items.append(
            evidence(
                'prediction',
                EvidenceKind.ACCOUNT_HISTORY,
                'Akkaunt tarixi',
                f'O‘rtacha ko‘rish: {inputs.context.account.average_views}, eng yaxshi: {inputs.context.account.best_views}.',
                confidence=prediction.confidence,
                source_date=inputs.context.account.history_updated_on,
            )
        )
    else:
        items.append(insufficient('prediction', 'Tarix yetarli emas', prediction.note))

    items.append(
        evidence(
            'scoring',
            EvidenceKind.AI_INFERENCE,
            'Baholash modeli',
            (
                f'Viral score {scores.viral_score} — o‘lchangan signallar va akkaunt turi og‘irliklari '
                'asosidagi ehtimoliy baho, kafolat emas.'
            ),
            confidence=scores.confidence,
        )
    )
    if inputs.llm and inputs.llm.usage.mode == 'production':
        items.append(
            evidence(
                'narrative',
                EvidenceKind.AI_INFERENCE,
                'LLM tavsiyalari',
                f'Hook/script/CTA matnlari {inputs.llm.usage.provider} ({inputs.llm.usage.model}) tomonidan yozildi.',
                confidence=70,
            )
        )
    elif inputs.provider_mode == 'demo':
        items.append(
            evidence(
                'narrative',
                EvidenceKind.AI_INFERENCE,
                'Demo rejim',
                'Matnli tavsiyalar development demo shabloni; production’da LLM provayderi majburiy.',
                confidence=25,
            )
        )
    return items


# --------------------------------------------------------------------------- narrative
DEMO_HOOKS = [
    'Instagramda videolaringiz 1 000 ko‘rishdan o‘tmayaptimi? Asosiy sabab kontentda emas.',
    'Ko‘pchilik Reels’ni 5-soniyada yo‘qotadi — bu bitta xato sabab bo‘ladi.',
    'Video foydali bo‘lsa ham nega tomoshabin oxirigacha ko‘rmaydi?',
]
DEMO_SCRIPT = [
    '0–2s: natijani ko‘rsating va bitta og‘riqli savol bering.',
    '3–8s: muammoning sababini bitta gapda ayting.',
    '9–20s: 3 qadamni ekran yozuvi bilan ko‘rsating.',
    '21s–oxir: natijani takrorlang va bitta harakatga chorlang.',
]
DEMO_BRIEF = [
    '00:00–00:02: asosiy va’dani birinchi kadrga chiqaring; katta, yuqori kontrastli subtitr ishlating.',
    'Salomlashuv va takror gaplarni kesing; kadrni 2–3 soniyadan uzun ushlab turmang.',
    'Muhim so‘zlarni kattalashtiring va safe zone ichida saqlang.',
    'Dalil qismiga Insights yoki oldin-keyin B-roll qo‘shing.',
    'Oxirida faqat bitta CTA qoldiring va uni foyda bilan bog‘lang.',
]


def _measured_changes(inputs: ReportInputs) -> list[str]:
    changes: list[str] = []
    bundle = inputs.bundle
    if bundle:
        early = [w for w in bundle.silences if w.start_seconds < 5]
        if early:
            changes.append(
                f'Birinchi 5 soniyadagi {sum(w.duration_seconds for w in early):.1f}s jimlikni kesing.'
            )
        if bundle.scene_change_rate is not None and bundle.scene_change_rate < 0.1:
            changes.append('Vizual o‘zgarish tezligi past: har 2–3 soniyada kadr yoki plan almashtiring.')
        if bundle.probe.is_vertical is False:
            changes.append('Video vertikal emas: 9:16 formatga qayta kadrlang.')
        if not bundle.probe.has_audio:
            changes.append('Audio oqim yo‘q: ovoz yoki musiqa qo‘shing, aks holda retention keskin tushadi.')
    return changes


def narrative(inputs: ReportInputs) -> dict:
    """Return the human-readable part of the report.

    Production requires a real LLM answer; demo mode uses the labelled
    development template.
    """
    if inputs.llm and inputs.llm.usage.mode == 'production':
        content = inputs.llm.content
        return {
            'short_summary': str(content.get('short_summary', '')).strip(),
            'required_changes': [str(x) for x in content.get('required_changes', [])][:8]
            or _measured_changes(inputs),
            'improved_hooks': [str(x) for x in content.get('improved_hooks', [])][:6],
            'improved_script': [str(x) for x in content.get('improved_script', [])][:12],
            'improved_cta': str(content.get('improved_cta', '')).strip(),
            'editor_brief': [str(x) for x in content.get('editor_brief', [])][:12],
        }

    if settings.is_production:
        raise ProviderConfigurationError(
            'Production report requires an LLM provider response; demo narrative is disabled.'
        )
    if not settings.demo_providers_enabled:
        raise ProviderConfigurationError(
            'No LLM provider output and demo providers are disabled; refusing to fabricate a report.'
        )

    measured = _measured_changes(inputs)
    return {
        'short_summary': (
            'Demo rejim: matnli tavsiyalar shablondan olindi, o‘lchangan media signallari esa haqiqiy. '
            'Production’da bu qism LLM provayderi tomonidan yoziladi.'
        ),
        'required_changes': measured
        + [
            'Birinchi 1–2 soniyada natija yoki muammoni aniq ko‘rsating.',
            'Kontekstdagi takror gaplarni kesib, asosiy fikrga tezroq o‘ting.',
            'CTA’ni bitta aniq harakatga almashtiring.',
        ],
        'improved_hooks': DEMO_HOOKS,
        'improved_script': DEMO_SCRIPT,
        'improved_cta': 'Keyingi videongizni joylashdan oldin shu cheklist bo‘yicha tekshirib chiqing va saqlab qo‘ying.',
        'editor_brief': DEMO_BRIEF,
    }


# --------------------------------------------------------------------------- assembly
def build_media_summary(inputs: ReportInputs) -> MediaSummary:
    bundle = inputs.bundle
    if bundle is None:
        return MediaSummary(analysed=False)
    probe = bundle.probe
    thumbnails = [
        ThumbnailCandidate(
            timestamp_seconds=candidate.timestamp_seconds,
            storage_key=inputs.thumbnail_keys.get(candidate.timestamp_seconds),
            reason='Kadr detali va kontrasti bo‘yicha nomzod (o‘lchangan JPEG hajmi bo‘yicha tartiblangan).',
        )
        for candidate in bundle.thumbnails
    ]
    return MediaSummary(
        duration_seconds=probe.duration_seconds,
        width=probe.width,
        height=probe.height,
        aspect_ratio=probe.aspect_ratio,
        is_vertical=probe.is_vertical,
        video_codec=probe.video_codec,
        audio_codec=probe.audio_codec,
        has_audio=probe.has_audio,
        fps=probe.fps,
        scene_change_count=len(bundle.scene_changes),
        scene_change_rate=bundle.scene_change_rate,
        silence_seconds=bundle.silence_seconds,
        speech_ratio=bundle.speech_ratio,
        frame_count=len(bundle.frames),
        keyframe_count=len(bundle.keyframes),
        thumbnails=thumbnails,
        analysed=True,
    )


def build_report(inputs: ReportInputs) -> AnalysisReport:
    language = resolve_language(inputs.language or (inputs.context.language or inputs.context.account.language))
    context = inputs.context
    if inputs.transcript and inputs.transcript.text and not context.transcript:
        context = context.model_copy(update={'transcript': inputs.transcript.text[:10000]})
    if inputs.bundle:
        probe = inputs.bundle.probe
        context = context.model_copy(
            update={
                'duration_seconds': probe.duration_seconds or context.duration_seconds,
                'width': probe.width or context.width,
                'height': probe.height or context.height,
            }
        )

    scores = score(context, observed_signals(inputs))
    timeline = build_timeline(ReportInputs(**{**inputs.__dict__, 'context': context}), scores)
    segments = build_segments(inputs, timeline, scores)
    prediction = build_prediction(inputs, scores)
    text = narrative(inputs)

    return AnalysisReport(
        scores=scores,
        short_summary=text['short_summary'],
        required_changes=text['required_changes'],
        improved_hooks=text['improved_hooks'],
        improved_script=text['improved_script'],
        improved_cta=text['improved_cta'],
        editor_brief=text['editor_brief'],
        segments=segments,
        timeline=timeline,
        evidence=build_evidence(inputs, scores, prediction),
        prediction=prediction,
        media=build_media_summary(inputs),
        usage=ProviderUsageSummary(**inputs.usage.summary()),
        language=language,
        provider_mode=inputs.provider_mode,  # type: ignore[arg-type]
        generated_at=datetime.now(timezone.utc),
    )
