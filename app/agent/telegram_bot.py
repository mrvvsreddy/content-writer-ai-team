"""
app.agent.telegram_bot — Real-time Telegram bot listener for the AI agent.

This runs alongside the existing pipeline without touching it.
When the admin sends a message, it instantly triggers the LangGraph agent
and replies with the agent's response.
"""
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.agent.graph import run_agent


# ── Security: only respond to the admin ────────────────────────
def _is_admin(update: Update) -> bool:
    """Check if the message is from the configured admin chat."""
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


# ── Handlers ───────────────────────────────────────────────────
async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    if not _is_admin(update):
        return
    await update.message.reply_text(
        "🤖 AI News Agent is online!\n\n"
        "Ask me anything about the pipeline:\n"
        "• \"How many articles are pending?\"\n"
        "• \"Show me the pipeline status\"\n"
        "• \"How many articles were posted?\"\n"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message from the admin by passing it to the LangGraph agent."""
    if not _is_admin(update):
        return

    user_text = update.message.text
    if not user_text:
        return

    # Show "typing..." indicator while the agent processes
    await update.effective_chat.send_action("typing")

    try:
        # Run the LangGraph agent
        response = await run_agent(user_text)
        await update.message.reply_text(response)
    except Exception as e:
        print(f"[TelegramBot] Agent error: {e}")
        await update.message.reply_text(
            f"❌ Sorry, something went wrong:\n{str(e)[:200]}"
        )


# ── Bot lifecycle ──────────────────────────────────────────────
async def start_telegram_bot():
    """
    Start the Telegram bot using long-polling.
    This function is designed to be run as an asyncio task inside the
    FastAPI lifespan so it coexists with the existing workers.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("[TelegramBot] ⚠ No TELEGRAM_BOT_TOKEN set — bot disabled.")
        return

    print("[TelegramBot] 🤖 Starting AI agent bot...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Initialize the app
    await app.initialize()
    await app.start()

    print("[TelegramBot] ✅ Bot is listening for messages from admin.")

    # Keep the bot running until cancelled, gracefully restarting polling on conflicts
    try:
        while True:
            if not app.updater.running:
                try:
                    # Starting polling in background. This handles transient deploy conflicts
                    # by retrying until the old deploy's bot releases the hook/polling limit.
                    await app.updater.start_polling(drop_pending_updates=True)
                except Exception as e:
                    print(f"[TelegramBot] ⚠️ Failed to start polling (will retry): {e}")
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        print("[TelegramBot] 🛑 Shutting down bot...")
        if app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
