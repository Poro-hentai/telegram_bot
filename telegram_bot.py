import os
import re
import uuid
import json
import logging
import requests
import threading
from flask import Flask
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------- Flask ----------------
flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ---------------- Global ----------------
ADMIN_ID = 5759232282  # Change to your Telegram user ID
TOKEN = os.environ.get("BOT_TOKEN") or "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
USERS_FILE = "users.json"

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

def load_users():
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def get_user_data(user_id):
    users = load_users()
    return users.get(str(user_id), {"pattern": "{original}_{number}", "thumb_url": None, "counter": 0})

def set_user_data(user_id, data):
    users = load_users()
    users[str(user_id)] = data
    save_users(users)

# ---------------- Utils ----------------
def generate_filename(original_name, pattern, counter):
    base, ext = os.path.splitext(original_name)
    base = re.sub(r'[<>:"/\\|?*]', '', base)
    ext = ext if ext else ".mp4"
    return pattern.replace("{original}", base).replace("{number}", str(counter)) + ext

def is_video(filename):
    return filename.lower().endswith((".mp4", ".mkv", ".webm", ".mov"))

# ---------------- Commands ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[
        InlineKeyboardButton("About", callback_data="about"),
        InlineKeyboardButton("Help", callback_data="help"),
        InlineKeyboardButton("Close", callback_data="close")
    ]]
    await update.message.reply_photo(
        photo="https://telegra.ph/file/9d18345731db88fff4f8c-d2b3920631195c5747.jpg",
        caption="👋 Welcome! Send a file to rename it. Use /setpattern and /setthumburl to customize.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        buttons = [[InlineKeyboardButton("Back", callback_data="start")]]
        await query.edit_message_caption(
            caption="📢 About: This bot renames files with custom names and thumbnails.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "help":
        buttons = [[InlineKeyboardButton("Back", callback_data="start")]]
        await query.edit_message_caption(
            caption="🛠️ Help: Use /setpattern and /setthumburl <telegra.ph URL> to customize.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "start":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setpattern {original}_{number}")
        return
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    data["pattern"] = " ".join(context.args)
    set_user_data(user_id, data)
    await update.message.reply_text("✅ Pattern updated!")

async def set_thumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /setthumburl <telegra.ph URL>")
        return
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    data["thumb_url"] = context.args[0]
    set_user_data(user_id, data)
    await update.message.reply_text("✅ Thumbnail URL set!")

async def delete_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    data["thumb_url"] = None
    set_user_data(user_id, data)
    await update.message.reply_text("🗑️ Thumbnail removed!")

async def see_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    if data.get("thumb_url"):
        await update.message.reply_photo(photo=data["thumb_url"], caption="📷 Current thumbnail")
    else:
        await update.message.reply_text("❌ No thumbnail set.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document or update.message.video
    if not file:
        return
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    data["counter"] += 1
    set_user_data(user_id, data)
    new_name = generate_filename(file.file_name or "file", data["pattern"], data["counter"])

    downloading = await update.message.reply_text("⬇️ Downloading...")
    tg_file = await file.get_file()
    temp_path = f"downloads/{uuid.uuid4().hex}_{file.file_name}"
    os.makedirs("downloads", exist_ok=True)
    await tg_file.download_to_drive(temp_path)
    await downloading.delete()

    uploading = await update.message.reply_text("⬆️ Uploading...")
    if is_video(file.file_name):
        thumb = None
        if data.get("thumb_url"):
            r = requests.get(data["thumb_url"])
            if r.ok:
                thumb_path = f"thumbs/{uuid.uuid4().hex}.jpg"
                os.makedirs("thumbs", exist_ok=True)
                with open(thumb_path, "wb") as f:
                    f.write(r.content)
                thumb = open(thumb_path, "rb")
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=open(temp_path, "rb"),
            caption=new_name,
            filename=new_name,
            supports_streaming=True,
            thumbnail=thumb
        )
        if thumb: thumb.close()
    else:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(temp_path, "rb"),
            filename=new_name,
            caption=new_name
        )
    await uploading.delete()
    os.remove(temp_path)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message")
        return
    users = load_users()
    msg = " ".join(context.args)
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
        except:
            continue
    await update.message.reply_text("✅ Broadcast sent.")

# ---------------- Main ----------------
if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("setthumburl", set_thumburl))
    app.add_handler(CommandHandler("deletethumb", delete_thumb))
    app.add_handler(CommandHandler("seethumb", see_thumb))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.Video.ALL, handle_file))

    logger.info("🤖 Bot running...")
    app.run_polling()
