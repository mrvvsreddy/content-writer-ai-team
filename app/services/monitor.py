"""
app.services.monitor — Proactive background monitor for the AI agent.

Periodically checks pipeline health and sends proactive alerts to the
admin via Telegram when issues are detected (high failure rates,
blocked feeds, stalled pipeline).
"""
import asyncio
from datetime import datetime, timezone

from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.db.supabase import get_status_counts, get_blocked_feeds


# ── Configuration ──────────────────────────────────────────────
MONITOR_INTERVAL_MINUTES = 30     # How often the monitor checks
FAILURE_THRESHOLD = 5             # Alert if FAILED count exceeds this


async def _send_alert(text: str):
    """Send a proactive alert message to the admin's Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Monitor] ⚠ Alert skipped (no Telegram config): {text[:80]}")
        return

    import httpx
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                print(f"[Monitor] ✅ Alert sent to Telegram.")
            else:
                print(f"[Monitor] ❌ Telegram API error: {resp.status_code}")
    except Exception as e:
        print(f"[Monitor] ❌ Failed to send alert: {e}")


async def _run_health_check():
    """
    Run a single health check cycle.
    Returns True if an alert was sent, False otherwise.
    """
    alerts = []

    # Check article status counts
    counts = await asyncio.to_thread(get_status_counts)
    failed = counts.get("FAILED", 0)
    pending = counts.get("PENDING", 0)

    if failed >= FAILURE_THRESHOLD:
        alerts.append(
            f"🚨 *High failure rate:* {failed} articles have FAILED.\n"
            f"   → Reply: _\"retry failed articles\"_ or _\"purge failed articles\"_"
        )

    # Check for blocked feeds
    blocked = await asyncio.to_thread(get_blocked_feeds)
    if blocked:
        feed_lines = "\n".join(f"  • `{f['feed_url']}`" for f in blocked)
        alerts.append(
            f"🚫 *{len(blocked)} feed(s) blocked:*\n{feed_lines}\n"
            f"   → Reply: _\"unblock feed <url>\"_"
        )

    if alerts:
        header = "🤖 *Proactive Pipeline Alert*\n\n"
        message = header + "\n\n".join(alerts)
        await _send_alert(message)
        return True

    return False


async def agent_monitor_worker():
    """
    Async loop that monitors pipeline health every MONITOR_INTERVAL_MINUTES.
    Sends proactive Telegram alerts when issues are detected.
    """
    delay_seconds = MONITOR_INTERVAL_MINUTES * 60
    print(
        f"[Monitor] 👁 Started — checking pipeline health every "
        f"{MONITOR_INTERVAL_MINUTES} minutes"
    )

    # Wait a bit on startup to let the pipeline settle
    await asyncio.sleep(60)

    while True:
        try:
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            alerted = await _run_health_check()
            if not alerted:
                print(f"[Monitor] [{now}] Pipeline healthy — no alerts.")
        except Exception as e:
            print(f"[Monitor] Unhandled error: {e}")

        await asyncio.sleep(delay_seconds)
