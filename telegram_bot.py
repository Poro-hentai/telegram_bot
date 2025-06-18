import os
import re
import uuid
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Configure logging for better insights into bot's operations
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Global Variables ---
# Default pattern for renaming files. {original} is replaced by the original filename (without extension),
# and {number} is replaced by an incrementing counter.
# Note: The initial pattern in the provided code was only "{original}".
# I'm updating it to include {number} for better functionality as suggested in the /setpattern command.
pattern = "{original}_{number}"
file_counter = 0  # Counter for renaming files
user_thumbnail = None  # Stores the path to a user-defined thumbnail for videos

# --- Flask App for Hosting (Keep-Alive) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    """Simple Flask route to indicate the bot is running."""
    return "Bot is running!"

def run_flask():
    """Runs the Flask application in a separate thread to keep the bot alive on some hosting platforms."""
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Flask app running on port {port}")
    flask_app.run(host="0.0.0.0", port=port)

# --- Filename Generation Logic ---
def generate_filename(original_name: str) -> str:
    """
    Generates a new filename based on the global pattern and increments the file counter.

    Args:
        original_name (str): The original name of the file.

    Returns:
        str: The newly generated filename.
    """
    global file_counter, pattern
    file_counter += 1
    base, ext = os.path.splitext(original_name)

    # Ensure extension starts with a dot if it exists, otherwise default to .mp4 for consistency
    if not ext:
        ext = ".mp4"
    elif not ext.startswith('.'):
        ext = '.' + ext

    # Sanitize base name for common file system issues and replace placeholders
    cleaned_base = re.sub(r'[<>:"/\\|?*]', '', base) # Remove invalid characters
    new_name = pattern.replace("{number}", str(file_counter)).replace("{original}", cleaned_base) + ext
    logger.info(f"Generated filename: {new_name} from original: {original_name}")
    return new_name

# --- Telegram Bot Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command. Greets the user and explains bot usage.
    """
    logger.info(f"User {update.effective_user.id} started the bot.")
    await update.message.reply_text(
        "👋 *Welcome to File Renamer Bot!* 🤖\n\n"
        "Send me any file, and I'll rename it using your custom pattern.\n\n"
        "Here are the available commands:\n"
        "✨ `/setpattern <your_pattern>` - Set your custom rename pattern. "
        "Use `{original}` for the original filename (without extension) and `{number}` for an incrementing counter. "
        "Example: `/setpattern MyShow S01E{number} - {original}`\n"
        "🔄 `/reset` - Reset the file counter to 0.\n"
        "🖼️ `/setthumb` - Reply to a photo with this command to set it as the default thumbnail for videos.\n"
        "💡 `/help` - Show this welcome message again.",
        parse_mode="Markdown"
    )

async def setpattern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /setpattern command. Allows users to define their renaming pattern.
    """
    global pattern
    if context.args:
        new_pattern = " ".join(context.args)
        # Basic validation: ensure at least one placeholder is present to make sense
        if "{original}" not in new_pattern and "{number}" not in new_pattern:
            await update.message.reply_text(
                "⚠️ Your pattern should ideally contain `{original}` or `{number}` to be useful. "
                "Do you want to set it anyway? If so, try again with placeholders."
            )
            logger.warning(f"User {update.effective_user.id} tried to set a pattern without placeholders: {new_pattern}")
        else:
            pattern = new_pattern
            await update.message.reply_text(f"✅ Pattern successfully set to:\n`{pattern}`", parse_mode="Markdown")
            logger.info(f"User {update.effective_user.id} set pattern to: {pattern}")
    else:
        await update.message.reply_text(
            "❗ Usage: `/setpattern YourSeries S01 - {number} - {original}`\n"
            "Use `{original}` for the original file name and `{number}` for a counter.",
            parse_mode="Markdown"
        )

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /reset command. Resets the file counter to 0.
    """
    global file_counter
    file_counter = 0
    await update.message.reply_text("🔄 File counter has been reset to 0.")
    logger.info(f"User {update.effective_user.id} reset the file counter.")

async def set_thumbnail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /setthumb command. Sets a user-provided photo as the default thumbnail for videos.
    """
    global user_thumbnail
    if update.message.photo:
        photo = update.message.photo[-1]  # Get the largest available photo
        # Generate a unique filename for the thumbnail
        thumb_path = f"thumbnails/thumb_{uuid.uuid4().hex}.jpg"
        
        # Ensure the thumbnails directory exists
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        file = await photo.get_file()
        await file.download_to_drive(thumb_path)
        
        # Clean up previous thumbnail if exists
        if user_thumbnail and os.path.exists(user_thumbnail):
            os.remove(user_thumbnail)
            logger.info(f"Removed old thumbnail: {user_thumbnail}")

        user_thumbnail = thumb_path
        await update.message.reply_text("✅ Default thumbnail set successfully! This will be used for videos.")
        logger.info(f"User {update.effective_user.id} set thumbnail: {user_thumbnail}")
    else:
        await update.message.reply_text("❗ Please *reply to a photo* with the `/setthumb` command to set it as a thumbnail.", parse_mode="Markdown")
        logger.warning(f"User {update.effective_user.id} tried to set thumbnail without replying to a photo.")

