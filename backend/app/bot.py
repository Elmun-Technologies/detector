"""Telegram entry point for the Viral Video AI MVP.

Run with:
    TELEGRAM_BOT_TOKEN=... python -m app.bot

For production, prefer a webhook behind HTTPS and replace the in-memory profile
store with the Users/Workspaces tables described in the product architecture.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from .config import settings
from .jobs import process_analysis
from .schemas import AccountProfile, VideoContext
from .store import analysis_store
from .video import VideoValidationError, probe_video, validate_upload

logger = logging.getLogger(__name__)
router = Router(name="viral-video-ai")

MENU_ANALYZE = "🎬 Videoni tahlil qilish"
MENU_IDEA = "💡 G‘oyani tekshirish"
MENU_PLAN = "🗓 Kontent-reja"
MENU_COMPETITORS = "👥 Raqobatchilar"
MENU_RESULTS = "📈 Natijalarim"
MENU_INSIGHTS = "✨ AI tavsiyalar"
MENU_PROFILE = "⚙️ Profil va sozlamalar"

user_profiles: dict[int, dict[str, str]] = {}


class Onboarding(StatesGroup):
    activity = State()
    objective = State()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MENU_ANALYZE), KeyboardButton(text=MENU_IDEA)],
            [KeyboardButton(text=MENU_PLAN), KeyboardButton(text=MENU_COMPETITORS)],
            [KeyboardButton(text=MENU_RESULTS), KeyboardButton(text=MENU_INSIGHTS)],
            [KeyboardButton(text=MENU_PROFILE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Bo‘limni tanlang yoki video yuboring",
    )


def activity_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ekspert blog"), KeyboardButton(text="Shaxsiy brend")],
            [KeyboardButton(text="Xizmat"), KeyboardButton(text="Mahsulot")],
            [KeyboardButton(text="Ta’lim"), KeyboardButton(text="Boshqa")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def objective_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ko‘rishlar va tanilish"), KeyboardButton(text="Obunachi o‘sishi")],
            [KeyboardButton(text="Lead va sotuv"), KeyboardButton(text="Save va share")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = message.from_user.first_name if message.from_user else "siz"
    await message.answer(
        f"Salom, {name}! ✦\n\n"
        "Men Viral Video AI — Reels’ingizni joylashdan oldin hook, retention, ssenariy va montaj signalini tekshiraman. "
        "Million ko‘rishni va’da qilmayman, ammo zaif joylarni vaqt kodi bilan ko‘rsataman.\n\n"
        "Boshlash uchun faoliyat yo‘nalishingizni tanlang.",
        reply_markup=activity_menu(),
    )
    await state.set_state(Onboarding.activity)


@router.message(Onboarding.activity)
async def collect_activity(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Iltimos, tugmalardan birini tanlang.")
        return
    await state.update_data(activity=message.text)
    await message.answer("Asosiy maqsadingiz nima?", reply_markup=objective_menu())
    await state.set_state(Onboarding.objective)


@router.message(Onboarding.objective)
async def collect_objective(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Iltimos, tugmalardan birini tanlang.")
        return
    data = await state.get_data()
    telegram_id = message.from_user.id if message.from_user else 0
    user_profiles[telegram_id] = {"activity": data.get("activity", "Boshqa"), "objective": message.text}
    await state.clear()
    await message.answer(
        "Tayyor! Siz uchun tavsiyalar faoliyat sohasi va maqsadingizga moslashtiriladi.\n\n"
        "🎬 Video yuboring yoki quyidagi bo‘limlardan birini tanlang.",
        reply_markup=main_menu(),
    )


@router.message(F.text == MENU_ANALYZE)
async def request_video(message: Message) -> None:
    await message.answer(
        "Videoni MP4, MOV yoki AVI formatida yuboring.\n\n"
        "Limit: 500 MB · 180 soniya · tavsiya: 9:16, 1080 × 1920.\n"
        "Istasangiz, xabarga video mavzusi va maqsadini ham yozing."
    )


@router.message(F.text == MENU_IDEA)
async def request_idea(message: Message) -> None:
    await message.answer(
        "G‘oyangizni bitta xabarda yuboring. Masalan:\n\n"
        "<i>2026-yilda O‘zbekistonda qaysi reklama kanallari ishlaydi?</i>\n\n"
        "Men potensial, optimal format, hook va fakt tekshirilishi kerak bo‘lgan joylarni chiqaraman.",
        parse_mode="HTML",
    )


@router.message(F.text.in_({MENU_PLAN, MENU_COMPETITORS, MENU_RESULTS, MENU_INSIGHTS, MENU_PROFILE}))
async def coming_soon_menu(message: Message) -> None:
    answers = {
        MENU_PLAN: "🗓 Oylik kontent-reja akkaunt tarixi va maqsadingiz asosida yaratiladi. Bu modul MVP’dan keyingi integratsiya bilan ochiladi.",
        MENU_COMPETITORS: "👥 Raqobatchi username’larini yuborishingiz mumkin. Ochiq kontent signallari asosida formatlar va kontent bo‘shliqlari ajratiladi.",
        MENU_RESULTS: "📈 Joylangan videolar uchun Insights’ni ulang yoki CSV yuklang. Shunda prognoz va real natija solishtiriladi.",
        MENU_INSIGHTS: "✨ AI tavsiyalar video, kontent tarixi va tasdiqlangan ma’lumotlarni ajratib ko‘rsatadi.",
        MENU_PROFILE: "⚙️ Profil konteksti keyingi versiyada to‘liq tahrirlanadi. Hozircha /start orqali onboarding’ni qayta boshlashingiz mumkin.",
    }
    await message.answer(answers[message.text])


async def _deliver_report(bot: Bot, chat_id: int, job_id: str) -> None:
    await process_analysis(job_id)
    job = analysis_store.get(job_id)
    if not job or not job.report:
        await bot.send_message(chat_id, "Tahlilni yakunlab bo‘lmadi. Iltimos, videoni qayta yuboring.")
        return
    report = job.report
    await bot.send_message(
        chat_id,
        "<b>AI tahlil tayyor ✦</b>\n\n"
        f"<b>Viral Score:</b> {report.scores.viral_score}/100\n"
        f"Hook: {report.scores.hook_score} · Retention: {report.scores.retention_score} · "
        f"Save: {report.scores.save_score}\n\n"
        f"<b>Qisqa xulosa</b>\n{report.short_summary}\n\n"
        "<b>Majburiy o‘zgarishlar</b>\n"
        + "\n".join(f"• {item}" for item in report.required_changes[:3])
        + f"\n\n<b>Yangi hook</b>\n<i>{report.improved_hooks[0]}</i>\n\n"
        f"<b>CTA</b>\n{report.improved_cta}\n\n"
        f"<i>{report.disclaimer}</i>",
        parse_mode="HTML",
    )


@router.message(F.video | F.document)
async def receive_video(message: Message, bot: Bot) -> None:
    attachment = message.video or message.document
    if attachment is None:
        return
    filename = getattr(attachment, "file_name", None) or "telegram-video.mp4"
    content_type = getattr(attachment, "mime_type", None)
    file_size = getattr(attachment, "file_size", 0) or 0

    try:
        validate_upload(filename, content_type, file_size, settings.max_upload_bytes)
    except VideoValidationError as error:
        await message.answer(f"⚠️ {error}")
        return

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    path = settings.uploads_dir / f"{uuid4()}-{Path(filename).name}"
    try:
        await bot.download(attachment, destination=path)
        metadata = probe_video(path)
        if metadata.duration_seconds and metadata.duration_seconds > settings.max_duration_seconds:
            path.unlink(missing_ok=True)
            await message.answer(f"⚠️ Video {settings.max_duration_seconds:g} soniyadan uzun bo‘lmasligi kerak.")
            return
    except Exception:
        logger.exception("Telegram file download failed")
        path.unlink(missing_ok=True)
        await message.answer("⚠️ Videoni yuklab bo‘lmadi. Iltimos, qayta urinib ko‘ring.")
        return

    profile = user_profiles.get(message.from_user.id if message.from_user else 0, {})
    context = VideoContext(
        title=Path(filename).stem,
        objective="reach",
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        account=AccountProfile(niche=profile.get("activity"), account_type="expert"),
    )
    job = analysis_store.create(context, filename)
    await message.answer(
        "🎬 Video qabul qilindi.\n\n"
        "1/5 Audio va kadrlar ajratilmoqda\n"
        "2/5 Hook va ssenariy signallari tekshiriladi\n"
        "3/5 Retention xaritasi tuziladi\n"
        "4/5 Viral Score hisoblanadi\n"
        "5/5 Shaxsiy hisobot tayyorlanadi"
    )
    asyncio.create_task(_deliver_report(bot, message.chat.id, job.id))


@router.message(F.text)
async def catch_text_as_idea(message: Message) -> None:
    text = message.text or ""
    if len(text.strip()) < 8:
        await message.answer("G‘oyani biroz batafsilroq yozing yoki menyudan bo‘lim tanlang.")
        return
    # Import locally so a plain /start path does not pull any optional model gateway.
    from .analyzer import check_idea

    result = check_idea(text, "reach")
    hooks = "\n".join(f"{index + 1}. {hook}" for index, hook in enumerate(result["hooks"][:3]))
    await message.answer(
        f"<b>G‘oya potensiali: {result['potential_score']}/100</b>\n"
        f"Auditoriya mosligi: {result['audience_fit']} · Save potensiali: {result['save_potential']}\n\n"
        f"<b>AI xulosasi</b>\n{result['improved_angle']}\n\n"
        f"<b>Hooklar</b>\n{hooks}\n\n"
        "<i>Bu baho kafolat emas. Faktli da’volarni ishonchli manba bilan tekshiring.</i>",
        parse_mode="HTML",
    )


async def run() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN topilmadi. Uni environment variable sifatida bering.")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(run())
