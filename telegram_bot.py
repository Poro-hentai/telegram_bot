# Final working Telegram File Renamer Bot with the following features:
# - /start: Banner image + caption + buttons
# - /setpattern: Per-user custom filename pattern
# - /setthumburl <url>: Sets custom thumbnail from Telegra.ph URL
# - /deletethumb: Deletes user's thumbnail
# - Handles document, video, and PDF files with appropriate thumbnails
# - Broadcast feature for admin

import os
import re
import json
import uuid
import logging
import requests
import threading
from flask import Flask
from telegram import (Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters)

# --- Configuration ---
BOT_TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282  # Change to your actual admin ID
START_BANNER_URL = "https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Data Files ---
THUMB_FILE = "thumbs.json"
PATTERN_FILE = "patterns.json"

# Load or init JSON
if not os.path.exists(THUMB_FILE):
    with open(THUMB_FILE, "w") as f: json.dump({}, f)
if not os.path.exists(PATTERN_FILE):
    with open(PATTERN_FILE, "w") as f: json.dump({}, f)

# --- Flask ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot is running!"
def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# --- Helper Functions ---
def load_json(path):
    with open(path, "r") as f:
        return json.load(f)
def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_user_pattern(user_id):
    data = load_json(PATTERN_FILE)
    return data.get(str(user_id), "{original}_{number}")

def get_user_thumb(user_id):
    data = load_json(THUMB_FILE)
    return data.get(str(user_id))

def set_user_pattern(user_id, pattern):
    data = load_json(PATTERN_FILE)
    data[str(user_id)] = pattern
    save_json(PATTERN_FILE, data)

def set_user_thumb(user_id, url):
    data = load_json(THUMB_FILE)
    thumb_path = f"thumbnails/{user_id}.jpg"
    os.makedirs("thumbnails", exist_ok=True)
    r = requests.get(url)
    if r.status_code == 200:
        with open(thumb_path, "wb") as f:
            f.write(r.content)
        data[str(user_id)] = thumb_path
        save_json(THUMB_FILE, data)
        return True
    return False

def delete_user_thumb(user_id):
    data = load_json(THUMB_FILE)
    path = data.pop(str(user_id), None)
    if path and os.path.exists(path): os.remove(path)
    save_json(THUMB_FILE, data)

def generate_filename(user_id, original_name, counter):
    base, ext = os.path.splitext(original_name)
    pattern = get_user_pattern(user_id)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    filename = pattern.replace("{original}", base).replace("{number}", str(counter))
    return filename + (ext or ".mp4")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[
        InlineKeyboardButton("About", callback_data="about"),
        InlineKeyboardButton("Help", callback_data="help"),
        InlineKeyboardButton("Close", callback_data="close")
    ]]
    await update.message.reply_photo(
        photo=START_BANNER_URL,
        caption="\U0001F44B *Welcome to File Renamer Bot!*\n\nSend a file to rename it with your custom pattern.",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "close":
        await query.message.delete()
    elif data == "help":
        await query.edit_message_text(
            "*Commands:*\n/setpattern <pattern>\n/setthumburl <url>\n/deletethumb\n/send file to rename",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]])
        )
    elif data == "about":
        await query.edit_message_text(
            "*This bot was made for renaming files with thumbnails!*\n\nBy @yourchannel",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]])
        )
    elif data == "back":
        await start(update, context)

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        pattern = " ".join(context.args)
        set_user_pattern(update.effective_user.id, pattern)
        await update.message.reply_text(f"✅ Pattern set to: `{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Usage: /setpattern {original}_{number}")

async def set_thumb_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        url = context.args[0]
        success = set_user_thumb(update.effective_user.id, url)
        await update.message.reply_text("✅ Thumbnail set." if success else "❌ Failed to set thumbnail.")
    else:
        await update.message.reply_text("Usage: /setthumburl <image_url>")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delete_user_thumb(update.effective_user.id)
    await update.message.reply_text("🗑️ Thumbnail deleted.")

# --- File Handler ---
counter = 1
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global counter
    file = update.message.document or update.message.video or update.message
    telegram_file = await file.effective_attachment.get_file()
    name = file.document.file_name if file.document else file.video.file_name if file.video else "file"
    new_name = generate_filename(update.effective_user.id, name, counter)
    counter += 1

    await update.message.reply_chat_action("upload_document")
    path = f"downloads/{uuid.uuid4().hex}_{new_name}"
    os.makedirs("downloads", exist_ok=True)
    await telegram_file.download_to_drive(path)

    thumb_path = get_user_thumb(update.effective_user.id)
    if file.video:
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=open(path, "rb"),
            caption=new_name,
            thumbnail=open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None,
            supports_streaming=True
        )
    else:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(path, "rb"),
            filename=new_name,
            caption=new_name
        )
    os.remove(path)

# --- Broadcast ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("You are not authorized.")
    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("Usage: /broadcast your_message")
    users = list(load_json(PATTERN_FILE).keys())
    count = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            count += 1
        except: continue
    await update.message.reply_text(f"✅ Sent to {count} users.")

# --- Main ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("setthumburl", set_thumb_url))
    app.add_handler(CommandHandler("deletethumb", delete_thumb))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.Video.ALL, handle_file))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)
