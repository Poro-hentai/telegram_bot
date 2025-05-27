import os
import re
import uuid
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

pattern = "{original}"
file_counter = 0
auto_rename = False
user_thumbnail = None

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def extract_episode(filename):
    match = re.search(r"[eE]p?\.?\s?(\d{1,3})", filename)
    return match.group(1) if match else None

def generate_filename(original_name):
    global file_counter, pattern, auto_rename
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp4"

    if auto_rename:
        episode = extract_episode(base)
        if episode:
            return pattern.replace("{episode}", episode) + ext

    new_name = pattern.replace("{number}", str(file_counter)).replace("{original}", base)
    return f"{new_name}{ext}"

def is_video_file(name):
    return name.lower().endswith(('.mp4', '.mkv', '.mov'))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "Send any file (PDF, video, etc.) and I will rename it.\n\n"
        "*Commands:*\n"
        "`/setpattern` - Set rename pattern using `{number}`, `{original}`, `{episode}`\n"
        "`/autorename` - Rename using episode number\n"
        "`/reset` - Reset counter and disable autorename\n"
        "`/setthumb` - Send JPG/PNG to use as video thumbnail",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Pattern set to: {pattern}")
    else:
        await update.message.reply_text("❗ Usage: /setpattern Series S01 - {episode}")

async def autorename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_rename
    auto_rename = True
    await update.message.reply_text("✅ Autorename enabled. Using episode numbers.")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter, auto_rename
    file_counter = 0
    auto_rename = False
    await update.message.reply_text("🔄 Counter reset and autorename disabled.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Default thumbnail saved for videos.")
    else:
        await update.message.reply_text("❗ Please send a JPG or PNG image.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        file = message.document or message.video
        if not file:
            return

        await message.reply_text("⬇️ Downloading...")

        tg_file = await file.get_file()
        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)
        local_path = f"{uuid.uuid4().hex}_{original_name}"
        await tg_file.download_to_drive(local_path)

        caption = new_name
        thumb = None

        if is_video_file(original_name):
            if hasattr(file, 'thumb') and file.thumb:
                tg_thumb = await file.thumb.get_file()
                thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
                await tg_thumb.download_to_drive(thumb_path)
                thumb = open(thumb_path, "rb")
            elif user_thumbnail:
                thumb = open(user_thumbnail, "rb")

            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumb=thumb if thumb else None
            )
        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption
            )

        await message.reply_text(f"✅ Renamed to: {new_name}")
        os.remove(local_path)
        if thumb and not thumb.closed:
            thumb.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()

    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("autorename", autorename))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, set_thumbnail))

    print("🚀 Bot is running...")
    app.run_polling()
