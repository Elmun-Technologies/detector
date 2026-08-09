from __future__ import annotations

from .schemas import AnalysisReport, Evidence, Segment, VideoContext
from .scoring import score


def _timeline(duration: float, retention_score: int, hook_score: int, cta_score: int) -> list[Segment]:
    """Create an explainable first-pass timeline.

    A real Vision/Audio worker should overwrite these signals once frame and
    transcript features are available. This fallback labels itself as a
    prediction rather than claiming that a drop-off was observed.
    """
    end = max(8.0, min(duration, 180.0))
    early_end = min(3.0, end)
    setup_end = min(max(5.0, end * 0.18), end)
    middle_end = min(max(10.0, end * 0.52), end)
    proof_end = min(max(16.0, end * 0.78), end)

    segments = [
        Segment(
            start_time=0,
            end_time=round(early_end, 1),
            title="Hook signali",
            state="strong" if hook_score >= 74 else "risk",
            retention_probability=hook_score,
            issue="Birinchi 1–3 soniyada va’da yoki muammo tez anglashilishi kerak.",
            recommendation="Natija, muammo yoki qarama-qarshilikni birinchi kadr va birinchi subtitrga olib chiqing.",
        ),
        Segment(
            start_time=round(early_end, 1),
            end_time=round(setup_end, 1),
            title="Kontekst",
            state="good" if retention_score >= 65 else "risk",
            retention_probability=max(0, retention_score - 3),
            issue="Kontekst cho‘zilsa, tomoshabin asosiy foydaga yetmasdan chiqib ketishi mumkin.",
            recommendation="Salomlashuv va takror gaplarni kesing; asosiy qiymatga bir gap bilan o‘ting.",
        ),
        Segment(
            start_time=round(setup_end, 1),
            end_time=round(middle_end, 1),
            title="Asosiy qiymat",
            state="good",
            retention_probability=max(0, retention_score - 7),
            issue="Bu qismda vizual yangilanish va qisqa fikrlar retentionni ushlab turadi.",
            recommendation="Har 2–3 soniyada B-roll, zoom, ekran yozuvi yoki subtitr urg‘usini almashtiring.",
        ),
        Segment(
            start_time=round(middle_end, 1),
            end_time=round(proof_end, 1),
            title="Dalil yoki misol",
            state="strong" if retention_score >= 64 else "risk",
            retention_probability=max(0, retention_score - 2),
            issue="Amaliy misol ishonchni oshiradi; u bo‘lmasa foyda umumiy ko‘rinib qolishi mumkin.",
            recommendation="Natija, oldin-keyin, screenshot yoki aniq misolni shu yerga joylashtiring.",
        ),
        Segment(
            start_time=round(proof_end, 1),
            end_time=round(end, 1),
            title="CTA",
            state="strong" if cta_score >= 72 else "risk",
            retention_probability=max(0, cta_score - 3),
            issue="Umumiy CTA video mazmuni bilan bog‘lanmasa, keyingi harakat ehtimoli past bo‘ladi.",
            recommendation="Faqat bitta harakatni so‘rang va foydalanuvchiga uni bajarish sababini bering.",
        ),
    ]
    return [segment for segment in segments if segment.end_time > segment.start_time]


