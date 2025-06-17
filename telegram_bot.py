import os
import uuid
import logging
import threading
import asyncio
from flask import Flask
from telegram import Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO)

pattern = "{original}"
file_counter = 0
user_thumbnail = {}  # user_id: file_path
admin_id = 5759232282  # Your Telegram user ID for admin-only features

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def generate_filename(original_name):
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".mp4"
    return pattern.replace("{number}", str(file_counter)).replace("{original}", base) + ext

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to File Renamer Bot!*\n\n"
        "📁 Send any file, and I'll rename it using your custom pattern.\n\n"
        "🛠️ Commands:\n"
        "`/setpattern` - Set rename pattern (use `{original}`, `{number}`)\n"
        "`/reset` - Reset serial counter\n"
        "`/setthumb` - Set default thumbnail (works for any file)\n"
        "`/getthumb` - Get current thumbnail\n"
        "`/delthumb` - Delete current thumbnail\n"
        "`/broadcast` - Admin only broadcast",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Pattern set to:\n`{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❗ Usage: /setpattern Series S01 - {number}")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔁 Counter reset.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        photo = update.message.photo[-1]
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail[user_id] = thumb_path
        await update.message.reply_text("✅ Thumbnail set for your uploads.")
    elif update.message.document and update.message.document.mime_type.startswith("image"):
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        file = await update.message.document.get_file()
        await file.download_to_drive(thumb_path)
        user_thumbnail[user_id] = thumb_path
        await update.message.reply_text("✅ Thumbnail set for your uploads.")
    else:
        await update.message.reply_text("❗ Send a valid image file (JPG/PNG).")

async def get_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_thumbnail and os.path.exists(user_thumbnail[user_id]):
        await update.message.reply_photo(photo=InputFile(user_thumbnail[user_id]), caption="🖼️ Your current thumbnail")
    else:
        await update.message.reply_text("❗ No thumbnail set.")

async def delete_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_thumbnail:
        try:
            os.remove(user_thumbnail[user_id])
        except:
            pass
        del user_thumbnail[user_id]
        await update.message.reply_text("🗑️ Thumbnail deleted.")
    else:
        await update.message.reply_text("❗ No thumbnail to delete.")

def is_video_file(name):
    return name.lower().endswith((".mp4", ".mkv", ".mov"))

def is_pdf_file(name):
    return name.lower().endswith(".pdf")

async def auto_delete(bot, message, delay=10):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        file = message.document or message.video
        if not file:
            return

        status = await message.reply_text("⬇️ Downloading...")
        asyncio.create_task(auto_delete(context.bot, status, delay=10))

        tg_file = await file.get_file()
        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)
        local_path = f"{uuid.uuid4().hex}_{original_name}"
        await tg_file.download_to_drive(local_path)

        if not os.path.exists(local_path):
            await message.reply_text("❌ Download failed or file missing.")
            return

        caption = new_name
        thumb = None
        thumb_path = None
        user_id = update.effective_user.id

        if is_video_file(original_name) and file.thumb:
            tg_thumb = await file.thumb.get_file()
            thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
            await tg_thumb.download_to_drive(thumb_path)
            thumb = open(thumb_path, "rb")
        elif user_id in user_thumbnail and os.path.exists(user_thumbnail[user_id]):
            thumb_path = user_thumbnail[user_id]
            thumb = open(thumb_path, "rb")

        if is_pdf_file(original_name):
            images = convert_from_path(local_path, first_page=1, last_page=1)
            if images:
                preview_path = f"preview_{uuid.uuid4().hex}.jpg"
                images[0].save(preview_path, 'JPEG')
                msg = await context.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=InputFile(preview_path),
                    caption="📄 PDF Preview (First Page)"
                )
                asyncio.create_task(auto_delete(context.bot, msg, delay=15))
                os.remove(preview_path)

        with open(local_path, "rb") as f:
            if is_video_file(original_name):
                await context.bot.send_video(
                    chat_id=message.chat.id,
                    video=f,
                    caption=caption,
                    thumb=thumb if thumb else None
                )
            else:
                await context.bot.send_document(
                    chat_id=message.chat.id,
                    document=f,
                    filename=new_name,
                    caption=caption,
                    thumb=thumb if thumb else None
                )

        done = await message.reply_text(f"✅ Renamed to: {new_name}")
        asyncio.create_task(auto_delete(context.bot, done, delay=10))

        os.remove(local_path)
        if thumb and not thumb.closed and thumb_path and "thumb_" in thumb_path:
            thumb.close()
            os.remove(thumb_path)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != admin_id:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    if not context.args:
        await update.message.reply_text("❗ Usage: /broadcast Your message here")
        return
    text = " ".join(context.args)
    async for dialog in context.bot.get_dialogs():
        try:
            await context.bot.send_message(chat_id=dialog.chat.id, text=f"📢 Broadcast:\n{text}")
        except:
            continue
    await update.message.reply_text("✅ Broadcast sent.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()

    TOKEN = os.environ.get("BOT_TOKEN", "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(CommandHandler("getthumb", get_thumbnail))
    app.add_handler(CommandHandler("delthumb", delete_thumbnail))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, set_thumbnail))

    print("🚀 Bot is running...")
    app.run_polling()
