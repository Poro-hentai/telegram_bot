import os
import re
import uuid
import json
import logging
import threading
import requests
from flask import Flask
from PIL import Image
from io import BytesIO
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
)

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Flask App (for Render keep-alive) ===
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# === Global Variables ===
pattern = "{original}_{number}"
file_counter = 0
THUMB_FILE = "thumbs.json"
thumbnails_dir = "thumbnails"
os.makedirs(thumbnails_dir, exist_ok=True)

# === Helper Functions ===
def load_thumbs():
    return json.load(open(THUMB_FILE)) if os.path.exists(THUMB_FILE) else {}

def save_thumbs(data):
    with open(THUMB_FILE, "w") as f:
        json.dump(data, f, indent=2)

def generate_filename(original_name: str) -> str:
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    ext = ext if ext.startswith('.') else f'.{ext}'
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    return pattern.replace("{original}", base).replace("{number}", str(file_counter)) + ext

def download_and_convert_jpg(url, path):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG")

# === Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("About", callback_data="about"),
         InlineKeyboardButton("Help", callback_data="help")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    caption = "\ud83d\udc4b *Welcome to File Renamer Bot!*\nSend me any video, document or PDF, and I'll rename it!\nUse /setthumburl to set your own thumbnail using a Telegra.ph image URL."
    media_url = "https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg"
    await update.message.reply_photo(photo=media_url, caption=caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "about":
        buttons = [[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="back")], [InlineKeyboardButton("Close", callback_data="close")]]
        await query.edit_message_caption(
            caption="\ud83d\udcc5 *About Us*\n\nWe are a simple file renamer bot for Telegram users.\n\nMade with \u2764\ufe0f by @YourChannel",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "help":
        await query.edit_message_caption(
            caption="\u2753 *Help Menu*\n\n/setpattern <pattern>\n/setthumburl <telegra.ph URL>\n/deletethumb\n/reset",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="back")], [InlineKeyboardButton("Close", callback_data="close")]])
        )
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

async def set_thumb_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setthumburl <Telegra.ph URL>")
        return
    url = context.args[0]
    if not url.startswith("https://telegra.ph/"):
        await update.message.reply_text("❌ Only Telegra.ph image links are supported.")
        return
    thumbs = load_thumbs()
    user_id = str(update.effective_user.id)
    thumbs[user_id] = url
    save_thumbs(thumbs)
    thumb_path = f"{thumbnails_dir}/{user_id}.jpg"
    download_and_convert_jpg(url, thumb_path)
    await update.message.reply_text("✅ Thumbnail saved and set successfully!")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs = load_thumbs()
    if user_id in thumbs:
        thumbs.pop(user_id)
        save_thumbs(thumbs)
        path = f"{thumbnails_dir}/{user_id}.jpg"
        if os.path.exists(path): os.remove(path)
        await update.message.reply_text("🗑️ Your thumbnail has been deleted.")
    else:
        await update.message.reply_text("ℹ️ You don't have a thumbnail set.")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔄 Counter reset to 0.")

# === File Handler ===
def is_video(filename):
    return filename.lower().endswith((".mp4", ".mkv", ".avi", ".webm"))

def is_pdf(filename):
    return filename.lower().endswith(".pdf")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document or update.message.video
    if not file:
        await update.message.reply_text("❗ Send a document or video file.")
        return

    status = await update.message.reply_text("⬇️ Downloading...")
    user_id = str(update.effective_user.id)
    original_name = file.file_name or "unnamed"
    new_name = generate_filename(original_name)
    local_path = f"downloads/{uuid.uuid4().hex}_{original_name}"
    os.makedirs("downloads", exist_ok=True)

    tg_file = await file.get_file()
    await tg_file.download_to_drive(local_path)
    await status.edit_text("⬆️ Uploading...")

    thumb = None
    thumb_path = f"{thumbnails_dir}/{user_id}.jpg"
    if os.path.exists(thumb_path):
        thumb = open(thumb_path, "rb")

    try:
        if is_video(original_name):
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=open(local_path, "rb"),
                caption=new_name,
                thumbnail=thumb,
                supports_streaming=True
            )
        else:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=new_name,
                thumbnail=thumb if is_pdf(original_name) else None
            )
        await status.edit_text("✅ Done! File renamed and sent.")
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(local_path): os.remove(local_path)
        if thumb: thumb.close()

# === Bot Init ===
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setthumburl", set_thumb_url))
    app.add_handler(CommandHandler("deletethumb", delete_thumb))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))

    logger.info("Bot running...")
    app.run_polling(drop_pending_updates=True)
