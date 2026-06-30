"""
app.core.config — Central configuration loaded from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter Config ──────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Supabase Config ───────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── Telegram Config ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", TELEGRAM_CHAT_ID)

# ── Keywords to filter ────────────────────────────────────────
AI_KEYWORDS = [
    " ai ", "artificial intelligence", "llm", "machine learning", "deep learning",
    "openai", "chatgpt", "anthropic", "claude", "gemini", "midjourney",
    "neural network", "generative ai", "agi", "sam altman", "nvidia",
]

# ── Polling intervals ────────────────────────────────────────
RSS_POLL_INTERVAL_MINUTES = 60       # 1 hour → 24 scans per day per feed
SCRAPER_POLL_INTERVAL_MINUTES = 5    # 5 min gap between each article scrape

# ── Blocking backoff ─────────────────────────────────────────
BLOCK_BACKOFF_HOURS = 1              # Hours to wait before retrying a blocked feed
