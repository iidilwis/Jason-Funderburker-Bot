"""
Мозок бота — Gemini Flash аналізує контекст і генерує відповідь
в стилі маленького кавунчика: суржик, абсурд, іноді в тему
"""

import httpx
import base64
import json
import random
import logging
from database import get_messages

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)

# Системний промпт — характер жаби
SYSTEM_PROMPT = """Ти — жаба-бот в телеграм-каналі "Маленький кавунчик". 
Твій стиль: хаотичний мікс української, російської та англійської мови в одному реченні (суржик + інтернет-сленг).
Ти абсурдний, іронічний, іноді nihilistic, іноді ніжний.
Використовуй мат природньо але не часто. Емодзі — зрідка.

ПРАВИЛА:
- Відповідай ДУЖЕ коротко: 1-3 речення максимум
- 70% часу відповідай якось пов'язано з темою, 30% — повний рандомний абсурд
- Мікс мов в одному реченні це норма ("ну і що з того what can i say")
- Не пояснюй себе, не вибачайся, просто кажи
- Можеш посилатись на меми, аніме (особливо Євангеліон), пострадянський побут

Приклади твоїх відповідей:
- "ну це буквально я о 3 ночі wtf"
- "прогрес неможливий без страждань і піци"  
- "я б прокоментував але в мене дедлайн з існуванням"
- "це called being perceived і я проти"
- "хтось скажіть йому що так не можна або навпаки можна"
"""


async def call_gemini(
    api_key: str,
    text_context: str | None = None,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
) -> str | None:
    """Запит до Gemini Flash. Повертає текст відповіді або None."""

    parts = []

    if image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": image_mime,
                "data": base64.b64encode(image_bytes).decode()
            }
        })

    prompt = SYSTEM_PROMPT + "\n\n"
    if text_context:
        prompt += f"Контекст/повідомлення на яке треба відреагувати:\n{text_context}"
    else:
        prompt += "Скажи щось рандомне в своєму стилі."

    parts.append({"text": prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "maxOutputTokens": 150,
            "temperature": 1.1,
            "topP": 0.95,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                GEMINI_URL,
                params={"key": api_key},
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None


async def generate_poll_options(api_key: str, topic: str) -> tuple[str, list[str]] | None:
    """Генерує питання і варіанти для опитування."""
    prompt = (
        SYSTEM_PROMPT
        + f"\n\nСтвори опитування на тему: '{topic}'\n"
        "Відповідай ТІЛЬКИ у форматі JSON:\n"
        '{"question": "...", "options": ["...", "...", "...", "..."]}\n'
        "Питання макс 90 символів, кожен варіант макс 80 символів."
    )

    payload = {
    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "contents": [{"role": "user", "parts": [{"text": f"Створи опитування на тему: '{topic}'\nВідповідай ТІЛЬКИ у форматі JSON:\n" + '{"question": "...", "options": ["...", "...", "...", "..."]}\nПитання макс 90 символів, кожен варіант макс 80 символів.'}]}],
    "generationConfig": {"maxOutputTokens": 200, "temperature": 1.2}
}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                GEMINI_URL, params={"key": api_key}, json=payload
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            # Витягуємо JSON з відповіді
            raw = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(raw)
            return data["question"][:90], [o[:80] for o in data["options"][:4]]
    except Exception as e:
        logger.error(f"Poll generation error: {e}")
        return None


async def generate_meme_text(
    api_key: str,
    context: str | None = None,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
) -> tuple[str, str] | None:
    """Генерує текст для мему (верх і низ)."""

    parts = []
    if image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": image_mime,
                "data": base64.b64encode(image_bytes).decode()
            }
        })

    prompt = (
        SYSTEM_PROMPT
        + "\n\nСтвори підпис для мему. "
    )
    if context:
        prompt += f"Контекст: {context}\n"
    meme_prompt = "Створи підпис для мему. "
    if context:
        meme_prompt += f"Контекст: {context}\n"
    meme_prompt += 'Відповідай ТІЛЬКИ у форматі JSON:\n{"top": "текст зверху", "bottom": "текст знизу"}\nКожен рядок макс 50 символів.'
    parts.append({"text": meme_prompt})

    payload = {
    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "contents": [{"role": "user", "parts": parts}],
    "generationConfig": {"maxOutputTokens": 100, "temperature": 1.3}
}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                GEMINI_URL, params={"key": api_key}, json=payload
            )
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            raw = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(raw)
            return data.get("top", ""), data.get("bottom", "")
    except Exception as e:
        logger.error(f"Meme text error: {e}")
        return None


def should_reply(is_channel_post: bool = False) -> bool:
    """Вирішує чи відповідати на це повідомлення."""
    from config import (
        REPLY_CHANCE_MIN, REPLY_CHANCE_MAX, CHANNEL_POST_REPLY_CHANCE
    )
    if is_channel_post:
        return random.random() < CHANNEL_POST_REPLY_CHANCE
    chance = random.uniform(REPLY_CHANCE_MIN, REPLY_CHANCE_MAX)
    return random.random() < chance


def pick_response_type() -> str:
    """Рандомно вибирає формат відповіді."""
    choices = [
        ("text", 35),        # просто текст — найчастіше
        ("demotivator", 20), # демотиватор
        ("meme", 20),        # мем з картинкою
        ("sticker", 15),     # стікер
        ("poll", 10),        # опитування
    ]
    types, weights = zip(*choices)
    return random.choices(types, weights=weights, k=1)[0]
