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
from pdf2image import convert_from_path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Global Variables ---
pattern = "{original}_{number}"
file_counter = 0
user_thumbnail = None

# --- Flask App ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Flask app running on port {port}")
    flask_app.run(host="0.0.0.0", port=port)

# --- Filename Generator ---
def generate_filename(original_name: str) -> str:
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    ext = ext if ext.startswith('.') else '.' + ext
    if not ext: ext = ".mp4"
    cleaned_base = re.sub(r'[<>:"/\\|?*]', '', base)
    return pattern.replace("{number}", str(file_counter)).replace("{original}", cleaned_base) + ext

# --- Telegram Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to File Renamer Bot!*\n\n"
        "Send me any file, and I'll rename it using your custom pattern.\n\n"
        "`/setpattern <pattern>` - Use `{original}` and `{number}`\n"
        "`/reset` - Reset counter\n"
        "`/setthumb` - Reply to a photo with this to set thumbnail\n"
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

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumbnails/thumb_{uuid.uuid4().hex}.jpg"
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        if user_thumbnail and os.path.exists(user_thumbnail):
            os.remove(user_thumbnail)
        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Thumbnail set!")
    else:
        await update.message.reply_text("❗ Reply to a photo with `/setthumb` to set a thumbnail.", parse_mode="Markdown")

# --- Helper ---
def is_video_file(filename: str) -> bool:
    return filename.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm'))

def is_pdf_file(filename: str) -> bool:
    return filename.lower().endswith('.pdf')

def generate_pdf_thumbnail(pdf_path: str) -> str:
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        thumb_path = f"thumbnails/pdf_thumb_{uuid.uuid4().hex}.jpg"
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        images[0].save(thumb_path, 'JPEG')
        return thumb_path
    except Exception as e:
        logger.error(f"PDF thumbnail error: {e}")
        return None

# --- File Handler ---
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    file = message.document or message.video

    if not file:
        await message.reply_text("❗ Send a document or video to rename.")
        return

    status = await message.reply_text("⬇️ Downloading...")
    try:
        tg_file = await file.get_file()
        original_name = file.file_name or "unknown_file"
        new_name = generate_filename(original_name)
        temp_dir = "downloads"
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{original_name}")
        await tg_file.download_to_drive(local_path)
        await status.edit_text("⬆️ Uploading...")

        caption = f"{new_name}"
        thumb_file = None
        temp_thumb_path = None

        if is_video_file(original_name):
            if file.thumbnail:
                tg_thumb = await file.thumbnail.get_file()
                temp_thumb_path = f"thumbnails/temp_thumb_{uuid.uuid4().hex}.jpg"
                os.makedirs(os.path.dirname(temp_thumb_path), exist_ok=True)
                await tg_thumb.download_to_drive(temp_thumb_path)
                thumb_file = open(temp_thumb_path, "rb")
            elif user_thumbnail and os.path.exists(user_thumbnail):
                thumb_file = open(user_thumbnail, "rb")

            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumbnail=thumb_file if thumb_file else None,
                supports_streaming=True
            )

        elif is_pdf_file(original_name):
            thumb_path = generate_pdf_thumbnail(local_path)
            if thumb_path:
                thumb_file = open(thumb_path, "rb")
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption,
                thumbnail=thumb_file if thumb_file else None
            )

        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption
            )

        await status.edit_text("✅ File renamed and sent!")

    except Exception as e:
        logger.error(f"File error: {e}", exc_info=True)
        await status.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)
        if thumb_file and not thumb_file.closed:
            thumb_file.close()
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)

# --- Main Bot Setup ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO & filters.REPLY, set_thumbnail))

    logger.info("🚀 Bot is running...")
    app.run_polling(drop_pending_updates=True)
