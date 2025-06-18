import os
import json
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

BOT_TOKEN = "7657397566:AAFKTEJnkSljny1wzRFF3NJHEtV3fKbTpDA"
DATA_FILE = "channels.json"

app = Flask(__name__)

# Data Functions
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    if not data.get(user_id):
        await update.message.reply_text("❌ No channels found. Please add a channel first by using ➕ Add Channel.")
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
        [InlineKeyboardButton("📢 My Channels", callback_data="my_channels")],
        [InlineKeyboardButton("📝 Create Post", callback_data="create_post")],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ])
    await update.message.reply_text("👋 Welcome to Controller Bot Clone!\nChoose an action:", reply_markup=btn)

# Callback handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = load_data()

    if query.data == "add_channel":
        context.user_data.clear()
        context.user_data["awaiting_channel"] = True
        await query.edit_message_text("Send your channel username (e.g., @mychannel):")

    elif query.data == "my_channels":
        channels = data.get(user_id, [])
        text = "\n".join(channels) if channels else "❌ No channels added."
        await query.edit_message_text(f"📢 Your Channels:\n{text}")

    elif query.data == "create_post":
        if not data.get(user_id):
            await query.edit_message_text("❌ Please add at least one channel before creating a post.")
            return
        context.user_data.clear()
        context.user_data["step"] = "choose_channel"
        btns = [[InlineKeyboardButton(ch, callback_data=f"select_{ch}")] for ch in data[user_id]]
        await query.edit_message_text("Select channel to post:", reply_markup=InlineKeyboardMarkup(btns))

    elif query.data == "close":
        await query.message.delete()

    elif query.data.startswith("select_"):
        channel = query.data.replace("select_", "")
        context.user_data["post_channel"] = channel
        context.user_data["step"] = "awaiting_post"
        await query.edit_message_text("Send the message you want to post (text, image, or video):")

    elif query.data == "confirm_post":
        channel = context.user_data.get("post_channel")
        msg = context.user_data.get("preview")
        btn = context.user_data.get("keyboard")
        media = context.user_data.get("media")
        try:
            if media:
                await context.bot.send_photo(chat_id=channel, photo=media, caption=msg, reply_markup=btn)
            else:
                await context.bot.send_message(chat_id=channel, text=msg, reply_markup=btn)
            await query.edit_message_text("✅ Post sent successfully!")
        except Exception as e:
            await query.edit_message_text(f"❌ Failed to send post.\n{e}")

    elif query.data == "cancel_post":
        await query.edit_message_text("❌ Post cancelled.")

# Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()

    if context.user_data.get("awaiting_channel"):
        channel = update.message.text.strip()
        if not channel.startswith("@"):  
            await update.message.reply_text("❌ Invalid format. Must start with @")
            return
        data.setdefault(user_id, [])
        if channel not in data[user_id]:
            data[user_id].append(channel)
            save_data(data)
            await update.message.reply_text(f"✅ Channel {channel} added.")
        else:
            await update.message.reply_text("⚠️ Channel already exists.")
        context.user_data.clear()
        return

    if context.user_data.get("step") == "awaiting_post":
        context.user_data["step"] = "awaiting_button"
        context.user_data["media"] = None
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            context.user_data["media"] = file_id
        elif update.message.video:
            file_id = update.message.video.file_id
            context.user_data["media"] = file_id

        context.user_data["preview"] = update.message.caption or update.message.text
        await update.message.reply_text(
            "Now send button text and URL in this format:\n\n```
Button 1 - https://link1.com\nButton 2 - https://link2.com
```\n\nSend `skip` to continue without buttons.",
            parse_mode="Markdown"
        )
        return

    if context.user_data.get("step") == "awaiting_button":
        btn_text = update.message.text
        keyboard = []

        if btn_text.lower() != "skip":
            for line in btn_text.strip().split("\n"):
                if " - " in line:
                    text, url = line.split(" - ", 1)
                    keyboard.append([InlineKeyboardButton(text.strip(), url=url.strip())])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        context.user_data["keyboard"] = reply_markup

        msg = context.user_data["preview"]
        media = context.user_data.get("media")

        if media:
            await update.message.reply_photo(photo=media, caption=msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg, reply_markup=reply_markup)

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_post"),
             InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
        ])
        await update.message.reply_text("Do you want to post this to the selected channel?", reply_markup=btn)
        context.user_data["step"] = "preview_done"

@app.route("/")
def home():
    return "Bot is running"

if __name__ == '__main__':
    from telegram.ext import ApplicationBuilder
    import threading

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, handle_message))

    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": int(os.environ.get("PORT", 5000))}).start()
    application.run_polling()
