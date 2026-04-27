import sqlite3
import os

DB_PATH = "bot.db"
TEMPLATES_DIR = "templates"


def init_db():
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stickers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            file_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL UNIQUE,
            local_path TEXT,
            source TEXT DEFAULT 'chat'
        );
        """)


def save_message(chat_id: int, user_id: int, text: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, user_id, text) VALUES (?,?,?)",
            (chat_id, user_id, text)
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat_id,)
        ).fetchone()[0]
        if count > 3000:
            conn.execute("""
                DELETE FROM messages WHERE id IN (
                    SELECT id FROM messages WHERE chat_id=? ORDER BY id ASC LIMIT ?
                )
            """, (chat_id, count - 3000))


def get_messages(chat_id: int, limit: int = 300) -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT text FROM messages WHERE chat_id=? ORDER BY RANDOM() LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    return [r[0] for r in rows]


def save_sticker(chat_id: int, file_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stickers (chat_id, file_id) VALUES (?,?)",
            (chat_id, file_id)
        )


def get_random_sticker(chat_id: int) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT file_id FROM stickers WHERE chat_id=? ORDER BY RANDOM() LIMIT 1",
            (chat_id,)
        ).fetchone()
    return row[0] if row else None


def save_template(file_id: str, local_path: str, source: str = "chat"):
    from config import MAX_TEMPLATES
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO templates (file_id, local_path, source) VALUES (?,?,?)",
            (file_id, local_path, source)
        )
        count = conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
        if count > MAX_TEMPLATES:
            conn.execute("""
                DELETE FROM templates WHERE id IN (
                    SELECT id FROM templates ORDER BY id ASC LIMIT ?
                )
            """, (count - MAX_TEMPLATES,))


def get_random_template() -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT file_id, local_path FROM templates "
            "WHERE local_path IS NOT NULL ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    if row and os.path.exists(row[1]):
        return {"file_id": row[0], "local_path": row[1]}
    return None


def get_template_count() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
