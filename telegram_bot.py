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

# Flask app for hosting
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Filename Generation ---
def generate_filename(original_name):
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp4"
    return pattern.replace("{number}", str(file_counter)).replace("{original}", base) + ext

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to File Renamer Bot!*\n\n"
        "Send me any file, and I'll rename it using your custom pattern.\n\n"
        "Commands:\n"
        "`/setpattern` - Set rename pattern (use `{original}`, `{number}`)\n"
        "`/reset` - Reset counter\n"
        "`/setthumb` - Set thumbnail (for videos only)",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Pattern set to:\n{pattern}")
    else:
        await update.message.reply_text("❗ Usage: /setpattern Series S01 - {number}")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔄 Counter reset.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Default thumbnail set.")
    else:
        await update.message.reply_text("❗ Please send a JPG or PNG image.")

# --- File Handler ---
def is_video_file(name):
    return name.lower().endswith(('.mp4', '.mkv', '.mov'))

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
            if file.thumb:
                tg_thumb = await file.thumb.get_file()
                thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
                await tg_thumb.download_to_drive(thumb_path)
                thumb = open(thumb_path, "rb")
            elif user_thumbnail and os.path.exists(user_thumbnail):
                thumb = open(user_thumbnail, "rb")

        if is_video_file(original_name):
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
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, set_thumbnail))

    print("🚀 Bot is running...")
    app.run_polling()
