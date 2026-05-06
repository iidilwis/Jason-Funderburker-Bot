import os
import random
import logging
import io

from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command

import database as db
import brain
import meme_maker
from config import GEMINI_API_KEY

router = Router()
logger = logging.getLogger(__name__)


async def download_file(bot: Bot, file_id: str) -> bytes | None:
    try:
        file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, buf)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


async def save_image_as_template(bot: Bot, file_id: str):
    if db.get_template_count() >= 300:
        return
    data = await download_file(bot, file_id)
    if not data:
        return
    safe_id = file_id.replace("-", "_")[:40]
    os.makedirs("templates", exist_ok=True)
    path = os.path.join("templates", f"{safe_id}.jpg")
    try:
        with open(path, "wb") as f:
            f.write(data)
        db.save_template(file_id, path, source="chat")
        logger.info(f"Saved template: {path}")
    except Exception as e:
        logger.error(f"Template save error: {e}")


def get_context(msg: Message) -> str:
    parts = []
    if msg.caption:
        parts.append(msg.caption)
    if msg.text:
        parts.append(msg.text)
    if msg.sticker:
        parts.append(f"стікер {msg.sticker.emoji or ''}")
    return " ".join(parts).strip()


async def safe_text(context: str, image_bytes=None, image_mime="image/jpeg") -> str:
    """Завжди повертає рядок — Gemini або fallback."""
    try:
        result = await brain.call_gemini(GEMINI_API_KEY, context, image_bytes, image_mime)
        if result:
            return result
    except Exception as e:
        logger.error(f"Gemini error: {e}")
    return brain.get_fallback()


async def get_any_image(bot: Bot, message: Message) -> bytes | None:
    """Бере картинку з повідомлення або рандомний шаблон."""
    # Спочатку рандомний шаблон щоб не відповідати тією ж картинкою
    tmpl = db.get_random_template()
    if tmpl:
        try:
            with open(tmpl["local_path"], "rb") as f:
                return f.read()
        except Exception:
            pass
    # Якщо шаблонів нема — картинка з повідомлення
    if message.photo:
        best = max(message.photo, key=lambda p: p.file_size or 0)
        return await download_file(bot, best.file_id)
    return None


async def respond(message: Message, bot: Bot):
    chat_id = message.chat.id
    rtype = brain.pick_response_type()
    context = get_context(message)

    image_bytes = None
    image_mime = "image/jpeg"
    if message.photo:
        best = max(message.photo, key=lambda p: p.file_size or 0)
        image_bytes = await download_file(bot, best.file_id)

    try:
        if rtype == "sticker":
            fid = db.get_random_sticker(chat_id)
            if fid:
                try:
                    await message.reply_sticker(fid)
                    return
                except Exception:
                    pass
            # fallthrough до тексту

        elif rtype == "gif":
            fid = db.get_random_gif(chat_id)
            if fid:
                try:
                    await message.reply_animation(fid)
                    return
                except Exception:
                    pass
            # fallthrough до тексту

        elif rtype == "poll":
            result = await brain.generate_poll_options(GEMINI_API_KEY, context or "щось важливе")
            if result:
                q, opts = result
                if len(opts) >= 2:
                    await bot.send_poll(
                        chat_id=chat_id,
                        question=q,
                        options=opts,
                        reply_to_message_id=message.message_id,
                        is_anonymous=False,
                    )
                    return
            # fallthrough до тексту

        elif rtype == "demotivator":
            img = await get_any_image(bot, message)
            if img:
                # Текст — Gemini або fallback, не блокуємо
                mt = None
                try:
                    mt = await brain.generate_meme_text(GEMINI_API_KEY, context, image_bytes, image_mime)
                except Exception:
                    pass
                title = (mt[0] or mt[1]) if mt and (mt[0] or mt[1]) else brain.get_fallback()
                subtitle = (mt[1] if mt and mt[0] else "") or ""
                result_bytes = meme_maker.make_demotivator(img, title, subtitle)
                await message.reply_photo(BufferedInputFile(result_bytes, "demotivator.jpg"))
                return
            # fallthrough до тексту

        elif rtype == "meme":
            img = await get_any_image(bot, message)
            if img:
                mt = None
                try:
                    mt = await brain.generate_meme_text(GEMINI_API_KEY, context, image_bytes, image_mime)
                except Exception:
                    pass
                top = mt[0] if mt else ""
                bottom = mt[1] if mt else brain.get_fallback()

                # Колаж якщо є другий шаблон
                if random.random() < 0.4:
                    tmpl2 = db.get_random_template()
                    if tmpl2:
                        try:
                            with open(tmpl2["local_path"], "rb") as f:
                                img2 = f.read()
                            result_bytes = meme_maker.make_collage([img, img2])
                            await message.reply_photo(BufferedInputFile(result_bytes, "meme.jpg"))
                            return
                        except Exception:
                            pass
                result_bytes = meme_maker.make_impact_meme(img, top, bottom)
                await message.reply_photo(BufferedInputFile(result_bytes, "meme.jpg"))
                return
            # fallthrough до тексту

        # Текст — завжди спрацює
        txt = await safe_text(context, image_bytes, image_mime)
        await message.reply(txt)

    except Exception as e:
        logger.error(f"respond error ({rtype}): {e}")
        try:
            await message.reply(brain.get_fallback())
        except Exception:
            pass


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group(message: Message, bot: Bot):
    text = message.text or message.caption or ""
    if text and len(text) > 3 and not text.startswith("/"):
        db.save_message(
            message.chat.id,
            message.from_user.id if message.from_user else 0,
            text
        )

    if message.sticker:
        db.save_sticker(message.chat.id, message.sticker.file_id)

    if message.animation:
        db.save_gif(message.chat.id, message.animation.file_id)

    # Краде кожну картинку (100% поки шаблонів < 20, потім 30%)
    if message.photo:
        threshold = 1.0 if db.get_template_count() < 20 else 0.3
        if random.random() < threshold:
            best = max(message.photo, key=lambda p: p.file_size or 0)
            await save_image_as_template(bot, best.file_id)

    if message.from_user and message.from_user.is_bot:
        return

    is_channel = bool(message.forward_from_chat)
    if brain.should_reply(is_channel):
        await respond(message, bot)


@router.message(Command("status"))
async def cmd_status(message: Message):
    chat_id = message.chat.id
    msgs = len(db.get_messages(chat_id, limit=9999))
    templates = db.get_template_count()
    await message.reply(
        f"🐸 стан жаби:\n"
        f"• повідомлень: {msgs}\n"
        f"• шаблонів мемів: {templates}\n"
        f"• жива: так, але втомлена"
    )


@router.message(Command("steal"))
async def cmd_steal(message: Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.photo:
        best = max(message.reply_to_message.photo, key=lambda p: p.file_size or 0)
        await save_image_as_template(bot, best.file_id)
        await message.reply("вкрала 🐸")
    else:
        await message.reply("відповідай на картинку")
