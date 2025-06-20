# === Advanced Telegram File Renamer Bot ===
# Features: Autorename, SetPattern, Custom Thumbnail, Auto PDF Preview, Progress Bar, Auto Cleanup, Metadata Replace, etc.

import os
import re
import uuid
import json
import logging
import threading
import requests
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from PIL import Image
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from pdf2image import convert_from_path

# === Configuration ===
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282
START_TIME = datetime.now()

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Flask for Render Keep-Alive ===
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot is running!"
def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# === Directories ===
os.makedirs("downloads", exist_ok=True)
os.makedirs("thumbnails", exist_ok=True)

# === File Paths ===
USERS_FILE = "users.json"
THUMBS_FILE = "thumbs.json"
METADATA_FILE = "metadata.json"

# === Loaders & Savers ===
def load_json(path): return json.load(open(path)) if os.path.exists(path) else {}
def save_json(path, data): json.dump(data, open(path, "w"), indent=2)

# === Globals ===
users = load_json(USERS_FILE)
thumbs = load_json(THUMBS_FILE)
metadata = load_json(METADATA_FILE)
autorename = {}
file_counter = 0
pattern = "{original}_{number}"

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

def download_thumb(url, path):
    r = requests.get(url)
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.save(path, "JPEG")

async def progress_bar(context, message, done_event):
    bar = ["⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜", ""]
    for i in range(1, 11):
        if done_event.is_set(): break
        bar[1] = bar[0][:i] + "🟩" + bar[0][i+1:]
        await message.edit_text(f"📦 Progress: `{bar[1]}`", parse_mode="Markdown")
        await asyncio.sleep(1)

async def cleanup_file(path):
    await asyncio.sleep(1800)
    if os.path.exists(path): os.remove(path)

# === Command Handlers ===
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
        caption="👋 *Welcome to File Renamer Bot!*\n\nSend a file, I'll rename or customize it as per your settings!\nUse /help for full command list.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📖 *Help Menu*

/setpattern <pattern> - Rename format
/seepattern - Show pattern
/delpattern - Reset pattern
/setthumburl <url> - Set Telegra.ph thumbnail
/seethumb - View current thumbnail
/deletethumb - Remove thumbnail
/setmetadata <@yourchannel> - Replace tags in filename
/autorename on|off - Auto rename
/stats - Bot stats (admin only)
/broadcast <text> - Send to all users (admin only)
    """, parse_mode="Markdown")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        await query.edit_message_caption(
            "📢 *About Us*\n\nMade for easy file renaming. Contact us: @YourChannelHere",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
        )
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

async def set_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if not context.args:
        await update.message.reply_text("❗ Usage: /setpattern <pattern>")
        return
    pattern = ' '.join(context.args)
    await update.message.reply_text(f"✅ Pattern set: `{pattern}`", parse_mode="Markdown")

async def seepattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🧾 Current Pattern: `{pattern}`", parse_mode="Markdown")

async def delpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    pattern = "{original}_{number}"
    await update.message.reply_text("♻️ Pattern reset to default.")

async def set_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setthumburl <Telegra.ph URL>")
        return
    url = context.args[0]
    if not url.startswith("https://telegra.ph"):
        await update.message.reply_text("❌ Only Telegra.ph images allowed.")
        return
    user_id = str(update.effective_user.id)
    thumbs[user_id] = url
    save_json(THUMBS_FILE, thumbs)
    download_thumb(url, f"thumbnails/{user_id}.jpg")
    await update.message.reply_text("✅ Thumbnail saved!")

async def seethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path):
        await update.message.reply_photo(photo=open(path, "rb"))
    else:
        await update.message.reply_text("ℹ️ No thumbnail set.")

async def deletethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs.pop(user_id, None)
    save_json(THUMBS_FILE, thumbs)
    path = f"thumbnails/{user_id}.jpg"
    if os.path.exists(path): os.remove(path)
    await update.message.reply_text("🗑️ Thumbnail deleted.")

async def set_metadata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /setmetadata <@channel>")
        return
    user_id = str(update.effective_user.id)
    metadata[user_id] = context.args[0]
    save_json(METADATA_FILE, metadata)
    await update.message.reply_text(f"✅ Metadata set to {context.args[0]}")

async def auto_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        status = autorename.get(user_id, False)
        await update.message.reply_text(f"⚙️ Autorename is currently {'ON' if status else 'OFF'}")
        return
    if context.args[0].lower() == "on":
        autorename[user_id] = True
        await update.message.reply_text("✅ Autorename enabled!")
    else:
        autorename[user_id] = False
        await update.message.reply_text("❌ Autorename disabled.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    uptime = str(datetime.now() - START_TIME).split('.')[0]
    await update.message.reply_text(f"📊 Uptime: {uptime}\n👥 Users: {len(users)}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = ' '.join(context.args)
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except: pass
    await update.message.reply_text("📢 Broadcast sent!")

# === File Handler ===
def is_video(name): return name.lower().endswith((".mp4", ".mkv", ".avi"))
def is_pdf(name): return name.lower().endswith(".pdf")

def replace_metadata(name, user_id):
    username = metadata.get(user_id)
    return re.sub(r"@\w+", username, name) if username else name

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    register_user(user_id)
    file = update.message.document or update.message.video
    if not file:
        await update.message.reply_text("❗ Send a file please.")
        return

    msg = await update.message.reply_text("⬇️ Downloading file...")
    name = file.file_name or "file"
    if autorename.get(user_id):
        name = generate_filename(name)
    else:
        name = replace_metadata(name, user_id)

    path = f"downloads/{uuid.uuid4().hex}_{name}"
    tg_file = await file.get_file()
    await tg_file.download_to_drive(path)

    done_event = asyncio.Event()
    asyncio.create_task(progress_bar(context, msg, done_event))
    await asyncio.sleep(2)

    thumb_path = f"thumbnails/{user_id}.jpg"
    thumb = open(thumb_path, "rb") if os.path.exists(thumb_path) else None

    if not thumb and is_pdf(name):
        try:
            img = convert_from_path(path, first_page=1)[0]
            img.save("temp.jpg", "JPEG")
            thumb = open("temp.jpg", "rb")
        except: pass

    try:
        if is_video(name):
            await context.bot.send_video(update.effective_chat.id, video=open(path, "rb"), caption=name, thumbnail=thumb, supports_streaming=True)
        else:
            await context.bot.send_document(update.effective_chat.id, document=open(path, "rb"), filename=name, caption=name, thumbnail=thumb)
        done_event.set()
        await msg.edit_text("✅ Done!")
    except Exception as e:
        done_event.set()
        await msg.edit_text(f"❌ Error: {e}")
    finally:
        if os.path.exists(path): asyncio.create_task(cleanup_file(path))
        if thumb: thumb.close()
        if os.path.exists("temp.jpg"): os.remove("temp.jpg")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("😵 Baka! I don't understand that command.")

# === Main ===
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("setpattern", set_pattern))
    app.add_handler(CommandHandler("seepattern", seepattern))
    app.add_handler(CommandHandler("delpattern", delpattern))
    app.add_handler(CommandHandler("setthumburl", set_thumb))
    app.add_handler(CommandHandler("seethumb", seethumb))
    app.add_handler(CommandHandler("deletethumb", deletethumb))
    app.add_handler(CommandHandler("autorename", auto_rename))
    app.add_handler(CommandHandler("setmetadata", set_metadata))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling(drop_pending_updates=True)
