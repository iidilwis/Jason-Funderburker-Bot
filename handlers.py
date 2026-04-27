"""
Хендлери бота. Логіка: читає повідомлення → вирішує чи відповідати →
вибирає формат → генерує відповідь через Gemini або Pillow.
"""

import os
import random
import logging
import io
import httpx

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, InputFile, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command

import database as db
import brain
import meme_maker
from config import GEMINI_API_KEY

router = Router()
logger = logging.getLogger(__name__)


# ── Утиліти ──────────────────────────────────────────────────────────────────

async def download_file(bot: Bot, file_id: str) -> bytes | None:
    """Завантажує файл з Telegram за file_id."""
    try:
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, buf)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


async def save_image_as_template(bot: Bot, file_id: str):
    """Краде картинку з чату як шаблон для майбутніх мемів."""
    if db.get_template_count() >= 300:
        return
    data = await download_file(bot, file_id)
    if not data:
        return
    safe_id = file_id.replace("-", "_")[:40]
    path = os.path.join("templates", f"{safe_id}.jpg")
    try:
        with open(path, "wb") as f:
            f.write(data)
        db.save_template(file_id, path, source="chat")
        logger.info(f"Saved template: {path}")
    except Exception as e:
        logger.error(f"Template save error: {e}")


def get_message_context(msg: Message) -> str:
    """Збирає текстовий контекст з повідомлення."""
    parts = []
    if msg.caption:
        parts.append(msg.caption)
    if msg.text:
        parts.append(msg.text)
    if msg.forward_from_chat:
        parts.append(f"[Форвард з {msg.forward_from_chat.title}]")
    if msg.sticker:
        parts.append(f"[Стікер: {msg.sticker.emoji or '?'}]")
    return " ".join(parts).strip()


# ── Головна логіка відповіді ──────────────────────────────────────────────────

async def respond_to_message(
    message: Message,
    bot: Bot,
    is_channel_post: bool = False,
):
    """
    Вирішує що відповісти і відправляє. Серце бота.
    """
    chat_id = message.chat.id
    response_type = brain.pick_response_type()

    # Збираємо байти картинки якщо є
    image_bytes: bytes | None = None
    image_mime = "image/jpeg"
    if message.photo:
        best = max(message.photo, key=lambda p: p.file_size or 0)
        image_bytes = await download_file(bot, best.file_id)
    elif message.document and message.document.mime_type and \
            message.document.mime_type.startswith("image/"):
        image_bytes = await download_file(bot, message.document.file_id)
        image_mime = message.document.mime_type

    text_context = get_message_context(message)

    try:
        if response_type == "sticker":
            await _send_sticker(message, bot, chat_id)

        elif response_type == "poll":
            await _send_poll(message, bot, text_context, image_bytes, image_mime)

        elif response_type == "demotivator":
            await _send_demotivator(message, bot, chat_id, text_context, image_bytes, image_mime)

        elif response_type == "meme":
            await _send_meme(message, bot, chat_id, text_context, image_bytes, image_mime)

        else:  # text
            await _send_text(message, bot, text_context, image_bytes, image_mime)

    except Exception as e:
        logger.error(f"respond_to_message error ({response_type}): {e}")
        # Fallback — просто текст
        try:
            txt = await brain.call_gemini(GEMINI_API_KEY, text_context)
            if txt:
                await message.reply(txt)
        except Exception:
            pass


async def _send_sticker(message: Message, bot: Bot, chat_id: int):
    file_id = db.get_random_sticker(chat_id)
    if file_id:
        await message.reply_sticker(file_id)
    else:
        # Немає стікерів — fallback на текст
        txt = await brain.call_gemini(GEMINI_API_KEY, get_message_context(message))
        if txt:
            await message.reply(txt)


async def _send_poll(
    message: Message, bot: Bot,
    text_context: str,
    image_bytes: bytes | None,
    image_mime: str,
):
    topic = text_context or "щось важливе"
    result = await brain.generate_poll_options(GEMINI_API_KEY, topic[:200])
    if result:
        question, options = result
        if len(options) >= 2:
            await bot.send_poll(
                chat_id=message.chat.id,
                question=question,
                options=options,
                reply_to_message_id=message.message_id,
                is_anonymous=False,
            )
            return
    # Fallback
    txt = await brain.call_gemini(GEMINI_API_KEY, text_context, image_bytes, image_mime)
    if txt:
        await message.reply(txt)


