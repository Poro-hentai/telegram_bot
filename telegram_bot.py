import os, uuid, logging, threading, asyncio
from flask import Flask
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO)

pattern = "{original}"
file_counter = 0
user_thumbnail = {}
admin_id = 5759232282
flask_app = Flask(__name__)

@flask_app.route('/')
def home(): return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def generate_filename(original):
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original)
    if not ext: ext = ".mp4"
    return pattern.replace("{number}", str(file_counter)).replace("{original}", base) + ext

def is_video(fn): return fn.lower().endswith((".mp4", ".mkv", ".mov"))
def is_pdf(fn): return fn.lower().endswith(".pdf")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to *File Renamer Bot*!\n\n"
        "📁 Send any file (video/document/PDF) and I'll rename it.\n\n"
        "🛠️ Commands:\n"
        "`/setpattern` – Set filename format `{original}` `{number}`\n"
        "`/reset` – Reset counter\n"
        "`/setthumb` – Upload an image as thumbnail\n"
        "`/getthumb` – View current thumbnail\n"
        "`/delthumb` – Delete your thumbnail\n"
        "`/broadcast` – Admin only",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global pattern
    if ctx.args:
        pattern = " ".join(ctx.args)
        await update.message.reply_text(f"✅ Pattern set:\n`{pattern}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❗ Use: /setpattern File - {number} - {original}")

async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔄 Counter reset to 0.")

async def setthumb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    file = update.message.photo[-1] if update.message.photo else update.message.document
    if file and (not update.message.document or update.message.document.mime_type.startswith("image/")):
        path = f"thumb_{uuid.uuid4().hex}.jpg"
        tg = await file.get_file()
        await tg.download_to_drive(path)
        user_thumbnail[uid] = path
        await update.message.reply_text("✅ Thumbnail saved.")
    else:
        await update.message.reply_text("❗ Send a JPG/PNG image only.")

async def getthumb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_thumbnail and os.path.exists(user_thumbnail[uid]):
        await update.message.reply_photo(photo=InputFile(user_thumbnail[uid]), caption="🖼️ Your thumbnail")
    else:
        await update.message.reply_text("❗ No thumbnail set.")

async def delthumb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in user_thumbnail:
        try: os.remove(user_thumbnail[uid])
        except: pass
        del user_thumbnail[uid]
        await update.message.reply_text("🗑️ Thumbnail deleted.")
    else:
        await update.message.reply_text("❗ No thumbnail to delete.")

async def auto_delete(bot, msg, delay=10):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        msg = update.message
        file = msg.document or msg.video
        if not file: return

        notify = await msg.reply_text("📥 Downloading...")
        asyncio.create_task(auto_delete(ctx.bot, notify))

        orig = file.file_name or "file"
        new_name = generate_filename(orig)
        local = f"{uuid.uuid4().hex}_{orig}"
        tg = await file.get_file()
        await tg.download_to_drive(local)

        thumb = None
        uid = update.effective_user.id
        if uid in user_thumbnail and os.path.exists(user_thumbnail[uid]):
            thumb = InputFile(user_thumbnail[uid])

        # Show PDF preview
        if is_pdf(orig):
            images = convert_from_path(local, first_page=1, last_page=1)
            if images:
                preview = f"prev_{uuid.uuid4().hex}.jpg"
                images[0].save(preview, "JPEG")
                preview_msg = await ctx.bot.send_photo(chat_id=msg.chat.id, photo=InputFile(preview), caption="📄 PDF Preview")
                asyncio.create_task(auto_delete(ctx.bot, preview_msg))
                os.remove(preview)

        # Send file
        with open(local, "rb") as f:
            if is_video(orig):
                await ctx.bot.send_document(
                    chat_id=msg.chat.id,
                    document=f,
                    caption=new_name,
                    filename=new_name,
                    thumb=thumb
                )
            else:
                await ctx.bot.send_document(
                    chat_id=msg.chat.id,
                    document=f,
                    filename=new_name,
                    caption=new_name,
                    thumb=thumb if thumb else None
                )

        confirm = await msg.reply_text(f"✅ Renamed to:\n`{new_name}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete(ctx.bot, confirm))
        os.remove(local)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: `{e}`", parse_mode="Markdown")

async def broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != admin_id:
        return await update.message.reply_text("❌ You're not authorized.")
    if not ctx.args:
        return await update.message.reply_text("Usage: /broadcast Message")
    msg = " ".join(ctx.args)
    count = 0
    updates = await ctx.bot.get_updates()
    uids = {u.message.chat.id for u in updates if u.message}
    for uid in uids:
        try:
            await ctx.bot.send_message(uid, f"📢 Broadcast:\n{msg}")
            count += 1
        except: pass
    await update.message.reply_text(f"✅ Sent to {count} users.")

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    TOKEN = os.environ.get("BOT_TOKEN", "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("setthumb", setthumb))
    app.add_handler(CommandHandler("getthumb", getthumb))
    app.add_handler(CommandHandler("delthumb", delthumb))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, setthumb))

    print("🚀 Bot is live...")
    app.run_polling()
