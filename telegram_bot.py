import os
import re
import uuid
import json
import logging
import threading
import requests
from flask import Flask
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask Setup for Keep Alive ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Bot is running!'

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port)

# --- Globals ---
USERS_FILE = 'users.json'
THUMB_DIR = 'thumbnails'
DOWNLOAD_DIR = 'downloads'
os.makedirs(THUMB_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

START_IMAGE_URL = 'https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg'
ADMIN_ID = 5759232282  # Replace with your actual Telegram user ID

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({}, f)

# --- Helpers ---
def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def get_user_data(user_id):
    users = load_users()
    return users.get(str(user_id), {"pattern": "{original}_{number}", "counter": 0, "thumburl": None})

def update_user_data(user_id, data):
    users = load_users()
    users[str(user_id)] = data
    save_users(users)

def download_image(url, path):
    r = requests.get(url)
    with open(path, 'wb') as f:
        f.write(r.content)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("About", callback_data='about'), InlineKeyboardButton("Help", callback_data='help')],
        [InlineKeyboardButton("Close", callback_data='close')]
    ]
    await update.message.reply_photo(
        photo=START_IMAGE_URL,
        caption="👋 *Welcome to File Renamer Bot!*\nSend a file to rename it using your pattern. Use /setpattern /setthumburl /deletethumb",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setpattern My_Series_Episode_{number}_{original}")
        return
    data = get_user_data(user_id)
    data['pattern'] = " ".join(context.args)
    update_user_data(user_id, data)
    await update.message.reply_text(f"✅ Pattern set to:\n{data['pattern']}")

async def setthumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setthumburl <telegra.ph image url>")
        return
    url = context.args[0]
    thumb_path = os.path.join(THUMB_DIR, f"thumb_{user_id}.jpg")
    try:
        download_image(url, thumb_path)
        data = get_user_data(user_id)
        data['thumburl'] = thumb_path
        update_user_data(user_id, data)
        await update.message.reply_text("✅ Thumbnail set from URL")
    except:
        await update.message.reply_text("❌ Failed to download thumbnail. Check the URL.")

async def deletethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    if data.get('thumburl') and os.path.exists(data['thumburl']):
        os.remove(data['thumburl'])
    data['thumburl'] = None
    update_user_data(user_id, data)
    await update.message.reply_text("🗑️ Thumbnail removed.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message")
        return
    msg = " ".join(context.args)
    users = load_users()
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
        except:
            pass
    await update.message.reply_text("✅ Broadcast sent.")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'about':
        keyboard = [[InlineKeyboardButton("Back", callback_data='start')]]
        await query.edit_message_caption(
            caption="📢 *About this bot*\nThis bot renames your files with thumbnails and custom patterns.",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif query.data == 'help':
        keyboard = [[InlineKeyboardButton("Back", callback_data='start')]]
        await query.edit_message_caption(
            caption="📖 *Help Guide*\nCommands: /setpattern /setthumburl /deletethumb /broadcast",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    elif query.data == 'start':
        await start(update, context)
    elif query.data == 'close':
        await query.message.delete()

# --- File Handler ---
def is_video(filename):
    return filename.lower().endswith(('.mp4', '.mkv', '.avi'))

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file = update.message.document or update.message.video
    if not file:
        return
    data = get_user_data(user_id)
    data['counter'] += 1
    update_user_data(user_id, data)

    original = file.file_name or "file"
    base, ext = os.path.splitext(original)
    cleaned = re.sub(r'[<>:"/\\|?*]', '', base)
    new_name = data['pattern'].replace('{original}', cleaned).replace('{number}', str(data['counter'])) + ext

    status = await update.message.reply_text("📥 Downloading...")
    tg_file = await file.get_file()
    temp_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}_{original}")
    await tg_file.download_to_drive(temp_path)
    await status.edit_text("📤 Uploading...")

    thumb = None
    if is_video(original) and data.get('thumburl') and os.path.exists(data['thumburl']):
        thumb = open(data['thumburl'], 'rb')

    try:
        if is_video(original):
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=open(temp_path, 'rb'),
                caption=new_name,
                thumbnail=thumb,
                supports_streaming=True
            )
        else:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=open(temp_path, 'rb'),
                filename=new_name,
                caption=new_name
            )
        await status.delete()
    finally:
        os.remove(temp_path)
        if thumb:
            thumb.close()

# --- Main ---
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    TOKEN = os.getenv("BOT_TOKEN") or "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("setthumburl", setthumburl))
    app.add_handler(CommandHandler("deletethumb", deletethumb))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))

    logger.info("🤖 Bot is now running...")
    app.run_polling()
