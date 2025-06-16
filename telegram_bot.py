# --- PDF THUMBNAIL SUPPORT ---
        elif original_name.lower().endswith('.pdf'):
            thumb_path = generate_pdf_thumbnail(local_path)
            if thumb_path and os.path.exists(thumb_path):
                thumb = open(thumb_path, "rb")

        # --- Send Final File ---
        if is_video_file(original_name):
            await context.bot.send_video(
                chat_id=message.chat.id,
                video=open(local_path, "rb"),
                caption=caption,
                thumb=thumb if thumb else None
            )
        else:
            await context.bot.send_document(
                chat_id=message.chat.id,
                document=open(local_path, "rb"),
                filename=new_name,
                caption=caption,
                thumb=thumb if thumb else None  # PDF will work here
            )

        await message.reply_text(f"✅ Renamed to: {new_name}")

        # Clean-up
        os.remove(local_path)
        if thumb:
            thumb.close()
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# --- MAIN ---
if name == "main":
    threading.Thread(target=run_flask).start()

    TOKEN = "7363840731:AAE7TD7eLEs7GjbsguH70v5o2XhT89BePCM"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpattern", setpattern))
    app.add_handler(CommandHandler("reset", reset_counter))
    app.add_handler(CommandHandler("setthumb", set_thumbnail))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, handle_file))
    app.add_handler(MessageHandler(filters.PHOTO, set_thumbnail))

    print("🚀 Bot is running...")
    app.run_polling()