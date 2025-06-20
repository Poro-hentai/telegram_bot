# === File Renamer Bot – Final Enhanced Version ===

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
from pdf2image import convert_from_path

# === Configuration ===
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282
START_TIME = datetime.now()

# === Logging ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Flask (Render Keep-Alive) ===
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

# === JSON Storage ===
USERS_FILE = "users.json"
THUMBS_FILE = "thumbs.json"
PATTERN_FILE = "patterns.json"

users = json.load(open(USERS_FILE)) if os.path.exists(USERS_FILE) else {}
thumbs = json.load(open(THUMBS_FILE)) if os.path.exists(THUMBS_FILE) else {}
patterns = json.load(open(PATTERN_FILE)) if os.path.exists(PATTERN_FILE) else {}
autorename_enabled = {}
file_counter = 0

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

# === Utilities ===
def register_user(user_id):
    if str(user_id) not in users:
        users[str(user_id)] = str(datetime.now())
        save_json(USERS_FILE, users)

def generate_filename(original, user_id):
    global file_counter
    file_counter += 1
    pattern = patterns.get(str(user_id), "{original}_{number}")
    base, ext = os.path.splitext(original)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    return pattern.replace("{original}", base).replace("{number}", str(file_counter)) + ext

def download_and_convert_jpg(url, path):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG")

def generate_pdf_thumb(pdf_path, thumb_path):
    try:
        pages = convert_from_path(pdf_path, first_page=1, last_page=1)
        pages[0].save(thumb_path, 'JPEG')
        return thumb_path
    except:
        return None

# === Commands ===
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
        caption="👋 *Welcome to File Renamer Bot!*

Send any document, video, or PDF and I’ll rename it for you with custom name and thumbnail.

🔧 Commands:
/setpattern – Set renaming pattern
/seepattern – View your current pattern
/delpattern – Delete your pattern
/setthumburl – Set thumbnail from Telegra.ph
/seethumb – Preview current thumbnail
/deletethumb – Remove your thumbnail
/autorename on|off – Enable/disable autorename
/stats – Uptime & users count
/broadcast – Admin only",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        await query.edit_message_caption(
            caption="📌 *About This Bot*

I help you rename your Telegram files with custom names & thumbnails.
Made by [@YourChannel](https://t.me/YourChannel)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "help":
        await query.edit_message_caption(
            caption="❓ *Help Guide*

/setpattern <pattern> – Set pattern (use {original} {number})
/seepattern – See your current pattern
/delpattern – Delete saved pattern
/setthumburl <URL> – Telegra.ph only
/seethumb – See your current thumbnail
/deletethumb – Remove your thumbnail
/autorename on|off – Enable or disable auto renaming

ℹ️ AutoRename helps rename files automatically on upload!",
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
        await update.message.reply_text("❌ Only Telegra.ph image links supported!")
        return
    user_id = str(update.effective_user.id)
    thumbs[user_id] = url
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    download_and_convert_jpg(url, path)
    await update.message.reply_text("✅ Thumbnail saved successfully!")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs.pop(user_id, None)
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path): os.remove(path)
    await update.message.reply_text("🗑️ Thumbnail deleted!")

async def see_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path):
        await update.message.reply_photo(photo=open(path, "rb"))
    else:
        await update.message.reply_text("ℹ️ No thumbnail found.")

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setpattern <pattern> e.g. `{original}_{number}`", parse_mode="Markdown")
        return
    user_id = str(update.effective_user.id)
    patterns[user_id] = ' '.join(context.args)
    save_json(PATTERN_FILE, patterns)
    await update.message.reply_text(f"✅ Pattern saved: `{patterns[user_id]}`", parse_mode="Markdown")

async def see_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    pattern = patterns.get(user_id, "{original}_{number}")
    await update.message.reply_text(f"📌 Your pattern: `{pattern}`", parse_mode="Markdown")

async def del_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in patterns:
        del patterns[user_id]
        save_json(PATTERN_FILE, patterns)
        await update.message.reply_text("🗑️ Pattern deleted!")
    else:
        await update.message.reply_text("ℹ️ No pattern to delete.")

async def auto_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if context.args:
        if context.args[0].lower() == "on":
            autorename_enabled[user_id] = True
            await update.message.reply_text("✅ AutoRename enabled!")
        elif context.args[0].lower() == "off":
            autorename_enabled[user_id] = False
            await update.message.reply_text("❌ AutoRename disabled!")
    else:
        status = autorename_enabled.get(user_id, False)
        await update.message.reply_text(f"ℹ️ AutoRename is {'enabled ✅' if status else 'disabled ❌'}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - START_TIME
    await update.message.reply_text(f"📊 Bot Stats:\n👥 Users: {len(users)}\n⏱️ Uptime: {str(uptime).split('.')[0]}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("❗ Usage: /broadcast <message>")
        return
    msg = ' '.join(context.args)
    count = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
            count += 1
        except:
            pass
    await update.message.reply_text(f"📢 Broadcast sent to {count} users.")

# === File Handler ===
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
    original_name = file.file_name or "file"
    new_name = generate_filename(original_name, user_id) if autorename_enabled.get(user_id) else original_name
    path = f"downloads/{uuid.uuid4().hex}_{original_name}"

    tg_file = await file.get_file()
    await tg_file.download_to_drive(path)
    await msg.edit_text("⬆️ Uploading...")

    thumb_path = f"thumbnails/{user_id}.jpg"
    thumb = open(thumb_path, "rb") if os.path.exists(thumb_path) else None

    # If PDF and no thumb, create one
    if not thumb and is_pdf(original_name):
        temp_thumb = f"thumbnails/temp_{uuid.uuid4().hex}.jpg"
        if generate_pdf_thumb(path, temp_thumb):
            thumb = open(temp_thumb, "rb")

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
                filename=new_name,
                caption=new_name,
                thumbnail=thumb
            )
        await msg.edit_text("✅ Done!")
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
    app.add_handler(CommandHandler("seethumb", see_thumb))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("seepattern", see_pattern))
    app.add_handler(CommandHandler("delpattern", del_pattern))
    app.add_handler(CommandHandler("autorename", auto_rename))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    logger.info("Bot running...")
    app.run_polling(drop_pending_updates=True)
