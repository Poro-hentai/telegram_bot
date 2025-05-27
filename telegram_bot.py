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

# Globals
pattern = "{original}"
file_counter = 0
user_thumbnail = None
auto_rename = False

# Flask app to keep Render alive
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def extract_episode(filename):
    match = re.search(r"[Ee]p?(\d{1,3})", filename)
    return f"Episode {match.group(1)}" if match else None

def generate_filename(original_name):
    global file_counter, pattern, auto_rename
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp4"

    if auto_rename:
        episode = extract_episode(base)
        if episode:
            return f"{episode}{ext}"

    new_name = pattern.replace("{number}", str(file_counter)).replace("{original}", base)
    return f"{new_name}{ext}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to the File Renamer Bot!*\n\n"
        "Send a file and it'll be renamed automatically.\n\n"
        "📌 *Commands:*\n"
        "`/setpattern pattern` - Set rename pattern (use `{number}` and `{original}`)\n"
        "`/autorename` - Use episode number as filename\n"
        "`/reset` - Reset counter & disable autorename\n"
        "`/setthumb` - Send an image (jpg/png) to use as thumbnail\n",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Rename pattern set to: `{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Usage: /setpattern newname_{number}_{original}")

async def autorename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_rename
    auto_rename = True
    await update.message.reply_text("✅ Autorename enabled. Episode number will be used if found.")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter, auto_rename
    file_counter = 0
    auto_rename = False
    await update.message.reply_text("🔁 Counter reset and autorename disabled.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Thumbnail has been set successfully!")
    else:
        await update.message.reply_text("⚠️ Please send a JPG/PNG image.")

def is_video_file(file_name):
    return file_name.lower().endswith(('.mp4', '.mkv', '.mov'))

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        file = message.document or message.video
        if not file:
            return

        await message.reply_text("📥 Downloading...")

        telegram_file = await file.get_file()
        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)
        local_path = f"{uuid.uuid4().hex}_{original_name}"
        await telegram_file.download_to_drive(local_path)

        caption = f"`{new_name}`"
        thumb = None

        if user_thumbnail and is_video_file(original_name):
            thumb = open(user_thumbnail, "rb")
        elif hasattr(file, 'thumb') and file.thumb:
            thumb_file = await file.thumb.get_file()
            thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
            await thumb_file.download_to_drive(thumb_path)
            thumb = open(thumb_path, "rb")

        if is_video_file(original_name):
            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumb=thumb,
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption,
                parse_mode="Markdown"
            )

        await message.reply_text(f"✅ Renamed to: `{new_name}`", parse_mode="Markdown")
        os.remove(local_path)
        if thumb and not thumb.closed:
            thumb.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Error while handling file: {e}")

# --- MAIN ---
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()

    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"  # <- Replace this with your real bot token
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
