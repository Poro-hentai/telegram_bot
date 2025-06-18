import os
import json
import uuid
from flask import Flask
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = "7657397566:AAFKTEJnkSljny1wzRFF3NJHEtV3fKbTpDA"
DATA_FILE = "channels.json"

app = Flask(__name__)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
        [InlineKeyboardButton("📢 My Channels", callback_data="my_channels")],
        [InlineKeyboardButton("📝 Create Post", callback_data="create_post")],
        [InlineKeyboardButton("ℹ Help", callback_data="help")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    await update.message.reply_text("👋 Welcome to Controller Bot!\nManage your channels and create posts easily.", reply_markup=btn)

# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Bot Commands:*\n"
        "/start - Open main menu\n"
        "/help - Show help info\n\n"
        "*Steps to Post:*\n"
        "1. Add your channel\n"
        "2. Click 'Create Post'\n"
        "3. Choose a channel\n"
        "4. Send your media or message\n"
        "5. Provide button links (Format: `Text - URL`)\n"
        "6. Confirm to post",
        parse_mode="Markdown"
    )

# Button callbacks
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()

    if query.data == "add_channel":
        context.user_data["awaiting_channel"] = True
        await query.edit_message_text("Send your channel username (e.g., @mychannel):")

    elif query.data == "my_channels":
        data = load_data()
        channels = data.get(user_id, [])
        text = "\n".join(channels) if channels else "❌ No channels added."
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        await query.edit_message_text(f"📢 Your Channels:\n{text}", reply_markup=btn)

    elif query.data == "create_post":
        data = load_data()
        channels = data.get(user_id, [])
        if not channels:
            await query.edit_message_text("⚠️ You have no channels. Please add one first.")
            return
        buttons = [[InlineKeyboardButton(ch, callback_data=f"post_to|{ch}")] for ch in channels]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        await query.edit_message_text("Select channel to post:", reply_markup=InlineKeyboardMarkup(buttons))

    elif query.data.startswith("post_to|"):
        ch = query.data.split("|")[1]
        context.user_data["target_channel"] = ch
        context.user_data["awaiting_post"] = True
        await query.edit_message_text(f"📤 Now send your post (text or media) to post on {ch}.")

    elif query.data == "confirm_post":
        channel = context.user_data.get("target_channel")
        media = context.user_data.get("post_content")
        markup = context.user_data.get("buttons")
        try:
            if isinstance(media, tuple):
                file_id, caption = media
                await context.bot.send_photo(channel, photo=file_id, caption=caption, reply_markup=markup)
            else:
                await context.bot.send_message(channel, text=media, reply_markup=markup)
            await query.edit_message_text("✅ Post sent successfully.")
        except Exception as e:
            await query.edit_message_text(f"⚠️ Failed to post.\n{e}")
        context.user_data.clear()

    elif query.data == "cancel_post":
        context.user_data.clear()
        await query.edit_message_text("❌ Post creation canceled.")

    elif query.data == "help":
        await help_command(update, context)

    elif query.data == "close":
        await query.message.delete()

    elif query.data == "back":
        await start(update, context)

# Button input parser
def parse_buttons(text):
    lines = text.strip().splitlines()
    rows, row = [], []
    for line in lines:
        if "-" not in line: continue
        parts = line.split("-", 1)
        if len(parts) != 2: continue
        label, link = parts[0].strip(), parts[1].strip()
        row.append(InlineKeyboardButton(label, url=link))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

# Channel addition / posting
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = load_data()

    if context.user_data.get("awaiting_channel"):
        ch = update.message.text.strip()
        if not ch.startswith("@"):
            await update.message.reply_text("❌ Invalid format. Use @channelusername.")
            return
        data.setdefault(user_id, [])
        if ch not in data[user_id]:
            data[user_id].append(ch)
            save_data(data)
            await update.message.reply_text(f"✅ Channel {ch} added.")
        else:
            await update.message.reply_text("⚠️ Channel already exists.")
        context.user_data["awaiting_channel"] = False

    elif context.user_data.get("awaiting_post"):
        msg = update.message
        if msg.photo:
            file_id = msg.photo[-1].file_id
            caption = msg.caption or ""
            context.user_data["post_content"] = (file_id, caption)
        else:
            context.user_data["post_content"] = msg.text
        context.user_data["awaiting_buttons"] = True
        await update.message.reply_text("✅ Got your post.\nNow send buttons like this:\n\nText - URL\nText - URL")

    elif context.user_data.get("awaiting_buttons"):
        btn_markup = parse_buttons(update.message.text)
        context.user_data["buttons"] = btn_markup
        preview = "Here's your post preview. Confirm to send."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_post")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
        ])
        content = context.user_data.get("post_content")
        if isinstance(content, tuple):
            file_id, caption = content
            await update.message.reply_photo(file_id, caption=caption, reply_markup=btn_markup)
        else:
            await update.message.reply_text(content, reply_markup=btn_markup)
        await update.message.reply_text(preview, reply_markup=keyboard)
        context.user_data["awaiting_buttons"] = False

    else:
        await update.message.delete()

@app.route("/")
def home():
    return "Bot is running!"

if __name__ == "__main__":
    import threading
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.PRIVATE, handle_text))
    app_bot.add_handler(MessageHandler(filters.PHOTO & filters.PRIVATE, handle_text))

    threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": int(os.environ.get("PORT", 5000))}).start()
    app_bot.run_polling()
