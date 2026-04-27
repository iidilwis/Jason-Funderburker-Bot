import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# ID групи-коментарів твого паблика
# Як дізнатись: додай @userinfobot в коменти і перешли йому будь-яке повідомлення
COMMENTS_GROUP_ID = int(os.getenv("COMMENTS_GROUP_ID", "0"))

# Шанс відповісти на коментар (рандом між мін і макс)
REPLY_CHANCE_MIN = 0.40
REPLY_CHANCE_MAX = 0.70

# На пости каналу — майже завжди
CHANNEL_POST_REPLY_CHANCE = 0.90

# Скільки зберігати шаблонів мемів
MAX_TEMPLATES = 300
