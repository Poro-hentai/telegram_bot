# === File Renamer Bot with All Features ===

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
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from pdf2image import convert_from_path

# === Bot Config ===
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282
START_TIME = datetime.now()

# === Logging ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Flask Keep-Alive ===
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# === Files & Paths ===
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)
USERS_FILE = "users.json"
THUMBS_FILE = "thumbs.json"
PATTERNS_FILE = "patterns.json"
AUTORENAME_FILE = "autorename.json"

# === Load Helpers ===
def load_json(path):
    return json.load(open(path)) if os.path.exists(path) else {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# === Load Data ===
users = load_json(USERS_FILE)
thumbs = load_json(THUMBS_FILE)
patterns = load_json(PATTERNS_FILE)
autorename = load_json(AUTORENAME_FILE)

# === Utilities ===
def register_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = str(datetime.now())
        save_json(USERS_FILE, users)

def generate_filename(original, user_id):
    base, ext = os.path.splitext(original)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    pattern = patterns.get(str(user_id), "{original}_{number}")
    number = str(uuid.uuid4().hex[:4])
    return pattern.replace("{original}", base).replace("{number}", number) + ext

def download_and_convert_jpg(url, path):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG")

def generate_pdf_thumbnail(path, out_path):
    images = convert_from_path(path, first_page=1, last_page=1)
    if images:
        images[0].save(out_path, "JPEG")

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user.id)
    buttons = [[
        InlineKeyboardButton("About", callback_data="about"),
        InlineKeyboardButton("Help", callback_data="help")
    ], [
        InlineKeyboardButton("Close", callback_data="close")
    ]]
    await update.message.reply_photo(
        photo="https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg",
        caption=(
            "\U0001F44B *Welcome to File Renamer Bot!*\n\n"
            "Send a document or video and I'll rename it.\n\n"
            "/setpattern | /seepattern | /delpattern\n"
            "/setthumburl | /seethumb | /deletethumb\n"
            "/autorename | /stats"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# === Inline Buttons ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "about":
        await query.edit_message_caption(
            caption="\U0001F4C5 *About Us*\n\nMade with \u2764\ufe0f by @YourChannelHere",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "help":
        await query.edit_message_caption(
            caption=(
                "\u2753 *Help Menu*\n\n"
                "/setpattern <pattern>\n/seepattern\n/delpattern\n"
                "/setthumburl <url>\n/seethumb\n/deletethumb\n"
                "/autorename on|off\n/stats"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

# === Command Handlers ===
async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setpattern <pattern>")
        return
    user_id = str(update.effective_user.id)
    patterns[user_id] = ' '.join(context.args)
    save_json(PATTERNS_FILE, patterns)
    await update.message.reply_text(f"✅ Pattern saved: `{patterns[user_id]}`", parse_mode="Markdown")

async def see_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    pattern = patterns.get(user_id)
    if pattern:
        await update.message.reply_text(f"🔍 Your pattern: `{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ You don't have any saved pattern.")

async def del_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in patterns:
        del patterns[user_id]
        save_json(PATTERNS_FILE, patterns)
        await update.message.reply_text("🗑️ Pattern deleted.")
    else:
        await update.message.reply_text("❌ No pattern found.")

async def set_thumb_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setthumburl <Telegra.ph URL>")
        return
    url = context.args[0]
    if not url.startswith("https://telegra.ph"):
        await update.message.reply_text("❌ Only Telegra.ph links allowed.")
        return
    user_id = str(update.effective_user.id)
    thumbs[user_id] = url
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    download_and_convert_jpg(url, path)
    await update.message.reply_text("✅ Thumbnail set!")

async def see_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path):
        await update.message.reply_photo(photo=open(path, "rb"))
    else:
        await update.message.reply_text("ℹ️ No thumbnail found.")

async def del_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    path = f"thumbnails/{user_id}.jpg"
    thumbs.pop(user_id, None)
    save_json(THUMBS_FILE, thumbs)
    if os.path.exists(path): os.remove(path)
    await update.message.reply_text("🗑️ Thumbnail deleted.")

async def auto_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        status = autorename.get(user_id, False)
        await update.message.reply_text(f"🔁 Autorename is currently {'✅ ON' if status else '❌ OFF'}")
    else:
        arg = context.args[0].lower()
        if arg == "on":
            autorename[user_id] = True
            await update.message.reply_text("✅ Autorename turned ON!")
        else:
            autorename[user_id] = False
            await update.message.reply_text("❌ Autorename turned OFF!")
        save_json(AUTORENAME_FILE, autorename)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - START_TIME
    await update.message.reply_text(f"📊 Uptime: {str(uptime).split('.')[0]}\n👥 Users: {len(users)}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"👥 Total users: {len(users)}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ Usage: /broadcast <message>")
        return
    text = ' '.join(context.args)
    success = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            success += 1
        except:
            continue
    await update.message.reply_text(f"📢 Broadcast sent to {success} users.")

# === File Handler ===
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    register_user(user_id)
    file = update.message.document or update.message.video
    if not file:
        return
    status = await update.message.reply_text("⬇️ Downloading...")
    name = file.file_name or "file"
    new_name = generate_filename(name, user_id) if autorename.get(user_id) else name
    path = f"downloads/{uuid.uuid4().hex}_{name}"
    tg_file = await file.get_file()
    await tg_file.download_to_drive(path)
    await status.edit_text("⬆️ Uploading...")
    thumb_path = f"thumbnails/{user_id}.jpg"
    thumb = open(thumb_path, "rb") if os.path.exists(thumb_path) else None
    try:
        if file.mime_type.startswith("video"):
            await context.bot.send_video(update.effective_chat.id, video=open(path, "rb"), caption=new_name, thumbnail=thumb, supports_streaming=True)
        else:
            if not os.path.exists(thumb_path) and file.file_name.lower().endswith(".pdf"):
                preview = f"thumbnails/{user_id}_auto.jpg"
                generate_pdf_thumbnail(path, preview)
                thumb = open(preview, "rb") if os.path.exists(preview) else None
            await context.bot.send_document(update.effective_chat.id, document=open(path, "rb"), caption=new_name, filename=new_name, thumbnail=thumb)
        await status.edit_text("✅ Done!")
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(path): os.remove(path)
        if thumb: thumb.close()

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("😒 Baka! I don't understand that command.")

# === Init ===
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("seepattern", see_pattern))
    app.add_handler(CommandHandler("delpattern", del_pattern))
    app.add_handler(CommandHandler("setthumburl", set_thumb_url))
    app.add_handler(CommandHandler("seethumb", see_thumb))
    app.add_handler(CommandHandler("deletethumb", del_thumb))
    app.add_handler(CommandHandler("autorename", auto_rename))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)
