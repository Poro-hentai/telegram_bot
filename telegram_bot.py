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
user_thumbnail = {}
admin_id = 5759232282  # Your Telegram ID
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
        "📁 Just send any video, document, or PDF file, and I will rename it using your custom pattern.\n\n"
        "⚙️ *Available Commands:*\n"
        "`/setpattern` - Set rename pattern using `{original}`, `{number}`\n"
        "`/reset` - Reset rename counter to 0\n"
        "`/setthumb` - Set a custom thumbnail for your files\n"
        "`/getthumb` - View your current thumbnail\n"
        "`/delthumb` - Delete saved thumbnail\n"
        "`/broadcast` - [Admin Only] Send message to all users\n\n"
        "🚀 *Supported Formats:* .mp4, .mkv, .mov, .pdf, images, documents",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pattern
    if context.args:
        pattern = " ".join(context.args)
        await update.message.reply_text(f"✅ Pattern set to:\n`{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❗ Usage: /setpattern NewName - {number} - {original}")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔁 Counter reset to 0.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    file = update.message.photo[-1] if update.message.photo else update.message.document
    if file and (not update.message.document or update.message.document.mime_type.startswith("image/")):
        thumb_path = f"thumb_{uuid.uuid4().hex}.jpg"
        tg_file = await file.get_file()
        await tg_file.download_to_drive(thumb_path)
        user_thumbnail[user_id] = thumb_path
        await update.message.reply_text("✅ Thumbnail set.")
    else:
        await update.message.reply_text("❗ Please send a valid image (JPG/PNG).")

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
        await update.message.reply_text("❗ No thumbnail found.")

def is_video_file(name): return name.lower().endswith((".mp4", ".mkv", ".mov"))
def is_pdf_file(name): return name.lower().endswith(".pdf")

async def auto_delete(bot, message, delay=10):
    await asyncio.sleep(delay)
    try: await message.delete()
    except: pass

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        file = message.document or message.video
        if not file: return

        status = await message.reply_text("📥 Downloading...")
        asyncio.create_task(auto_delete(context.bot, status))

        original_name = file.file_name or "file"
        new_name = generate_filename(original_name)
        local_path = f"{uuid.uuid4().hex}_{original_name}"

        tg_file = await file.get_file()
        await tg_file.download_to_drive(local_path)

        caption = new_name
        thumb = None
        user_id = update.effective_user.id

        # Set thumbnail if exists
        if is_video_file(original_name):
            if user_id in user_thumbnail and os.path.exists(user_thumbnail[user_id]):
                thumb = InputFile(user_thumbnail[user_id])

        # PDF preview
        if is_pdf_file(original_name):
            images = convert_from_path(local_path, first_page=1, last_page=1)
            if images:
                preview_path = f"preview_{uuid.uuid4().hex}.jpg"
                images[0].save(preview_path, "JPEG")
                msg = await context.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=InputFile(preview_path),
                    caption="📄 PDF Preview (Page 1)"
                )
                asyncio.create_task(auto_delete(context.bot, msg))
                os.remove(preview_path)

        with open(local_path, "rb") as f:
            if is_video_file(original_name):
                await context.bot.send_video(
                    chat_id=message.chat.id,
                    video=f,
                    caption=caption,
                    thumb=thumb
                )
            else:
                await context.bot.send_document(
                    chat_id=message.chat.id,
                    document=f,
                    caption=caption
                )

        done = await message.reply_text(f"✅ Renamed to: `{new_name}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete(context.bot, done))

        os.remove(local_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{str(e)}`", parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != admin_id:
        await update.message.reply_text("❌ You're not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return
    message = " ".join(context.args)
    count = 0

    try:
        updates = await context.bot.get_updates()
        user_ids = list({u.message.chat.id for u in updates if u.message})
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Broadcast:\n{message}")
                count += 1
            except:
                continue
        await update.message.reply_text(f"✅ Broadcast sent to {count} users.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

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
