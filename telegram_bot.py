import os, json, asyncio
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)

BOT_TOKEN = "7657397566:AAFKTEJnkSljny1wzRFF3NJHEtV3fKbTpDA"
DATA_FILE = "channels.json"
POST_DATA = {}
app = Flask(__name__)

# -- Data utils --
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

# -- Conversation states --
SELECT_CHANNEL, ENTER_CONTENT, ENTER_BUTTONS = range(3)

# -- Commands --

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ctx.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "👋 Welcome to Controller Bot!\n\n"
            "Use the buttons below to manage channels and posts."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
            [InlineKeyboardButton("📝 Create Post", callback_data="create_post")],
            [InlineKeyboardButton("📢 My Channels", callback_data="my_channels")],
            [InlineKeyboardButton("❌ Close", callback_data="close")]
        ])
    )

async def help_command(update: Update, ctx):
    await update.message.reply_text(
        "ℹ️ *Help Menu*\n\n"
        "/start – Open control menu\n"
        "/help – Show this help\n\n"
        "*Create Post Workflow:*\n"
        "1. Add channel\n"
        "2. Tap Create Post\n"
        "3. Choose channel\n"
        "4. Send text or media\n"
        "5. Send buttons:\n"
        "`Button 1 - https://link1.com`\n"
        "`Button 2 - https://link2.com`\n"
        "`⬇️ Download - https://download.com`\n"
        "(First 2 = top row, others = below)\n"
        "6. Preview and confirm send",
        parse_mode="Markdown"
    )

# -- Button callback handling --

async def callback_handler(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    user = str(q.from_user.id)
    data = load_data()

    if q.data == "add_channel":
        ctx.user_data["await_channel"] = True
        msg = await q.edit_message_text("Send channel username (e.g. @yourchannel):")
        ctx.user_data["prompt_msg"] = msg

    elif q.data == "my_channels":
        chs = data.get(user, [])
        msg = "\n".join(chs) if chs else "🚫 No channels."
        msg_obj = await q.edit_message_text(f"📢 Your Channels:\n{msg}")
        ctx.user_data["prompt_msg"] = msg_obj

    elif q.data == "create_post":
        chs = data.get(user, [])
        if not chs:
            msg_obj = await q.edit_message_text("❗ Add a channel first!")
            ctx.user_data["prompt_msg"] = msg_obj
            return
        keyboards = [[InlineKeyboardButton(ch, callback_data=f"select_{ch}")] for ch in chs]
        msg_obj = await q.edit_message_text(
            "Select a channel to post to:",
            reply_markup=InlineKeyboardMarkup(keyboards)
        )
        ctx.user_data["prompt_msg"] = msg_obj

    elif q.data.startswith("select_"):
        ch = q.data.split("_",1)[1]
        ctx.user_data["channel"] = ch
        msg_obj = await q.edit_message_text(f"Posting to **{ch}**. Now send content (text/media):", parse_mode="Markdown")
        ctx.user_data["prompt_msg"] = msg_obj
        return ENTER_CONTENT

    elif q.data == "close":
        await q.message.delete()

    elif q.data == "confirm":
        u = user
        post = POST_DATA.get(u)
        if not post:
            await q.edit_message_text("🚫 No post data.")
            return ConversationHandler.END
        try:
            await ctx.bot.send_message(
                chat_id=post["channel"],
                text=post["text"],
                reply_markup=post["buttons"],
                parse_mode="HTML"
            ) if not post["media"] else await ctx.bot.send_photo(
                chat_id=post["channel"],
                photo=post["media"],
                caption=post["text"],
                reply_markup=post["buttons"],
                parse_mode="HTML"
            )
            await q.edit_message_text("✅ Posted successfully!")
        except Exception as e:
            await q.edit_message_text(f"❌ Failed:\n{e}")
        POST_DATA.pop(u, None)
        return ConversationHandler.END

# -- Message handlers --

async def handle_text(update: Update, ctx):
    msg_id = ctx.user_data.pop("prompt_msg", None)
    if msg_id:
        await msg_id.delete()
    user = str(update.message.from_user.id)
    data = load_data()

    if ctx.user_data.get("await_channel"):
        ch = update.message.text.strip()
        if not ch.startswith("@"):
            return await update.message.reply_text("❌ Must start with @")
        data.setdefault(user, [])
        if ch not in data[user]:
            data[user].append(ch)
            save_data(data)
            await update.message.reply_text(f"✅ Added {ch}")
        else:
            await update.message.reply_text("⚠️ Already added.")
        ctx.user_data.pop("await_channel", None)
        return

async def handle_content(update: Update, ctx):
    user = str(update.message.from_user.id)
    ch = ctx.user_data.get("channel")
    if not ch:
        return ConversationHandler.END
    text = update.message.text or update.message.caption or ""
    media = None
    if update.message.photo:
        media = update.message.photo[-1].file_id
    elif update.message.document:
        media = update.message.document.file_id
    POST_DATA[user] = {"channel": ch, "text": text, "media": media}
    prompt = await update.message.reply_text(
        "Send buttons:\n`Btn1 - URL1`\n`Btn2 - URL2`\n`⬇️ Download - URL…`",
        parse_mode="Markdown"
    )
    ctx.user_data["btn_prompt"] = prompt
    return ENTER_BUTTONS

async def handle_buttons(update: Update, ctx):
    pm = ctx.user_data.pop("btn_prompt", None)
    if pm:
        await pm.delete()
    user = str(update.message.from_user.id)
    lines = update.message.text.splitlines()
    rows, current = [], []
    for line in lines:
        if "-" not in line: continue
        t, u = line.split("-",1)
        current.append(InlineKeyboardButton(t.strip(), url=u.strip()))
        if len(current)==2:
            rows.append(current); current=[]
    if current: rows.append(current)
    POST_DATA[user]["buttons"] = InlineKeyboardMarkup(rows)
    post = POST_DATA[user]
    if post["media"]:
        preview = await update.message.reply_photo(post["media"], caption=post["text"], reply_markup=post["buttons"])
    else:
        preview = await update.message.reply_text(post["text"], reply_markup=post["buttons"])
    await preview.reply_text("✅ Preview above. Tap Confirm:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm")]
    ]))
    return ConversationHandler.END

# -- Flask root --
@app.route("/")
def root(): return "Bot running."

# -- Main run --
if __name__ == "__main__":
    import threading
    app_bot = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_handler, pattern="^select_")],
        states={
            ENTER_CONTENT: [MessageHandler(filters.ALL & filters.ChatType.PRIVATE, handle_content)],
            ENTER_BUTTONS: [MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_buttons)]
        },
        fallbacks=[]
    )

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))
    app_bot.add_handler(conv)

    threading.Thread(target=app.run, kwargs={"host":"0.0.0.0","port":int(os.getenv("PORT",5000))}).start()
    app_bot.run_polling()
