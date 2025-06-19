# ✅ FINAL ENHANCED VERSION - FILE RENAMER BOT with AUTORENAME, THUMB, BROADCAST, AUTH, ETC.
# Compatible with Render.com, python-telegram-bot v20.7, Flask

import os
import json
import logging
import fitz  # PyMuPDF
import requests
from flask import Flask, request
from telegram import (Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.ext import (Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler)
from telegram.constants import ChatAction

BOT_TOKEN = '7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM'
ADMIN_ID = 5759232282  # Change to your Telegram ID
THUMB_DIR = 'downloads'
DATA_FILE = 'users.json'

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Create folder if not exists
os.makedirs(THUMB_DIR, exist_ok=True)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user_data(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {"pattern": "{filename}", "thumb_url": "", "autorename": False}
        save_data(data)
    return data[user_id]

def update_user_data(user_id, key, value):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {"pattern": "{filename}", "thumb_url": "", "autorename": False}
    data[user_id][key] = value
    save_data(data)

def extract_episode_from_name(name):
    import re
    match = re.search(r'[eE]p?(\d+)', name)
    return f"Ep{match.group(1)}" if match else "Episode"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btns = [[
        InlineKeyboardButton("About", callback_data='about'),
        InlineKeyboardButton("Help", callback_data='help')
    ], [InlineKeyboardButton("Close", callback_data='close')]]
    await update.message.reply_photo(
        photo='https://telegra.ph/file/050a20dace942a60220c0.jpg',
        caption="👋 Welcome to the File Renamer Bot!\nUse /setpattern to customize filename.\nSend any file to rename.",
        reply_markup=InlineKeyboardMarkup(btns))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "about":
        btns = [[InlineKeyboardButton("Back", callback_data='back')]]
        await query.edit_message_media(media=InputFile.from_url('https://telegra.ph/file/9d18345731db88fff4f8c.jpg'))
        await query.edit_message_caption("ℹ️ <b>About:</b>\nThis bot renames files with custom patterns.", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(btns))
    elif query.data == "help":
        btns = [[InlineKeyboardButton("Back", callback_data='back')]]
        await query.edit_message_media(media=InputFile.from_url('https://telegra.ph/file/e6ec31fc792d072da2b7e.jpg'))
        await query.edit_message_caption("🛠️ Send a file, and it'll be renamed!\n/setpattern - custom name\n/setthumburl - set thumbnail", reply_markup=InlineKeyboardMarkup(btns))
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = ' '.join(context.args)
    if not pattern:
        await update.message.reply_text("❌ Usage: /setpattern My Anime {episode}")
        return
    update_user_data(update.effective_user.id, "pattern", pattern)
    await update.message.reply_text(f"✅ Pattern set to: `{pattern}`", parse_mode='Markdown')

async def setthumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /setthumburl https://link.to/image.jpg")
        return
    url = context.args[0]
    update_user_data(update.effective_user.id, "thumb_url", url)
    await update.message.reply_text("✅ Thumbnail URL set!")

async def deletethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_user_data(update.effective_user.id, "thumb_url", "")
    await update.message.reply_text("🗑️ Thumbnail deleted!")

async def seethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(update.effective_user.id)
    thumb = data.get("thumb_url")
    if thumb:
        await update.message.reply_photo(thumb, caption="📸 Your thumbnail")
    else:
        await update.message.reply_text("❌ No thumbnail set.")

async def autorename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_data(user_id).get("autorename", False)
    update_user_data(user_id, "autorename", not state)
    await update.message.reply_text(f"🔄 AutoRename: {'Enabled' if not state else 'Disabled'}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document or update.message.video or update.message.audio or update.message.photo[-1]
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    pattern = user_data.get("pattern", "{filename}")
    filename = update.message.document.file_name if update.message.document else "file"
    if user_data.get("autorename"):
        episode = extract_episode_from_name(filename)
        new_name = pattern.replace("{episode}", episode) + os.path.splitext(filename)[1]
    else:
        new_name = pattern.replace("{filename}", os.path.splitext(filename)[0]) + os.path.splitext(filename)[1]
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    new_file = await file.get_file()
    downloaded = await new_file.download_to_drive(os.path.join(THUMB_DIR, new_name))
    thumb_path = None
    if filename.lower().endswith('.pdf'):
        try:
            doc = fitz.open(downloaded)
            pix = doc[0].get_pixmap()
            thumb_path = os.path.join(THUMB_DIR, f"{new_name}.jpg")
            pix.save(thumb_path)
        except Exception:
            thumb_path = None
    elif user_data.get("thumb_url"):
        try:
            r = requests.get(user_data['thumb_url'])
            thumb_path = os.path.join(THUMB_DIR, f"{user_id}.jpg")
            with open(thumb_path, 'wb') as f:
                f.write(r.content)
        except:
            thumb_path = None
    await update.message.reply_document(document=InputFile(downloaded), filename=new_name, thumb=InputFile(thumb_path) if thumb_path else None, caption=f"✅ Renamed to: `{new_name}`", parse_mode='Markdown')

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("😡 Baka! You are not my Senpai.")
        return
    msg = ' '.join(context.args)
    if not msg:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    data = load_data()
    for uid in data.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
        except:
            pass
    await update.message.reply_text("✅ Broadcast sent.")

# Webhook route (Render needs this)
@app.route('/')
def index():
    return "Running"

if __name__ == '__main__':
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler('start', start))
    bot_app.add_handler(CommandHandler('setpattern', setpattern))
    bot_app.add_handler(CommandHandler('setthumburl', setthumburl))
    bot_app.add_handler(CommandHandler('seethumb', seethumb))
    bot_app.add_handler(CommandHandler('deletethumb', deletethumb))
    bot_app.add_handler(CommandHandler('autorename', autorename))
    bot_app.add_handler(CommandHandler('broadcast', broadcast))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    bot_app.add_handler(MessageHandler(filters.Document.ALL | filters.Audio.ALL | filters.PHOTO, handle_file))

    bot_app.run_polling()
    app.run(host='0.0.0.0', port=10000)