def generate_report(context: VideoContext) -> AnalysisReport:
    scores = score(context)
    duration = context.duration_seconds or 34.0
    has_transcript = bool(context.transcript)
    has_account_history = context.account.average_views is not None

    strengths: list[str] = []
    if scores.hook_score >= 74:
        strengths.append("hook signali")
    if scores.save_score >= 72:
        strengths.append("saqlab olish potensiali")
    if scores.clarity_score >= 72:
        strengths.append("fikrning aniqligi")

    if strengths:
        strengths_text = ", ".join(strengths)
        short_summary = f"Dastlabki bahoda {strengths_text} kuchli ko‘rinadi. "
    else:
        short_summary = "Dastlabki bahoda video signallari aralash ko‘rinadi. "

    if scores.retention_score < 66:
        short_summary += "Retention ehtimolini oshirish uchun intro va kontekstni qisqartirib, vizual o‘zgarishni tezlashtiring."
    else:
        short_summary += "Kontekst va asosiy foydani qisqa bo‘laklarda saqlasangiz, retention signalini himoya qilasiz."

    required_changes = [
        "Birinchi 1–2 soniyada natija yoki muammoni aniq ko‘rsating.",
        "Kontekstdagi takror gap va pauzalarni kesib, asosiy fikrga tezroq o‘ting.",
        "Har 2–3 soniyada kamida bitta vizual o‘zgarish: B-roll, ekran yozuvi, zoom yoki kadr almashuvi qo‘shing.",
        "CTA’ni bitta aniq harakatga almashtiring: mazmun cheklist bo‘lsa, “saqlab qo‘ying” tabiiyroq bo‘ladi.",
    ]
    improved_hooks = [
        "Instagramda videolaringiz 1 000 ko‘rishdan o‘tmayaptimi? Asosiy sabab kontentda emas.",
        "Ko‘pchilik Reels’ni 5-soniyada yo‘qotadi — bu bitta xato sabab bo‘ladi.",
        "Video foydali bo‘lsa ham nega tomoshabin oxirigacha ko‘rmaydi?",
        "Retentionni oshirish uchun videongizdan olib tashlashingiz kerak bo‘lgan 3 narsa bor.",
    ]
    improved_cta = "Keyingi videongizni joylashdan oldin shu cheklist bo‘yicha tekshirib chiqing va saqlab qo‘ying."
    editor_brief = [
        "00:00–00:02: coverdagi asosiy va’dani birinchi kadrga chiqaring; katta, yuqori kontrastli subtitr ishlating.",
        "00:03–00:08: salomlashuv va takror gaplarni kesing; kadrni 2–3 soniyadan uzun ushlab turmang.",
        "Asosiy qiymat qismida muhim so‘zlarni kattalashtiring va safe zone ichida saqlang.",
        "Dalil qismiga Insights, case natijasi yoki oldin-keyin B-roll qo‘shing.",
        "Oxirida faqat bitta CTA qoldiring va uni foyda bilan bog‘lang.",
    ]

    evidence = [
        Evidence(
            kind="ai_inference",
            label="Dastlabki scoring",
            detail="Score video konteksti, ssenariy matni va ochiq scoring og‘irliklaridan hisoblandi.",
        ),
        Evidence(
            kind="ai_inference" if has_transcript else "insufficient_data",
            label="Nutq va ssenariy",
            detail="Transkript tahlil uchun berildi." if has_transcript else "Transkript berilmagan; nutq tezligi, pauza va aniq gaplarni tasdiqlash uchun STT kerak.",
        ),
        Evidence(
            kind="account_history" if has_account_history else "insufficient_data",
            label="Akkaunt benchmarki",
            detail=(
                f"O‘rtacha ko‘rishlar: {context.account.average_views:,}. Ushbu qiymat individual benchmark sifatida ishlatilishi mumkin."
                if has_account_history
                else "Akkauntning avvalgi Insights ma’lumoti berilmagan; prognoz umumiy signallarga tayangan."
            ),
        ),
    ]

    return AnalysisReport(
        scores=scores,
        short_summary=short_summary,
        required_changes=required_changes,
        improved_hooks=improved_hooks,
        improved_cta=improved_cta,
        editor_brief=editor_brief,
        segments=_timeline(duration, scores.retention_score, scores.hook_score, scores.cta_score),
        evidence=evidence,
    )


def check_idea(idea: str, objective: str) -> dict:
    text = idea.lower()
    specificity = min(18, len(text.split()) * 2)
    timely = 8 if any(token in text for token in ("2026", "bugun", "yangi", "trend")) else 0
    utility = 14 if any(token in text for token in ("qaysi", "qanday", "3", "5", "narx", "kanal", "formula")) else 4
    potential = max(45, min(94, 52 + specificity + timely + utility))
    save_potential = max(45, min(93, 53 + utility + (10 if objective == "save" else 0)))
    audience_fit = max(48, min(92, 62 + specificity))
    novelty = max(45, min(88, 58 + timely + (7 if "o‘zbekiston" in text or "o'zbekiston" in text else 0)))

    return {
        "potential_score": potential,
        "audience_fit": audience_fit,
        "save_potential": save_potential,
        "novelty": novelty,
        "competition": "medium" if novelty >= 65 else "high",
        "optimal_duration_seconds": (30, 45),
        "improved_angle": "Mavzuni aniq auditoriya, budget yoki real case bilan toraytiring — bu uni umumiy maslahatdan amaliy qarorga aylantiradi.",
        "hooks": [
            "2026’da reklama budgetini shu 3 kanalda sarflamasangiz, kech qolishingiz mumkin.",
            "Hamma bu kanal ishlamaydi deyapti. Raqamlar esa boshqa narsani ko‘rsatmoqda.",
            "Kichik biznes uchun eng foydali reklama kanali — ko‘pchilik o‘ylagan kanal emas.",
            "$100 budget bilan qaysi kanal real mijoz olib keladi?",
            "Reklama kanalini tanlashda ko‘pchilik aynan shu bitta xatoga yo‘l qo‘yadi.",
        ],
        "fact_check_needed": [
            "Reklama kanallari bo‘yicha da’volarni 2026-yilga tegishli rasmiy yoki ishonchli manba bilan tekshiring.",
            "Narx, CPM/CPC va ROI raqamlarini niche, hudud va davr bilan birga ko‘rsating.",
            "“Eng yaxshi” kabi umumiy fikrni fakt emas, sharoitga bog‘liq ekspert xulosasi sifatida belgilang.",
        ],
        "disclaimer": "G‘oya bahosi kafolat emas. Trend, raqobat va auditoriya qiziqishi vaqt o‘tishi bilan o‘zgaradi; faktli da’volar alohida manba bilan tekshirilishi kerak.",
    }