async def _send_demotivator(
    message: Message, bot: Bot, chat_id: int,
    text_context: str,
    image_bytes: bytes | None,
    image_mime: str,
):
    # Беремо картинку: або з повідомлення, або рандомний шаблон
    img_data = image_bytes
    if not img_data:
        template = db.get_random_template()
        if template:
            try:
                with open(template["local_path"], "rb") as f:
                    img_data = f.read()
            except Exception:
                img_data = None

    if not img_data:
        # Зовсім нема картинок — відправляємо текст
        txt = await brain.call_gemini(GEMINI_API_KEY, text_context)
        if txt:
            await message.reply(txt)
        return

    # Генеруємо текст через Gemini
    meme_text = await brain.generate_meme_text(
        GEMINI_API_KEY, text_context, image_bytes, image_mime
    )
    if meme_text:
        title, subtitle = meme_text
    else:
        title = text_context[:60] if text_context else "..."
        subtitle = ""

    result_bytes = meme_maker.make_demotivator(img_data, title, subtitle)
    photo = BufferedInputFile(result_bytes, filename="demotivator.jpg")
    await message.reply_photo(photo)


async def _send_meme(
    message: Message, bot: Bot, chat_id: int,
    text_context: str,
    image_bytes: bytes | None,
    image_mime: str,
):
    img_data = image_bytes
    if not img_data:
        template = db.get_random_template()
        if template:
            try:
                with open(template["local_path"], "rb") as f:
                    img_data = f.read()
            except Exception:
                img_data = None

    if not img_data:
        txt = await brain.call_gemini(GEMINI_API_KEY, text_context)
        if txt:
            await message.reply(txt)
        return

    meme_text = await brain.generate_meme_text(
        GEMINI_API_KEY, text_context, image_bytes, image_mime
    )
    if meme_text:
        top, bottom = meme_text
    else:
        top, bottom = "", text_context[:50] if text_context else ""

    # Рандомно: або Impact мем, або колаж з ще однією рандомною картинкою
    if random.random() < 0.4:
        template2 = db.get_random_template()
        if template2:
            try:
                with open(template2["local_path"], "rb") as f:
                    img2 = f.read()
                result_bytes = meme_maker.make_collage([img_data, img2])
            except Exception:
                result_bytes = meme_maker.make_impact_meme(img_data, top, bottom)
        else:
            result_bytes = meme_maker.make_impact_meme(img_data, top, bottom)
    else:
        result_bytes = meme_maker.make_impact_meme(img_data, top, bottom)

    photo = BufferedInputFile(result_bytes, filename="meme.jpg")
    await message.reply_photo(photo)


async def _send_text(
    message: Message, bot: Bot,
    text_context: str,
    image_bytes: bytes | None,
    image_mime: str,
):
    txt = await brain.call_gemini(
        GEMINI_API_KEY, text_context, image_bytes, image_mime
    )
    if txt:
        await message.reply(txt)


# ── Хендлери повідомлень ─────────────────────────────────────────────────────

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message, bot: Bot):
    """Всі повідомлення в будь-якій групі де є бот."""

    # Зберігаємо повідомлення для навчання
    text = message.text or message.caption or ""
    if text and len(text) > 3 and not text.startswith("/"):
        db.save_message(message.chat.id, message.from_user.id if message.from_user else 0, text)

    # Зберігаємо стікери
    if message.sticker:
        db.save_sticker(message.chat.id, message.sticker.file_id)

    # Краємо картинки як шаблони (не всі, рандомно ~30%)
    if message.photo and random.random() < 0.3:
        best = max(message.photo, key=lambda p: p.file_size or 0)
        await save_image_as_template(bot, best.file_id)

    # Ігноруємо власні повідомлення
    if message.from_user and message.from_user.is_bot:
        return

    # Пост з каналу в коментах (forward_from_chat = канал)
    is_channel_post = bool(
        message.forward_from_chat and
        message.forward_from_chat.id != message.chat.id
    )

    if brain.should_reply(is_channel_post):
        await respond_to_message(message, bot, is_channel_post)


# ── Адмін-команди ─────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Показує стан бота."""
    chat_id = message.chat.id
    msgs = len(db.get_messages(chat_id, limit=9999))
    templates = db.get_template_count()
    await message.reply(
        f"📊 Стан жаби:\n"
        f"• Повідомлень вивчено: {msgs}\n"
        f"• Шаблонів мемів: {templates}\n"
        f"• Стан: alive і трохи confused"
    )


@router.message(Command("steal"))
async def cmd_steal(message: Message, bot: Bot):
    """Адмін-команда: вкрасти картинку як шаблон вручну."""
    if message.reply_to_message and message.reply_to_message.photo:
        best = max(message.reply_to_message.photo, key=lambda p: p.file_size or 0)
        await save_image_as_template(bot, best.file_id)
        await message.reply("вкрала 🐸")
    else:
        await message.reply("відповідай на картинку")
