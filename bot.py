import telebot
from telebot import types
import sqlite3
import threading
import json

# ================= CONFIGURATION =================
BOT_TOKEN = "Your Bot Token"
BOT_USERNAME = "Username"
ADMIN_ID = 

CHANNEL_1_ID = "Channel"
CHANNEL_1_LINK = "link"

CHANNEL_2_ID = -
CHANNEL_2_LINK = "link"
# =================================================

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def get_db():
    return sqlite3.connect("files.db", timeout=15)

# Database Tables Setup
with get_db() as conn:
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_type TEXT,
        caption TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS albums (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        media_data TEXT,
        caption TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS join_requests (
        user_id INTEGER,
        chat_id INTEGER,
        PRIMARY KEY (user_id, chat_id)
    )
    """)
    conn.commit()

album_storage = {}
album_timers = {}

def process_album_upload(media_group_id, chat_id):
    messages = album_storage.pop(media_group_id, [])
    album_timers.pop(media_group_id, None)
    if not messages:
        return

    media_items = []
    album_caption = ""

    for m in messages:
        if m.caption and not album_caption:
            album_caption = m.caption
        if m.photo:
            media_items.append({"type": "photo", "file_id": m.photo[-1].file_id})
        elif m.video:
            media_items.append({"type": "video", "file_id": m.video.file_id})

    if not media_items:
        return

    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO albums (media_data, caption) VALUES (?, ?)", (json.dumps(media_items), album_caption))
        conn.commit()
        album_id = c.lastrowid

    share_link = f"https://t.me/{BOT_USERNAME}?start=album_{album_id}"
    bot.send_message(
        chat_id,
        f"✅ **Album Saved! ({len(media_items)} Media)**\n\n🔗 **Link:**\n`{share_link}`",
        parse_mode="Markdown"
    )

@bot.chat_join_request_handler()
def handle_join_request(request):
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO join_requests (user_id, chat_id) VALUES (?, ?)", 
                (request.from_user.id, request.chat.id)
            )
            conn.commit()
    except Exception as e:
        print(f"DB Error: {e}")

def is_joined_channel_1(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_1_ID, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

def is_requested_channel_2(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_2_ID, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
    except Exception:
        pass

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM join_requests WHERE user_id = ? AND chat_id = ?", (user_id, CHANNEL_2_ID))
            return c.fetchone() is not None
    except Exception:
        return False

@bot.message_handler(commands=['start'])
def start_handler(message):
    try:
        user_id = message.from_user.id
        text = message.text.strip()
        args = text.split()[1] if len(text.split()) > 1 else None

        if not args or not (args.startswith("file_") or args.startswith("album_")):
            bot.reply_to(message, "👋 Welcome to RCX File Store Bot!")
            return

        ch1_joined = is_joined_channel_1(user_id)
        ch2_requested = is_requested_channel_2(user_id)

        if not ch1_joined or not ch2_requested:
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("📢 1. Join Public Channel", url=CHANNEL_1_LINK),
                types.InlineKeyboardButton("🔒 2. Request Private Channel", url=CHANNEL_2_LINK),
                types.InlineKeyboardButton("🔄 Verified / Download", url=f"https://t.me/{BOT_USERNAME}?start={args}")
            )
            status_text = (
                "⛔ **ACCESS DENIED!**\n\n"
                "File download karne ke liye dono task complete karein:\n\n"
                f"{'✅' if ch1_joined else '❌'} **Task 1:** Public Channel ko **JOIN** karein.\n"
                f"{'✅' if ch2_requested else '❌'} **Task 2:** Private Channel me **REQUEST** bhejein.\n\n"
                "⚠️ Ek bhi channel chhootne par file nahi milegi!\n"
                "Dono complete karke **'Verified / Download'** dabayein."
            )
            bot.send_message(user_id, status_text, reply_markup=markup, parse_mode="Markdown")
            return

        if args.startswith("album_"):
            album_id = args.replace("album_", "")
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT media_data, caption FROM albums WHERE id = ?", (album_id,))
                row = c.fetchone()

            if row:
                media_items = json.loads(row[0])
                custom_caption = row[1] if row[1] else "Downloaded from RCX Family 👑"

                media_group = []
                for idx, item in enumerate(media_items):
                    cap = custom_caption if idx == 0 else None
                    if item["type"] == "photo":
                        media_group.append(types.InputMediaPhoto(item["file_id"], caption=cap))
                    elif item["type"] == "video":
                        media_group.append(types.InputMediaVideo(item["file_id"], caption=cap))

                for i in range(0, len(media_group), 10):
                    bot.send_media_group(user_id, media_group[i:i+10])
            else:
                bot.send_message(user_id, "❌ File expire ho chuki hai ya galat link hai.")
            return

        if args.startswith("file_"):
            file_db_id = args.replace("file_", "")
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT file_id, file_type, caption FROM files WHERE id = ?", (file_db_id,))
                row = c.fetchone()

            if row:
                file_id, file_type, caption = row
                caption_text = caption if caption else "Downloaded from RCX Family 👑"
                if file_type == 'document':
                    bot.send_document(user_id, file_id, caption=caption_text)
                elif file_type == 'video':
                    bot.send_video(user_id, file_id, caption=caption_text)
                elif file_type == 'audio':
                    bot.send_audio(user_id, file_id, caption=caption_text)
                elif file_type == 'photo':
                    bot.send_photo(user_id, file_id, caption=caption_text)
            else:
                bot.send_message(user_id, "❌ File expire ho chuki hai ya galat link hai.")
    except Exception as e:
        print(f"Start Error: {e}")

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo'])
def save_file_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        if message.media_group_id:
            mg_id = message.media_group_id
            if mg_id not in album_storage:
                album_storage[mg_id] = []
            album_storage[mg_id].append(message)

            if mg_id in album_timers:
                album_timers[mg_id].cancel()

            timer = threading.Timer(1.5, process_album_upload, args=[mg_id, message.chat.id])
            album_timers[mg_id] = timer
            timer.start()
            return

        file_id = ""
        file_type = ""
        caption = message.caption or ""

        if message.document:
            file_id = message.document.file_id
            file_type = "document"
        elif message.video:
            file_id = message.video.file_id
            file_type = "video"
        elif message.audio:
            file_id = message.audio.file_id
            file_type = "audio"
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"

        with get_db() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO files (file_id, file_type, caption) VALUES (?, ?, ?)", (file_id, file_type, caption))
            conn.commit()
            file_db_id = c.lastrowid

        share_link = f"https://t.me/{BOT_USERNAME}?start=file_{file_db_id}"
        bot.reply_to(message, f"✅ **File Saved!**\n\n🔗 **Link:**\n`{share_link}`", parse_mode="Markdown")
    except Exception as e:
        print(f"Save Error: {e}")

print("⚡ Bot is running strictly (Stable Mode)...")
bot.infinity_polling(timeout=20, long_polling_timeout=20)
