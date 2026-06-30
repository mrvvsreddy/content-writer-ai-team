"""
app.services.summarizer — Generates AI summaries via OpenRouter.
"""
import time
from pathlib import Path
from openai import OpenAI
from app.core.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

# Initialize the OpenAI client for OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# Model from environment config
TARGET_MODEL = OPENROUTER_MODEL

def generate_summary(text, title):
    """
    Generate a concise summary of the given article text using OpenRouter.
    Returns a tuple: (formatted_summary_string, total_tokens_used).
    """
    if not text or len(text) < 100:
        return "Not enough text to summarize.", 0

    # Read the system prompt skill
    skill_path = Path(__file__).parent.parent / "agent" / "skills" / "post_writer.md"
    try:
        system_prompt = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"    [Summarizer] Failed to read skill file: {e}")
        system_prompt = "You are an expert tech journalist and AI assistant."

    prompt = f"Title: {title}\n\nArticle Text:\n{text}"

    try:
        if not OPENROUTER_API_KEY:
            return "No OpenRouter API key provided.", 0

        # Try up to 3 times with a 2s gap
        for attempt in range(1, 4):
            print(f"    [Summarizer] Attempt {attempt} using model: {TARGET_MODEL}")
            try:
                response = client.chat.completions.create(
                    model=TARGET_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=250,
                    temperature=0.5,
                )
                content = response.choices[0].message.content
                tokens_used = response.usage.total_tokens if response.usage else 0
                if content:
                    return content.strip(), tokens_used
            except Exception as model_err:
                print(f"    [Summarizer] Model {TARGET_MODEL} failed: {model_err}")
                if attempt < 3:
                    print("    [Summarizer] Waiting 2 seconds before retrying...")
                    time.sleep(2)
                continue # Try the next attempt
        
        # If we exhausted all attempts
        return "Summary generation failed.", 0
    except Exception as e:
        print(f"    [Summarizer] Fatal error: {e}")
        return "Summary generation failed.", 0
