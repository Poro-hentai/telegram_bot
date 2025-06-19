import os
import re
import uuid
import logging
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
pattern = "{original}_{number}"
file_counter = 0
user_thumbnail = None

# Thumbnail URL (permanent)
THUMBNAIL_URL = "https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg"
THUMBNAIL_PATH = "fixed_thumb.jpg"

# Flask app for Render
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# Helpers
def generate_filename(original_name: str) -> str:
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    ext = ext if ext.startswith('.') else '.' + ext
    if not ext:
        ext = ".mp4"
    cleaned_base = re.sub(r'[<>:"/\\|?*]', '', base)
    return pattern.replace("{number}", str(file_counter)).replace("{original}", cleaned_base) + ext

def is_video_file(filename: str) -> bool:
    return filename.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm'))

def ensure_thumbnail():
    os.makedirs("thumbnails", exist_ok=True)
    if not os.path.exists(THUMBNAIL_PATH):
        with open(THUMBNAIL_PATH, "wb") as f:
            f.write(requests.get(THUMBNAIL_URL).content)
    return open(THUMBNAIL_PATH, "rb")

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to File Renamer Bot!*\n\n"
        "Send me any file, and I'll rename it using your custom pattern.\n\n"
        "`/setpattern <pattern>` - Use `{original}` and `{number}`\n"
        "`/reset` - Reset counter\n"
        "`/help` - Show help again",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        new_pattern = " ".join(context.args)
        if "{original}" not in new_pattern and "{number}" not in new_pattern:
            await update.message.reply_text("⚠️ Pattern should include `{original}` or `{number}`.")
        else:
            pattern = new_pattern
            await update.message.reply_text(f"✅ Pattern set to:\n`{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❗ Usage: `/setpattern MySeries - {number} - {original}`", parse_mode="Markdown"
        )

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔄 File counter has been reset to 0.")

# File handler
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    file = message.document or message.video

    if not file:
        await message.reply_text("❗ Send a document or video to rename.")
        return

    status = await message.reply_text("⬇️ Downloading...")

    try:
        tg_file = await file.get_file()
        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)

        temp_dir = "downloads"
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{original_name}")
        await tg_file.download_to_drive(local_path)

        await status.edit_text("⬆️ Uploading...")

        caption = f"{new_name}"
        thumb_file = ensure_thumbnail()

        if is_video_file(original_name):
            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumbnail=thumb_file,
                supports_streaming=True
            )
        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption,
                thumbnail=thumb_file
            )

        await status.delete()

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status.edit_text(f"❌ Error:\n`{e}`", parse_mode="Markdown")

    finally:
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
            if thumb_file and not thumb_file.closed:
                thumb_file.close()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

# Main bot setup
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))

    logger.info("🚀 Bot is live...")
    app.run_polling(drop_pending_updates=True)
