import os
import json
import uuid
import logging
import requests
from PIL import Image
from flask import Flask
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from pdf2image import convert_from_path

# === Configuration ===
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()

# === JSON helpers ===
def load_json(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

patterns = load_json("patterns.json")
thumbnails = load_json("thumbs.json")
AUTO_RENAME = False

# === Utilities ===
def extract_episode(filename):
    import re
    match = re.search(r"(?:CH|Ep|EP|E)?\s*(\d{1,3})", filename, re.IGNORECASE)
    return match.group(1) if match else "01"

def generate_pdf_thumb(path):
    try:
        img = convert_from_path(path, first_page=1, last_page=1)[0]
        thumb_path = f"thumb_{uuid.uuid4()}.jpg"
        img.save(thumb_path, "JPEG")
        return thumb_path
    except Exception as e:
        logging.error("PDF Thumb Error: %s", e)
        return None

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("About", callback_data="about"), InlineKeyboardButton("Help", callback_data="help")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    await update.message.reply_photo(
        photo="https://telegra.ph/file/050a20dace942a60220c0.jpg",
        caption="""👋 <b>Welcome to File Renamer Bot</b>

• Send me any file.
• I'll help you rename it.
• Admin can use pattern, auto-rename, and thumbnail commands.

Use buttons below to learn more.
        """,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    users = load_json("users.json")
    users[str(update.message.from_user.id)] = True
    save_json("users.json", users)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "close":
        await q.message.delete()
    elif q.data == "about":
        await q.message.edit_caption(
            caption="""📌 <b>About:</b>
I rename files, generate thumbnails, extract PDF previews, and more!

<a href='https://t.me/yourchannel'>📣 Join our Channel</a>""",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
    elif q.data == "help":
        await q.message.edit_caption(
            caption="""ℹ️ <b>Help Menu</b>:

1. Send me any file.
2. /setpattern {filename} or {episode}
3. /autorename to toggle auto renaming
4. /thumburl <image_url>
        """,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
    elif q.data == "back":
        await start(update, context)

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid != str(ADMIN_ID):
        return await update.message.reply_text("Baka! You are not my senpai ✋")
    if not context.args:
        return await update.message.reply_text("Use: /setpattern {pattern}")
    patterns[uid] = " ".join(context.args)
    save_json("patterns.json", patterns)
    await update.message.reply_text(f"✅ Pattern set to: `{patterns[uid]}`", parse_mode='Markdown')

async def autorename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AUTO_RENAME
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("Baka! You are not my senpai ✋")
    AUTO_RENAME = not AUTO_RENAME
    await update.message.reply_text(f"✅ Auto Rename is now: {'ON' if AUTO_RENAME else 'OFF'}")

async def thumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid != str(ADMIN_ID):
        return await update.message.reply_text("Baka! You are not my senpai ✋")
    if not context.args:
        return await update.message.reply_text("Send image URL")
    try:
        img = Image.open(requests.get(context.args[0], stream=True).raw)
        path = f"thumb_{uid}.jpg"
        img.save(path)
        thumbnails[uid] = path
        save_json("thumbs.json", thumbnails)
        await update.message.reply_text("✅ Thumbnail set successfully.")
    except Exception as e:
        await update.message.reply_text("Failed to set thumbnail.")
        logging.error("Thumbnail error: %s", e)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    uid = str(user.id)
    media = update.message.document or update.message.video or update.message.audio or update.message.photo[-1]
    file = await media.get_file()
    original_name = getattr(media, "file_name", f"file_{uuid.uuid4()}.mp4")
    episode = extract_episode(original_name)
    pattern = patterns.get(uid, "{filename}")
    new_name = pattern.replace("{episode}", episode).replace("{filename}", os.path.splitext(original_name)[0])
    downloaded = await file.download_to_drive(new_name)

    thumb = None
    if original_name.lower().endswith(".pdf"):
        thumb = generate_pdf_thumb(downloaded)
    elif uid in thumbnails:
        thumb = thumbnails[uid]

    await update.message.reply_document(
        document=InputFile(downloaded),
        filename=new_name,
        caption=f"{new_name}",
        parse_mode='Markdown',
        thumb=InputFile(thumb) if thumb else None
    )
    os.remove(downloaded)
    if thumb and thumb.startswith("thumb_"):
        os.remove(thumb)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("Baka! You are not my senpai ✋")
    if not context.args:
        return await update.message.reply_text("Use: /broadcast Your message")
    text = " ".join(context.args)
    users = load_json("users.json")
    count = 0
    for uid in users:
        try:
            await bot_app.bot.send_message(chat_id=uid, text=text)
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {count} users!")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Use /start")

# === Web App ===
@app.route("/")
def home():
    return "🤖 Bot is alive!"

@app.route("/restart")
def restart():
    return "🔄 Bot restarted by Shadow"

# === Register Handlers ===
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("setpattern", setpattern))
bot_app.add_handler(CommandHandler("autorename", autorename))
bot_app.add_handler(CommandHandler("thumburl", thumburl))
bot_app.add_handler(CommandHandler("broadcast", broadcast))
bot_app.add_handler(CallbackQueryHandler(callback_handler))
bot_app.add_handler(MessageHandler(
    filters.Document.ALL | filters.VIDEO | filters.Audio | filters.PHOTO,
    handle_file
))
bot_app.add_handler(MessageHandler(filters.COMMAND, unknown))

# === Run Bot ===
if __name__ == '__main__':
    import threading
    threading.Thread(target=lambda: bot_app.run_polling()).start()
    app.run(host="0.0.0.0", port=10000)
