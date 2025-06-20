# === Enhanced File Renamer Bot with Full Features ===

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
from pdf2image import convert_from_path
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
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

# === Flask Setup ===
flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# === Paths & Globals ===
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)
USERS_FILE = "users.json"
THUMBS_FILE = "thumbs.json"
PATTERNS_FILE = "patterns.json"
users = {}
thumbs = {}
patterns = {}
autorename_enabled = {}
file_counter = 0

# === Load & Save ===
def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# === Startup Load ===
users = load_json(USERS_FILE)
thumbs = load_json(THUMBS_FILE)
patterns = load_json(PATTERNS_FILE)

def register_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = str(datetime.now())
        save_json(USERS_FILE, users)

def get_pattern(user_id):
    return patterns.get(str(user_id), "{original}_{number}")

def generate_filename(original, user_id):
    global file_counter
    file_counter += 1
    base, ext = os.path.splitext(original)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    pattern = get_pattern(user_id)
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
        caption="👋 *Welcome to File Renamer Bot!*\n\nSend any video or document and I will rename it!\n\nUse /setpattern /seepattern /delpattern /setthumburl /seethumb /deletethumb /autorename on|off\n\n🧠 Made by @YourChannelHere",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        await query.edit_message_caption(
            caption="📌 *About Us*\n\nThis bot renames your Telegram files easily.\nJoin @YourChannelHere for updates.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "help":
        await query.edit_message_caption(
            caption="❓ *Help Menu*\n\n/setpattern <pattern>\n/seepattern\n/delpattern\n/setthumburl <url>\n/seethumb\n/deletethumb\n/autorename on|off\n\n\nAutorename will rename using your pattern. Use {original} and {number} in pattern.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setpattern <pattern>")
        return
    pattern = ' '.join(context.args)
    patterns[str(update.effective_user.id)] = pattern
    save_json(PATTERNS_FILE, patterns)
    await update.message.reply_text(f"✅ Pattern saved: `{pattern}`", parse_mode="Markdown")

async def seepattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = get_pattern(update.effective_user.id)
    await update.message.reply_text(f"📂 Current pattern: `{pattern}`", parse_mode="Markdown")

async def delpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    patterns.pop(user_id, None)
    save_json(PATTERNS_FILE, patterns)
    await update.message.reply_text("🗑️ Pattern deleted.")

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

async def seethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in thumbs:
        await update.message.reply_photo(photo=thumbs[user_id], caption="🖼️ Your current thumbnail")
    else:
        await update.message.reply_text("⚠️ No thumbnail set.")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs.pop(user_id, None)
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path): os.remove(path)
    await update.message.reply_text("🗑️ Thumbnail deleted.")

async def auto_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.args and context.args[0].lower() == "on":
        autorename_enabled[user_id] = True
        await update.message.reply_text("✅ Autorename enabled!")
    elif context.args and context.args[0].lower() == "off":
        autorename_enabled[user_id] = False
        await update.message.reply_text("❌ Autorename disabled!")
    else:
        status = autorename_enabled.get(user_id, False)
        await update.message.reply_text(f"🔄 Autorename is currently: {'✅ Enabled' if status else '❌ Disabled'}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    uptime = datetime.now() - START_TIME
    await update.message.reply_text(f"📊 Stats:\nUsers: {len(users)}\nUptime: {str(uptime).split('.')[0]}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"👥 Total users: {len(users)}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("😵 Baka! I don't understand that command.")

# === File Handling ===
def is_video(name):
    return name.lower().endswith((".mp4", ".mkv", ".webm"))

def is_pdf(name):
    return name.lower().endswith(".pdf")

def generate_pdf_thumb(pdf_path, thumb_path):
    pages = convert_from_path(pdf_path, 100, first_page=1, last_page=1)
    pages[0].save(thumb_path, 'JPEG')

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    register_user(user_id)
    file = update.message.document or update.message.video
    if not file:
        return
    status = await update.message.reply_text("⬇️ Downloading...")
    fname = file.file_name or "file"
    path = f"downloads/{uuid.uuid4().hex}_{fname}"
    tg_file = await file.get_file()
    await tg_file.download_to_drive(path)
    pattern = autorename_enabled.get(user_id, False)
    new_name = generate_filename(fname, user_id) if pattern else fname
    thumb_path = f"thumbnails/{user_id}.jpg"
    thumb = open(thumb_path, "rb") if os.path.exists(thumb_path) else None

    if not thumb and is_pdf(fname):
        preview = f"thumbnails/{user_id}_auto.jpg"
        generate_pdf_thumb(path, preview)
        thumb = open(preview, "rb")

    await status.edit_text("⬆️ Uploading...")
    try:
        if is_video(fname):
            await context.bot.send_video(chat_id=update.effective_chat.id, video=open(path, "rb"), caption=new_name, thumbnail=thumb, supports_streaming=True)
        else:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(path, "rb"), filename=new_name, caption=new_name, thumbnail=thumb if is_pdf(fname) else None)
        await status.edit_text("✅ Done!")
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(path): os.remove(path)
        if thumb: thumb.close()

# === App Init ===
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("seepattern", seepattern))
    app.add_handler(CommandHandler("delpattern", delpattern))
    app.add_handler(CommandHandler("setthumburl", set_thumb_url))
    app.add_handler(CommandHandler("seethumb", seethumb))
    app.add_handler(CommandHandler("deletethumb", delete_thumb))
    app.add_handler(CommandHandler("autorename", auto_rename))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)
