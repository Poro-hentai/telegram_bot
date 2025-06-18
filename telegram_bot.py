import os
import json
from flask import Flask
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)

BOT_TOKEN = "7657397566:AAFKTEJnkSljny1wzRFF3NJHEtV3fKbTpDA"
DATA_FILE = "channels.json"

app = Flask(__name__)

# Load or initialize data
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
        [InlineKeyboardButton("📢 My Channels", callback_data="my_channels")],
        [InlineKeyboardButton("📝 Post to Channel", callback_data="post")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await update.message.reply_text("👋 Welcome to Controller Bot!\nChoose an action below:", reply_markup=btn)

# Handle callback buttons
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if query.data == "add_channel":
        context.user_data["awaiting_channel"] = True
        await query.edit_message_text("📨 Send your channel username (e.g., @mychannel):")
    elif query.data == "my_channels":
        data = load_data()
        channels = data.get(user_id, [])
        text = "\n".join(channels) if channels else "❌ No channels added."
        await query.edit_message_text(f"📢 Your Channels:\n{text}")
    elif query.data == "post":
        context.user_data["awaiting_post"] = True
        await query.edit_message_text("📝 Send the message you want to post to all your channels:")
    elif query.data == "close":
        await query.message.delete()

# Handle text for channel input and post message
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = load_data()

    # Add channel
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
            await update.message.reply_text("⚠️ Channel already added.")
        context.user_data["awaiting_channel"] = False

    # Post message
    elif context.user_data.get("awaiting_post"):
        message = update.message.text
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶ Watch Now", url="https://t.me/yourchannel")],
            [InlineKeyboardButton("❤️ Like", callback_data="like")]
        ])
        sent_count = 0
        for ch in data.get(user_id, []):
            try:
                await context.bot.send_message(chat_id=ch, text=message, reply_markup=btn)
                sent_count += 1
            except Exception as e:
                await update.message.reply_text(f"⚠️ Failed to post to {ch}.\n{e}")
        await update.message.reply_text(f"✅ Posted to {sent_count} channel(s).")
        context.user_data["awaiting_post"] = False

# Like button handler
async def like_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("❤️ Thanks for liking!")

# Flask route
@app.route('/')
def home():
    return "Bot is Live!"

# Main bot + flask run
if __name__ == "__main__":
    from telegram.ext import ApplicationBuilder
    import threading

    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CallbackQueryHandler(handle_callback, pattern="^(add_channel|my_channels|post|close)$"))
    app_bot.add_handler(CallbackQueryHandler(like_callback, pattern="^like$"))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))

    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": int(os.environ.get("PORT", 5000))}).start()
    app_bot.run_polling()
