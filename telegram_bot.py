# === File Renamer Bot with Enhanced Features ===

import os
import re
import uuid
import json
import logging
import threading
import requests
from datetime import datetime
from flask import Flask
from PIL import Image
from io import BytesIO
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    CallbackQueryHandler, filters
)

# === Configuration ===
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282
START_TIME = datetime.now()

# === Logging ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Flask for Render Keep-Alive ===
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# === Directories ===
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# === File Paths ===
USERS_FILE = "users.json"
THUMBS_FILE = "thumbs.json"

# === Load/Save Functions ===
def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

# === Globals ===
users = load_json(USERS_FILE)
thumbs = load_json(THUMBS_FILE)
file_counter = 0
pattern = "{original}_{number}"
autorename_enabled = {}

# === Utils ===
def register_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = str(datetime.now())
        save_json(USERS_FILE, users)

def generate_filename(original):
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    return pattern.replace("{original}", base).replace("{number}", str(file_counter)) + ext

def download_and_convert_jpg(url, path):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG")

# === Command Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    register_user(user_id)
    buttons = [[
        InlineKeyboardButton("About", callback_data="about"),
        InlineKeyboardButton("Help", callback_data="help")
    ], [
        InlineKeyboardButton("Close", callback_data="close")
    ]]
    await update.message.reply_photo(
        photo="https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg",
        caption="\U0001F44B *Welcome to File Renamer Bot!*\n\nSend a document or video and I'll rename it!\n\n/setpattern | /setthumburl | /deletethumb | /autorename | /stats",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "about":
        await query.edit_message_caption(
            caption="\U0001F4C5 *About Us*\n\nFile renamer bot for Telegram. Made by @YourChannel.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "help":
        await query.edit_message_caption(
            caption="\u2753 *Help Menu*\n\n/setpattern <pattern>\n/setthumburl <url>\n/deletethumb\n/autorename on|off\n/stats",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
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
    if not url.startswith("https://telegra.ph"):
        await update.message.reply_text("❌ Only Telegra.ph images supported.")
        return
    user_id = str(update.effective_user.id)
    thumbs[user_id] = url
    save_json(THUMBS_FILE, thumbs)
    download_and_convert_jpg(url, f"thumbnails/{user_id}.jpg")
    await update.message.reply_text("✅ Thumbnail set!")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs.pop(user_id, None)
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path): os.remove(path)
    await update.message.reply_text("🗑️ Thumbnail deleted.")

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if not context.args:
        await update.message.reply_text("❗ Usage: /setpattern <pattern>")
        return
    pattern = ' '.join(context.args)
    await update.message.reply_text(f"✅ Pattern set: `{pattern}`", parse_mode="Markdown")

async def auto_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.args and context.args[0].lower() == "on":
        autorename_enabled[user_id] = True
        await update.message.reply_text("✅ Autorename enabled!")
    else:
        autorename_enabled[user_id] = False
        await update.message.reply_text("❌ Autorename disabled.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - START_TIME
    await update.message.reply_text(f"📊 Stats\nUsers: {len(users)}\nUptime: {str(uptime).split('.')[0]}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"👥 Total users: {len(users)}")

# === File Handling ===
def is_video(filename):
    return filename.lower().endswith(('.mp4', '.mkv', '.avi'))

def is_pdf(filename):
    return filename.lower().endswith('.pdf')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    register_user(user_id)
    file = update.message.document or update.message.video
    if not file:
        await update.message.reply_text("❗ Send a valid video or document file.")
        return

    msg = await update.message.reply_text("⬇️ Downloading...")
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    original_name = file.file_name or "file"
    new_name = generate_filename(original_name) if autorename_enabled.get(user_id) else original_name
    path = f"downloads/{uuid.uuid4().hex}_{original_name}"

    tg_file = await file.get_file()
    await tg_file.download_to_drive(path)
    await msg.edit_text("⬆️ Uploading...")

    thumb_path = f"thumbnails/{user_id}.jpg"
    thumb = open(thumb_path, "rb") if os.path.exists(thumb_path) else None

    try:
        if is_video(original_name):
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=open(path, "rb"),
                caption=new_name,
                thumbnail=thumb,
                supports_streaming=True
            )
        else:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=open(path, "rb"),
                caption=new_name,
                filename=new_name,
                thumbnail=thumb if is_pdf(original_name) else None
            )
        await msg.delete()
        done_msg = await update.effective_chat.send_message("✅ Done!")
        await threading.Timer(30.0, lambda: context.bot.delete_message(update.effective_chat.id, done_msg.message_id)).start()
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(path): os.remove(path)
        if thumb: thumb.close()

# === Main Init ===
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setthumburl", set_thumb_url))
    app.add_handler(CommandHandler("deletethumb", delete_thumb))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("autorename", auto_rename))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.ALL, lambda u, c: u.message.delete()))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)
