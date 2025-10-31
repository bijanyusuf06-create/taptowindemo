import os
import asyncio
import time
import random
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ---- KEEP SERVER AWAKE ----
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ---- CONFIG ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

app = ApplicationBuilder().token(BOT_TOKEN).build()

# ---- GLOBALS ----
players = {}  # username -> {chat_id, taps, first5}
manual_player_names = []  # fake 9 players
active_codes = []
current_round_players = []
round_active = False
start_time = None

# ---- COMMANDS ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to TapToWin Demo Recording Bot!\n\n"
        "Commands:\n"
        "/enterplayers - enter 9 fake players\n"
        "/entergame - join as 10th player (you)\n"
        "/generatecode - create one-time game code"
    )

async def enterplayers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global manual_player_names
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this command.")
        return

    manual_player_names.clear()
    await update.message.reply_text(
        "Please enter 9 player names separated by commas.\nExample:\nJohn, Sarah, Mike, Alice, Tom, Zara, Ben, Leo, Anna"
    )
    context.user_data["awaiting_players"] = True

async def handle_manual_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global manual_player_names
    if not context.user_data.get("awaiting_players"):
        return

    names = [n.strip() for n in update.message.text.split(",") if n.strip()]
    if len(names) != 9:
        await update.message.reply_text("❌ You must enter exactly 9 names.")
        return

    manual_player_names = names
    context.user_data["awaiting_players"] = False
    await update.message.reply_text(
        f"✅ Players entered:\n{', '.join(manual_player_names)}\n\nNow use /generatecode and /entergame to join as 10th player."
    )

async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this command.")
        return
    num = random.randint(100, 999)
    code = f"TTW{num}"
    active_codes.append(code)
    await update.message.reply_text(f"✅ Code generated: {code}")

async def entergame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or "you"
    players[username] = {"chat_id": update.effective_chat.id, "taps": 0, "first5": 0}
    await update.message.reply_text("Enter your one-time game code:")
    context.user_data["awaiting_code"] = True

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_round_players
    username = update.effective_user.username or "you"
    if not context.user_data.get("awaiting_code"):
        return

    code = update.message.text.strip()
    if code not in active_codes:
        await update.message.reply_text("❌ Invalid code.")
        return

    # Valid code
    active_codes.remove(code)
    context.user_data["awaiting_code"] = False
    current_round_players = [username] + manual_player_names  # include you + 9 fake

    await update.message.reply_text("✅ You are in! Game will start soon.")
    await start_countdown_for_round(context, username)

async def start_countdown_for_round(context, username):
    global round_active, start_time
    round_active = True
    start_time = None

    # 5-second countdown
    for i in range(5, 0, -1):
        await context.bot.send_message(players[username]["chat_id"], f"Game starting in {i}...")
        await asyncio.sleep(1)

    # start round
    start_time = time.time()
    button = InlineKeyboardButton("👆 TAP", callback_data="tap")
    markup = InlineKeyboardMarkup([[button]])
    await context.bot.send_message(players[username]["chat_id"], "🚀 Start tapping! 10 seconds go!", reply_markup=markup)
    await asyncio.sleep(10)

    round_active = False
    await context.bot.send_message(players[username]["chat_id"], "⏱ Time’s up!")

    # random leaderboard
    results = {}
    for name in current_round_players:
        if name == username:
            results[name] = players[username]["taps"]
        else:
            results[name] = random.randint(100, 250)

    sorted_players = sorted(results.items(), key=lambda x: x[1], reverse=True)
    leaderboard = "\n".join([f"{i+1}. @{n}: {t} taps" for i, (n, t) in enumerate(sorted_players)])
    winner = sorted_players[0][0]

    await context.bot.send_message(players[username]["chat_id"], f"🏆 Winner: @{winner}\n\n📊 Results:\n{leaderboard}")

    # reset
    players[username]["taps"] = 0
    current_round_players.clear()

async def tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global start_time
    if not round_active or start_time is None:
        await update.callback_query.answer("Round not active!", show_alert=True)
        return

    username = update.effective_user.username or "you"
    if username not in players:
        await update.callback_query.answer("Register first!", show_alert=True)
        return

    players[username]["taps"] += 1
    await update.callback_query.answer(f"Taps: {players[username]['taps']}")

# ---- HANDLERS ----
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("enterplayers", enterplayers))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_players))
app.add_handler(CommandHandler("generatecode", generate_code))
app.add_handler(CommandHandler("entergame", entergame))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
app.add_handler(CallbackQueryHandler(tap, pattern="^tap$"))

if __name__ == "__main__":
    print("Bot running...")
    app.run_polling()
