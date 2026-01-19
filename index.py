import os
import logging
import csv
import io
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from supabase import create_client, Client

# --- CONFIGURATION ---
# Get these from Vercel Environment Variables
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Admin IDs (Add yours)
ADMIN_IDS = [6454727490]
GROUP_CHAT_ID = -1002664797681  # Optional: Add your group ID
X_LINK = "https://x.com/ceruleanlabs"
TELEGRAM_LINK = "https://t.me/ceruleanlabsgroupchat"

# Initialize Flask (The Server)
app = Flask(__name__)

# Initialize Supabase (The Database)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Bot (The Logic)
bot_app = Application.builder().token(TOKEN).build()
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---
def get_current_period():
    now = datetime.now()
    return f"{now.year}-W{now.isocalendar()[1]:02d}", f"{now.year}-M{now.month:02d}"

# --- HANDLERS ---

async def start(update: Update, context):
    user = update.effective_user
    args = context.args
    week, month = get_current_period()

    # 1. Handle Ambassador Referral (amb_123)
    if args and args[0].startswith("amb_"):
        referrer_id = args[0].replace("amb_", "")
        if str(referrer_id) == str(user.id):
            await update.message.reply_text("⚠️ You cannot refer yourself!")
            return

        # Check if already referred
        res = supabase.table("users").select("*").eq("user_id", user.id).execute()
        if res.data:
            await update.message.reply_text("✅ You are already registered!")
            return

        # Register the referral
        supabase.table("users").insert({
            "user_id": user.id,
            "referrer": referrer_id,
            "status": "pending"
        }).execute()
        
        # Show tasks
        await show_tasks(update, referrer_id, "ambassador")

    # 2. Handle Contest Referral (ref_123)
    elif args and args[0].startswith("ref_"):
        referrer_id = args[0].replace("ref_", "")
        if str(referrer_id) == str(user.id):
            await update.message.reply_text("⚠️ You cannot refer yourself!")
            return

        # Check existing referral for this month
        res = supabase.table("referrals").select("*").eq("user_id", user.id).eq("period", month).execute()
        if res.data:
            await update.message.reply_text("✅ You already joined this month's contest!")
            return

        # Register referral
        supabase.table("referrals").insert({
            "user_id": user.id,
            "referrer_id": referrer_id,
            "username": user.username,
            "status": "pending",
            "period": month
        }).execute()

        await show_tasks(update, referrer_id, "contest")

    # 3. Normal Start
    else:
        keyboard = [
            [InlineKeyboardButton("👑 Become Ambassador", callback_data="become_amb")],
            [InlineKeyboardButton("🔗 Get Referral Link", callback_data="get_ref")],
            [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
            [InlineKeyboardButton("🏆 Leaderboards", callback_data="leaderboards")]
        ]
        await update.message.reply_text(
            "🌟 **Welcome to Cerulean Labs!**\n\nChoose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def show_tasks(update, referrer_id, type_):
    keyboard = [
        [InlineKeyboardButton("📱 Join Telegram", url=TELEGRAM_LINK)],
        [InlineKeyboardButton("🐦 Follow on X", url=X_LINK)],
        [InlineKeyboardButton("✅ Verify Tasks", callback_data=f"verify_{type_}_{referrer_id}")]
    ]
    await update.message.reply_text(
        "🎯 **Complete these tasks to verify:**\n1️⃣ Join our Telegram\n2️⃣ Follow us on X",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def verify_task(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_") # verify, type, referrer_id
    user_id = query.from_user.id
    type_ = data[1]
    referrer_id = data[2]
    week, month = get_current_period()

    if type_ == "ambassador":
        # Update User Status
        supabase.table("users").update({"status": "completed"}).eq("user_id", user_id).execute()
        # Give Point to Ambassador
        # Note: Supabase doesn't have simple "increment", so we do a stored procedure or just read-write.
        # Simple read-write for now (fine for small scale):
        amb = supabase.table("ambassadors").select("points").eq("user_id", referrer_id).execute()
        if amb.data:
            new_points = amb.data[0]['points'] + 1
            supabase.table("ambassadors").update({"points": new_points}).eq("user_id", referrer_id).execute()
        
        await query.edit_message_text("✅ Verified! Welcome to the community.")

    elif type_ == "contest":
        supabase.table("referrals").update({
            "status": "completed", 
            "completed_at": "now()"
        }).eq("user_id", user_id).eq("period", month).execute()
        
        await query.edit_message_text("✅ Verified! Your referrer got a point.")

async def become_ambassador(update: Update, context):
    user = update.effective_user
    res = supabase.table("ambassadors").select("*").eq("user_id", user.id).execute()
    
    if res.data:
        await update.message.reply_text("👑 You are already an ambassador!")
        return

    supabase.table("ambassadors").insert({
        "user_id": user.id, 
        "username": user.username,
        "points": 0
    }).execute()
    
    bot_name = context.bot.username
    link = f"https://t.me/{bot_name}?start=amb_{user.id}"
    await update.message.reply_text(f"🎉 **Welcome Ambassador!**\n\nYour Link:\n`{link}`", parse_mode="Markdown")

async def get_ref_link(update: Update, context):
    user = update.effective_user
    bot_name = context.bot.username
    link = f"https://t.me/{bot_name}?start=ref_{user.id}"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(f"🎁 **Contest Link:**\n`{link}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"🎁 **Contest Link:**\n`{link}`", parse_mode="Markdown")

async def track_engagement(update: Update, context):
    # Only track in groups
    if update.message.chat.type not in ["group", "supergroup"]:
        return

    user = update.effective_user
    week, month = get_current_period()
    
    # Check if user exists for this week
    res = supabase.table("engagement").select("*").eq("user_id", user.id).eq("period", week).execute()
    
    if not res.data:
        supabase.table("engagement").insert({
            "user_id": user.id,
            "username": user.username,
            "message_count": 1,
            "period": week,
            "last_message_at": "now()"
        }).execute()
    else:
        new_count = res.data[0]['message_count'] + 1
        supabase.table("engagement").update({
            "message_count": new_count,
            "last_message_at": "now()"
        }).eq("id", res.data[0]['id']).execute()

async def export_data(update: Update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return

    await update.message.reply_text("📂 Generating export...")
    
    # Fetch Data
    res = supabase.table("ambassadors").select("*").execute()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "Username", "Points"])
    for row in res.data:
        writer.writerow([row['user_id'], row['username'], row['points']])
    
    # Convert to bytes for Telegram
    output.seek(0)
    bytes_io = io.BytesIO(output.getvalue().encode('utf-8'))
    bytes_io.name = "ambassadors.csv"
    
    await update.message.reply_document(document=bytes_io, caption="Ambassador Data")

async def my_stats(update: Update, context):
    user_id = update.effective_user.id
    week, month = get_current_period()
    
    text = "📊 **Your Stats**\n\n"
    
    # Amb Stats
    amb = supabase.table("ambassadors").select("*").eq("user_id", user_id).execute()
    if amb.data:
        text += f"👑 **Ambassador Points:** {amb.data[0]['points']}\n"
    
    # Engagement Stats
    eng = supabase.table("engagement").select("*").eq("user_id", user_id).eq("period", week).execute()
    if eng.data:
        text += f"💬 **Weekly Messages:** {eng.data[0]['message_count']}\n"
        
    await update.effective_message.reply_text(text, parse_mode="Markdown")

# --- WEBHOOK ROUTE ---
@app.route("/", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        if request.is_json:
            update = Update.de_json(request.get_json(force=True), bot_app.bot)
            
            # Add Handlers
            bot_app.add_handler(CommandHandler("start", start))
            bot_app.add_handler(CommandHandler("become_ambassador", become_ambassador))
            bot_app.add_handler(CommandHandler("get_referral_link", get_ref_link)) # Fixed command
            bot_app.add_handler(CommandHandler("export", export_data))
            bot_app.add_handler(CommandHandler("stats", my_stats))
            
            # Callbacks
            bot_app.add_handler(CallbackQueryHandler(become_ambassador, pattern="^become_amb$"))
            bot_app.add_handler(CallbackQueryHandler(get_ref_link, pattern="^get_ref$"))
            bot_app.add_handler(CallbackQueryHandler(my_stats, pattern="^my_stats$"))
            bot_app.add_handler(CallbackQueryHandler(verify_task, pattern="^verify_"))
            
            # Message Handler (Engagement)
            bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_engagement))
            
            # Run
            try:
                # We use await here inside the Flask async context if available, 
                # but standard Flask is sync. We use the asyncio loop:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(bot_app.process_update(update))
                loop.close()
            except Exception as e:
                logger.error(f"Error: {e}")
                
            return "ok"
        return "Not JSON", 400
    return "Bot is active and running!"
