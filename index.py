import os
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from supabase import create_client, Client

# --- CONFIG ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_IDS = [6454727490]  # Your ID

# Initialize Flask & Supabase
app = Flask(__name__)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Bot Application (Global)
bot_app = Application.builder().token(TOKEN).build()

# --- LOGIC HANDLERS (Simplified for Vercel) ---

async def start(update: Update, context):
    user = update.effective_user
    args = context.args
    
    # Check for referral in args (e.g., ?start=ref_123)
    if args and args[0].startswith("ref_"):
        referrer_id = args[0].replace("ref_", "")
        # Save to Supabase
        try:
            data = {"user_id": user.id, "referrer_id": referrer_id, "username": user.username, "period": "2026-M01"}
            supabase.table("referrals").upsert(data).execute()
        except Exception as e:
            logging.error(f"DB Error: {e}")

    keyboard = [
        [InlineKeyboardButton("👑 Ambassador Program", callback_data="become_amb")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")]
    ]
    await update.message.reply_text(
        "🌟 **Welcome to Cerulean Labs!**\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def become_ambassador(update: Update, context):
    user = update.effective_user
    # DB: Add to ambassadors table
    supabase.table("ambassadors").upsert({"user_id": user.id, "username": user.username}).execute()
    
    link = f"https://t.me/ceruleanlabsbot?start=amb_{user.id}"
    await update.message.reply_text(f"👑 You are now an Ambassador!\nLink: `{link}`", parse_mode="Markdown")

# --- THE WEBHOOK ROUTE (The Heart of Vercel) ---
@app.route("/", methods=["POST"])
def webhook():
    if request.method == "POST":
        # Process the update from Telegram
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        
        # Add Handlers dynamically (stateless)
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CommandHandler("become_ambassador", become_ambassador))
        # Add more handlers here from your original bot.py...
        
        # Run the update
        asyncio.run(bot_app.process_update(update))
        return "ok"
    return "env running"

import asyncio