# --- File Handling Logic ---

def is_video_file(filename: str) -> bool:
    """
    Checks if a given filename corresponds to a common video file extension.

    Args:
        filename (str): The name of the file to check.

    Returns:
        bool: True if it's a video file, False otherwise.
    """
    return filename.lower().endswith(('.mp4', '.mkv', '.mov', '.avi', '.webm'))

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming documents and videos. Downloads, renames, and sends them back to the user.
    """
    message = update.message
    file = message.document or message.video
    
    if not file:
        await message.reply_text("Please send a document or a video to rename.")
        logger.warning(f"User {update.effective_user.id} sent an unsupported message type.")
        return

    # Indicate download start
    status_message = await message.reply_text("⬇️ Downloading your file...")
    logger.info(f"Starting download for file from user {update.effective_user.id}")

    try:
        tg_file = await file.get_file()
        original_name = file.file_name or "unknown_file"
        new_name = generate_filename(original_name)
        
        # Create a unique temporary path for the downloaded file
        temp_dir = "downloads"
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{original_name}")
        
        await tg_file.download_to_drive(local_path)
        logger.info(f"Downloaded file to {local_path}")
        
        await status_message.edit_text("⬆️ Uploading and renaming your file...")

        caption = f"`{new_name}`"
        thumb_file_object = None
        temp_thumb_path = None

        if is_video_file(original_name):
            # Prioritize Telegram's own thumbnail if available
            if file.thumbnail: # Corrected from file.thumb to file.thumbnail as per python-telegram-bot docs
                tg_thumb = await file.thumbnail.get_file()
                temp_thumb_path = f"thumbnails/temp_thumb_{uuid.uuid4().hex}.jpg"
                os.makedirs(os.path.dirname(temp_thumb_path), exist_ok=True)
                await tg_thumb.download_to_drive(temp_thumb_path)
                thumb_file_object = open(temp_thumb_path, "rb")
                logger.info(f"Using Telegram's provided thumbnail: {temp_thumb_path}")
            # Fallback to user-defined thumbnail
            elif user_thumbnail and os.path.exists(user_thumbnail):
                thumb_file_object = open(user_thumbnail, "rb")
                logger.info(f"Using user-defined thumbnail: {user_thumbnail}")
            
            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumbnail=thumb_file_object if thumb_file_object else None, # Corrected from thumb to thumbnail
                supports_streaming=True # Important for large video files
            )
            logger.info(f"Sent renamed video: {new_name}")
        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption
            )
            logger.info(f"Sent renamed document: {new_name}")

        await status_message.edit_text(f"🎉 Done! Your file has been renamed.")

    except Exception as e:
        logger.error(f"Error handling file for user {update.effective_user.id}: {e}", exc_info=True)
        await status_message.edit_text(f"❌ An error occurred while processing your file. Please try again later.\nError details: `{e}`", parse_mode="Markdown")
    finally:
        # Clean up downloaded files and opened thumbnail files
        if os.path.exists(local_path):
            os.remove(local_path)
            logger.info(f"Cleaned up local file: {local_path}")
        if thumb_file_object and not thumb_file_object.closed:
            thumb_file_object.close()
            logger.info("Closed thumbnail file object.")
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)
            logger.info(f"Cleaned up temporary thumbnail: {temp_thumb_path}")


# --- Main Bot Setup ---
if __name__ == "__main__":
    # Start the Flask app in a separate thread for continuous deployment (e.g., on Heroku)
    threading.Thread(target=run_flask, daemon=True).start()

    # Get the bot token from environment variables for security
    # It's highly recommended to use environment variables instead of hardcoding
    # TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    # if not TOKEN:
    #     logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
    #     exit(1)
    
    # For demonstration, keeping the provided hardcoded token.
    # In a production environment, always use environment variables.
    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"

    app = ApplicationBuilder().token(TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start)) # /help also shows start message
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    
    # Register message handlers
    # Handle both documents and videos for renaming
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    # Handle photos specifically for setting thumbnails when replied to /setthumb
    app.add_handler(MessageHandler(filters.PHOTO & filters.REPLY, set_thumbnail)) # Only process photos that are replies
    
    logger.info("🚀 Bot is running and polling for updates...")
    app.run_polling(drop_pending_updates=True) # drop_pending_updates can be useful to avoid processing old updates on restart
