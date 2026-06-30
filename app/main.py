"""
app.main — FastAPI application entrypoint.

Starts the RSS and Scraper background workers inside the application lifespan.
Run with:  uv run uvicorn app.main:app --reload
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.services.workers import rss_worker, scraper_worker
from app.services.monitor import agent_monitor_worker
from app.agent.telegram_bot import start_telegram_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage background worker tasks that run for the lifetime of the application.
    """
    print("🚀 Starting background workers...")
    rss_task = asyncio.create_task(rss_worker())
    scraper_task = asyncio.create_task(scraper_worker())
    bot_task = asyncio.create_task(start_telegram_bot())
    monitor_task = asyncio.create_task(agent_monitor_worker())

    yield  # Application is running

    print("🛑 Shutting down background workers...")
    rss_task.cancel()
    scraper_task.cancel()
    bot_task.cancel()
    monitor_task.cancel()

    # Wait for clean cancellation
    for task in (rss_task, scraper_task, bot_task, monitor_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="AI News Scraper",
    description="RSS aggregation, scraping, and summarization pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
