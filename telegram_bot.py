import os
import json
import requests
from flask import Flask, request as flask_request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ChatAction

TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
ADMIN_ID = 5759232282

app = Flask(__name__)

# JSON file paths
THUMB_FILE = "thumbs.json"
PATTERN_FILE = "patterns.json"

# Load or initialize JSON
for file in [THUMB_FILE, PATTERN_FILE]:
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump({}, f)

# Load data

def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("About", callback_data="about"), InlineKeyboardButton("Help", callback_data="help")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ]
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo="https://telegra.ph/file/050a20dace942a60220c0.jpg",
        caption="\u2728 <b>Welcome to the File Renamer Bot</b>\nUse /setpattern and /setthumburl to configure.\nEnjoy fast renaming and thumbnails.\nJoin <a href='https://t.me/yourchannel'>Our Channel</a>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# BUTTON HANDLER
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "about":
        buttons = [[InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]]
        await query.edit_message_media(
            media=InputMediaPhoto(
                media="https://telegra.ph/file/9d18345731db88fff4f8c.jpg",
                caption="<b>About Us</b>\n<a href='https://t.me/yourchannel'>Channel</a> | <a href='https://t.me/support'>Support</a>",
                parse_mode="HTML"
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "help":
        buttons = [[InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]]
        await query.edit_message_media(
            media=InputMediaPhoto(
                media="https://telegra.ph/file/e6ec31fc792d072da2b7e.jpg",
                caption="\u2753 <b>Help</b>\nUse /setpattern to set filename\n/setthumburl to set thumbnail from image URL.",
                parse_mode="HTML"
            ),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif query.data == "back":
        await start(update, context)
    elif query.data == "close":
        await query.message.delete()

# SETPATTERN
async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    pattern = " ".join(context.args)
    data = load_json(PATTERN_FILE)
    data[user_id] = pattern
    save_json(PATTERN_FILE, data)
    await update.message.reply_text("✅ Pattern saved successfully!")

# SETTHUMBURL
async def setthumburl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    url = " ".join(context.args)
    thumbs = load_json(THUMB_FILE)
    thumbs[user_id] = url
    save_json(THUMB_FILE, thumbs)
    await update.message.reply_text("✅ Thumbnail URL saved!")

# SEETHUMB
async def seethumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    thumbs = load_json(THUMB_FILE)
    if user_id in thumbs:
        await update.message.reply_photo(photo=thumbs[user_id], caption="This is your saved thumbnail.")
    else:
        await update.message.reply_text("❌ No thumbnail found.")

# BROADCAST
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = update.message.reply_to_message
    if not msg:
        await update.message.reply_text("Reply to a message to broadcast.")
        return

    with open("users.json", "r") as f:
        users = json.load(f)

    count = 0
    for uid in users:
        try:
            await msg.copy(chat_id=int(uid))
            count += 1
        except:
            continue
    await update.message.reply_text(f"Broadcasted to {count} users.")

# HANDLE FILE
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    file = update.message.document or update.message.video
    file_name = file.file_name

    patterns = load_json(PATTERN_FILE)
    new_name = patterns.get(user_id, file_name)

    thumbs = load_json(THUMB_FILE)
    thumb = thumbs.get(user_id)

    await update.message.chat.send_action(action=ChatAction.UPLOAD_DOCUMENT)
    await file.get_file().download_to_drive(file_name)
    with open(file_name, "rb") as f:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=f,
            filename=new_name,
            caption=f"Here is your renamed file: <code>{new_name}</code>",
            parse_mode="HTML",
            thumb=thumb if thumb else None
        )
    os.remove(file_name)

    # Save user to users.json
    if not os.path.exists("users.json"):
        with open("users.json", "w") as f:
            json.dump({}, f)
    with open("users.json", "r") as f:
        users = json.load(f)
    if user_id not in users:
        users[user_id] = True
        with open("users.json", "w") as f:
            json.dump(users, f, indent=2)

# MAIN
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button))
application.add_handler(CommandHandler("setpattern", setpattern))
application.add_handler(CommandHandler("setthumburl", setthumburl))
application.add_handler(CommandHandler("seethumb", seethumb))
application.add_handler(CommandHandler("broadcast", broadcast))
application.add_handler(MessageHandler(filters.Document.ALL | filters.Video, handle_file))

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

def run():
    application.run_polling()

if __name__ == '__main__':
    run()
    app.run(host="0.0.0.0", port=10000)
