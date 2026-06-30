"""
app.agent.telegram_bot — Real-time Telegram bot listener for the AI agent.

This runs alongside the existing pipeline without touching it.
When the admin sends a message, it instantly triggers the LangGraph agent
and replies with the agent's response.
"""
import asyncio
from telegram import Update
from telegram.error import Conflict, TimedOut, NetworkError
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)
import logging

# ── Suppress Conflict tracebacks from python-telegram-bot ──
class _SuppressConflictFilter(logging.Filter):
    def filter(self, record):
        if record.exc_info:
            _, exc_value, _ = record.exc_info
            if isinstance(exc_value, Conflict):
                return False
        return True

for logger_name in ["telegram.ext.Updater", "telegram.ext._updater", "telegram.ext._utils.networkloop"]:
    logging.getLogger(logger_name).addFilter(_SuppressConflictFilter())

from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.agent.graph import run_agent


# ── Security: only respond to the admin ────────────────────────
def _is_admin(update: Update) -> bool:
    """Check if the message is from the configured admin chat."""
    if not update.effective_chat:
        return False
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
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass  # Non-critical — don't fail the message handler

    try:
        # Run the LangGraph agent
        response = await run_agent(user_text)
        await update.message.reply_text(response)
    except Exception as e:
        print(f"[TelegramBot] Agent error: {e}")
        try:
            await update.message.reply_text(
                f"❌ Sorry, something went wrong:\n{str(e)[:200]}"
            )
        except Exception as send_err:
            print(f"[TelegramBot] Failed to send error reply: {send_err}")


# ── Global error handler ──────────────────────────────────────
async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Global error handler registered on the Application.
    Catches polling-level errors (Conflict, NetworkError, TimedOut)
    without crashing or spamming the terminal.
    """
    error = context.error

    if isinstance(error, Conflict):
        # This happens during Uvicorn reloads when two instances
        # momentarily compete for getUpdates. It resolves itself.
        print("[TelegramBot] ⚠ Polling conflict (deploy overlap) — will auto-resolve.")
        return

    if isinstance(error, TimedOut):
        print("[TelegramBot] ⚠ Network timeout — retrying automatically.")
        return

    if isinstance(error, NetworkError):
        print(f"[TelegramBot] ⚠ Network error: {error} — retrying automatically.")
        return

    # For any other unexpected error, log it fully
    print(f"[TelegramBot] ❌ Unhandled error: {error}")


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

    try:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    except Exception as e:
        print(f"[TelegramBot] ❌ Failed to build bot application: {e}")
        return

    # Register handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Register the global error handler to suppress Conflict spam
    app.add_error_handler(_error_handler)

    # Initialize the app
    try:
        await app.initialize()
        await app.start()
    except Exception as e:
        print(f"[TelegramBot] ❌ Failed to initialize bot: {e}")
        return

    print("[TelegramBot] ✅ Bot is listening for messages from admin.")

    # Keep the bot running until cancelled, gracefully restarting polling on conflicts
    try:
        while True:
            if not app.updater.running:
                try:
                    # Starting polling in background. This handles transient deploy conflicts
                    # by retrying until the old deploy's bot releases the hook/polling limit.
                    await app.updater.start_polling(drop_pending_updates=True)
                except Conflict:
                    print("[TelegramBot] ⚠ Polling conflict on startup — retrying in 5s...")
                except Exception as e:
                    print(f"[TelegramBot] ⚠️ Failed to start polling (will retry): {e}")
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        print("[TelegramBot] 🛑 Shutting down bot...")
        try:
            if app.updater.running:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception as e:
            print(f"[TelegramBot] ⚠ Error during shutdown (ignored): {e}")
