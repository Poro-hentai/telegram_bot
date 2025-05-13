import os
import re
import uuid
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

# Globals
pattern = "{original}"
counter = 1
file_counter = 0
user_thumbnail = None

def generate_filename(original_name):
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp4"
    new_name = pattern.replace("{number}", str(file_counter)).replace("{original}", base)
    return f"{new_name}{ext}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to the File Renamer Bot!*\n\n"
        "📂 Rename incoming files using a custom pattern.\n\n"
        "📌 *Commands:*\n"
        "`/setpattern pattern` - Set rename pattern (use `{number}` and `{original}`)\n"
        "`/reset` - Reset counter to 1\n"
        "`/setthumb` - Send an image (jpg/png) to use as thumbnail\n",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Rename pattern set to: `{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Usage: /setpattern newname_{number}_{original}")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global counter, file_counter
    counter = 1
    file_counter = 0
    await update.message.reply_text("🔁 Counter reset to 1.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Thumbnail has been set successfully!")
    else:
        await update.message.reply_text("⚠️ Please send a JPG/PNG image.")

def is_video_file(file_name):
    return file_name.lower().endswith(('.mp4', '.mkv', '.mov'))

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        file = message.document or message.video
        if not file:
            return

        await message.reply_text("📥 Downloading...")

        telegram_file = await file.get_file()
        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)
        local_path = f"{uuid.uuid4().hex}_{original_name}"
        await telegram_file.download_to_drive(local_path)

        if is_video_file(original_name):
            buttons = [[
                InlineKeyboardButton("🎬 Send as Video", callback_data=f"video||{local_path}||{new_name}"),
                InlineKeyboardButton("📄 Send as Document", callback_data=f"doc||{local_path}||{new_name}")
            ]]
        else:
            buttons = [[InlineKeyboardButton("📄 Send File", callback_data=f"doc||{local_path}||{new_name}")]]
        
        await message.reply_text(
            "✅ File downloaded. Choose send method:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error while handling file: {e}")

async def send_file(context, chat_id, file_path, new_name, as_video):
    caption = f"`{new_name}`"
    try:
        thumb = user_thumbnail if user_thumbnail and as_video else None

        if not os.path.exists(file_path):
            await context.bot.send_message(chat_id=chat_id, text="❌ File no longer exists.")
            return

        if as_video:
            await context.bot.send_video(
                chat_id=chat_id,
                video=open(file_path, "rb"),
                caption=caption,
                thumb=open(thumb, "rb") if thumb else None,
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_document(
                chat_id=chat_id,
                document=open(file_path, "rb"),
                filename=new_name,
                caption=caption,
                parse_mode="Markdown"
            )

        await context.bot.send_message(chat_id=chat_id, text=f"✅ Renamed to: `{new_name}`", parse_mode="Markdown")

        os.remove(file_path)
        if thumb:
            try: os.remove(thumb)
            except: pass
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed to send file: `{e}`", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        mode, file_path, new_name = query.data.split("||")
        as_video = (mode == "video")
        await query.edit_message_text("📤 Uploading...")
        await send_file(context, query.message.chat.id, file_path, new_name, as_video)
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")

# --- MAIN ---
if __name__ == "__main__":
    import asyncio
    TOKEN = "YOUR_BOT_TOKEN"  # Replace this
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, set_thumbnail))

    print("🚀 Bot is running...")
    app.run_polling()
