import os
import json
import requests
import logging
from flask import Flask, request as flask_request
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile)
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters)

app = Flask(__name__)
TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282  # Change to your Telegram user ID
USERS_FILE = "users.json"

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({}, f)

def save_user_data(user_id, key, value):
    with open(USERS_FILE, "r") as f:
        data = json.load(f)
    if str(user_id) not in data:
        data[str(user_id)] = {}
    data[str(user_id)][key] = value
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user_data(user_id, key, default=None):
    with open(USERS_FILE, "r") as f:
        data = json.load(f)
    return data.get(str(user_id), {}).get(key, default)

@app.route("/")
def index():
    return "Bot is running"

# Telegram Bot Setup
bot_app = Application.builder().token(TOKEN).build()

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("About", callback_data="about"),
         InlineKeyboardButton("Help", callback_data="help")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    await update.message.reply_photo(
        photo="https://telegra.ph/file/050a20dace942a60220c0.jpg",
        caption="\u2728 *Welcome to File Renamer Bot!*\n\nUse this bot to rename files with custom captions and thumbnails.\n\nJoin our [Channel](https://t.me/example) for updates!",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

# Callback for Start Menu
async def buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "about":
        await query.edit_message_media(
            media=InputFile.from_url("https://telegra.ph/file/9d18345731db88fff4f8c.jpg"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]
            ])
        )
    elif data == "help":
        await query.edit_message_media(
            media=InputFile.from_url("https://telegra.ph/file/e6ec31fc792d072da2b7e.jpg"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]
            ])
        )
    elif data == "back":
        await start(update, context)
    elif data == "close":
        await query.message.delete()

# Set Pattern
async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pattern = " ".join(context.args)
    if pattern:
        save_user_data(update.effective_user.id, "pattern", pattern)
        await update.message.reply_text("✅ Pattern set successfully!")
    else:
        await update.message.reply_text("❌ Please provide a pattern after /setpattern")

# Set Thumbnail URL
async def setthumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        thumb_url = context.args[0]
        try:
            res = requests.get(thumb_url)
            if res.status_code == 200:
                save_user_data(update.effective_user.id, "thumb_url", thumb_url)
                await update.message.reply_text("✅ Thumbnail URL set successfully!")
            else:
                await update.message.reply_text("❌ Invalid image URL.")
        except:
            await update.message.reply_text("❌ Error downloading image.")
    else:
        await update.message.reply_text("❌ Please provide a URL after /setthumburl")

# See Current Thumbnail
async def seethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thumb_url = get_user_data(update.effective_user.id, "thumb_url")
    if thumb_url:
        await update.message.reply_photo(photo=thumb_url, caption="🖼️ Your current thumbnail")
    else:
        await update.message.reply_text("❌ No thumbnail set")

# Broadcast
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ You are not authorized.")
    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("❌ Provide text after /broadcast")

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    count = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            count += 1
        except:
            continue
    await update.message.reply_text(f"✅ Broadcast sent to {count} users")

# File Handler
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    file = update.message.document or update.message.video
    if not file:
        return

    await_msg = await update.message.reply_text("📥 Downloading...")

    file_path = await file.get_file()
    filename = file.file_name
    pattern = get_user_data(user.id, "pattern")
    new_name = pattern.format(filename=filename) if pattern else filename

    thumb_url = get_user_data(user.id, "thumb_url")
    thumb = InputFile.from_url(thumb_url) if thumb_url else None

    await await_msg.delete()
    await update.message.reply_document(document=file.file_id, filename=new_name, caption=new_name, thumb=thumb)

# Register Handlers
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(buttons_callback))
bot_app.add_handler(CommandHandler("setpattern", setpattern))
bot_app.add_handler(CommandHandler("setthumburl", setthumburl))
bot_app.add_handler(CommandHandler("seethumb", seethumb))
bot_app.add_handler(CommandHandler("broadcast", broadcast))
bot_app.add_handler(MessageHandler(filters.Document.ALL | filters.Video | filters.Audio | filters.Photo, handle_file))

if __name__ == "__main__":
    import threading
    threading.Thread(target=bot_app.run_polling).start()
    app.run(host="0.0.0.0", port=10000)
