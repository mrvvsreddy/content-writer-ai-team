"""
app.services.telegram — Handles sending messages to the admin Telegram chat.
"""
import requests
from app.core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_CHAT_ID

def send_telegram_message(title: str, summary: str, article_url: str, image_url: str = None, target: str = "channel") -> bool:
    """
    Sends the generated summary to the configured Telegram chat/channel.
    Returns True if successful, False otherwise.
    """
    chat_id = TELEGRAM_CHANNEL_ID if target == "channel" else TELEGRAM_CHAT_ID

    if not TELEGRAM_BOT_TOKEN or not chat_id:
        print(f"    ⚠️ [Telegram] Credentials missing for {target}; skipping message.")
        return False
    message_text = summary

    try:
        # If there's an image, we try to send a photo message
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": chat_id,
                "photo": image_url,
                "caption": message_text
            }
            # The caption limit is 1024 chars. If our text is longer, we fallback to just text.
            if len(message_text) > 1000:
                return _send_text_only(message_text)

            res = requests.post(url, json=payload, timeout=10)
            
            # If sending photo fails (e.g. invalid image URL), fallback to text
            if not res.ok:
                print(f"    ⚠️ [Telegram] Failed to send photo to {target} (HTTP {res.status_code}), falling back to text.")
                return _send_text_only(message_text, chat_id)
            
            return True

        else:
            return _send_text_only(message_text, chat_id)

    except Exception as e:
        print(f"    ❌ [Telegram] Send error: {e}")
        return False

def _send_text_only(text: str, chat_id: str) -> bool:
    """Helper to send a text-only message to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False
    }
    res = requests.post(url, json=payload, timeout=10)
    if not res.ok:
        print(f"    ❌ [Telegram] Failed to send text (HTTP {res.status_code}): {res.text}")
        return False
    return True
