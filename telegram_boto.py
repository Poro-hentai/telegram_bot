import os, json, threading
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = "7657397566:AAFKTEJnkSljny1wzRFF3NJHEtV3fKbTpDA"
DATA_FILE = "channels.json"

app = Flask(__name__)
POST = {}  # holds temporary post data per user

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            return json.load(open(DATA_FILE))
        except:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- Commands ---

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to your personal ControllerBot copy!\nUse the buttons below to manage channels and posts.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
            [InlineKeyboardButton("📢 My Channels", callback_data="my_channels")],
            [InlineKeyboardButton("📝 Create Post", callback_data="create_post")],
            [InlineKeyboardButton("ℹ Help", callback_data="help")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *Help — How to use this bot*\n\n"
        "/start – Show control menu\n"
        "/help – Show this help\n\n"
        "*To post:* ➕ Add a channel → Create Post → choose channel → send text/media → send buttons (Text - URL) → Preview → Confirm",
        parse_mode="Markdown"
    )

# --- Callbacks ---

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = str(q.from_user.id)
    data = load_data()

    if q.data == "add_channel":
        ctx.user_data["await_channel"] = True
        await q.edit_message_text("Send your channel username (e.g., @channelusername):")

    elif q.data == "my_channels":
        channels = data.get(user, [])
        msg = "\n".join(channels) if channels else "🚫 No channels added."
        await q.edit_message_text(f"📢 Your Channels:\n{msg}",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]]))

    elif q.data == "create_post":
        chans = data.get(user, [])
        if not chans:
            await q.edit_message_text("⚠️ You need to add a channel first!")
            return
        btns = [[InlineKeyboardButton(c, callback_data=f"select|{c}")] for c in chans]
        btns.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        await q.edit_message_text("Select channel to post to:", reply_markup=InlineKeyboardMarkup(btns))

    elif q.data and q.data.startswith("select|"):
        ch = q.data.split("|",1)[1]
        ctx.user_data["target"] = ch
        await q.edit_message_text(f"✅ Selected {ch}. Now send your post (text/photo):")
        return

    elif q.data == "help":
        await q.edit_message_text("ℹ Opening help…")
        return await help_cmd(update, ctx)

    elif q.data == "close":
        await q.message.delete()

    elif q.data == "back":
        return await start_cmd(update, ctx)

    elif q.data == "confirm":
        u = str(q.from_user.id)
        post = POST.get(u)
        if not post:
            await q.edit_message_text("⚠️ No post available.")
            return
        try:
            if post.get("media"):
                await ctx.bot.send_photo(
                    chat_id=post["target"],
                    photo=post["media"],
                    caption=post["text"] or "",
                    reply_markup=post["buttons"]
                )
            else:
                await ctx.bot.send_message(
                    chat_id=post["target"],
                    text=post["text"],
                    reply_markup=post["buttons"]
                )
            await q.edit_message_text("✅ Posted successfully!")
        except Exception as e:
            await q.edit_message_text(f"❌ Failed to post: {e}")
        POST.pop(u, None)

    elif q.data == "cancel":
        POST.pop(str(q.from_user.id), None)
        await q.edit_message_text("❌ Post canceled.")

# --- Text & Media Handler ---

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = str(msg.from_user.id)
    data = load_data()

    # Add channel
    if ctx.user_data.pop("await_channel", False):
        ch = msg.text.strip()
        if not ch.startswith("@"):
            return await msg.reply_text("❌ Invalid format. Should start with @")
        data.setdefault(user, [])
        if ch not in data[user]:
            data[user].append(ch)
            save_data(data)
            await msg.reply_text(f"✅ Channel {ch} added.")
        else:
            await msg.reply_text("⚠️ Channel already exists.")
        return

    # During post creation
    if ctx.user_data.get("target") and not POST.get(user):
        # Capture message
        if msg.photo:
            media = msg.photo[-1].file_id
            text = msg.caption or ""
        else:
            media = None
            text = msg.text or ""
        POST[user] = {
            "target": ctx.user_data.get("target"),
            "media": media,
            "text": text
        }
        await msg.reply_text("📎 Got your content! Now send buttons (each 'Text - URL'):")

    elif POST.get(user) and "buttons" not in POST[user]:
        # Parse buttons
        lines = msg.text.strip().splitlines()
        btn_rows = []
        row = []
        for line in lines:
            if "-" not in line: continue
            t, u = line.split("-", 1)
            btn = InlineKeyboardButton(t.strip(), url=u.strip())
            row.append(btn)
            if len(row) == 2:
                btn_rows.append(row)
                row = []
        if row: btn_rows.append(row)
        POST[user]["buttons"] = InlineKeyboardMarkup(btn_rows)

        # Preview
        p = POST[user]
        if p["media"]:
            await msg.reply_photo(p["media"], caption=p["text"], reply_markup=p["buttons"])
        else:
            await msg.reply_text(p["text"], reply_markup=p["buttons"])

        await msg.reply_text("✅ Preview above. Tap to confirm:",
                             reply_markup=InlineKeyboardMarkup([
                                 [InlineKeyboardButton("✅ Confirm", callback_data="confirm")],
                                 [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                             ]))
    else:
        await msg.delete()

# --- Flask root & bot startup ---

@app.route("/")
def root(): return "✅ Bot is up!"

if __name__ == "__main__":
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, handle_message))

    threading.Thread(target=app.run, kwargs={"host":"0.0.0.0","port":int(os.getenv("PORT",5000))}).start()
    application.run_polling()
