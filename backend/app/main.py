"""FastAPI application entry point with APScheduler."""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import router
from app.services.report_generator import generate_all_reports
from app.services.postmortem import init_postmortem_table, evaluate_all_expired
from app.services.price_spike import start_monitor, stop_monitor

scheduler = AsyncIOScheduler()


def _setup_scheduler():
    """Schedule analysis jobs at 08:00, 12:00, 22:00 Beijing time (UTC+8)."""
    for hour in settings.SCHEDULE_HOURS:
        # Convert Beijing time to UTC: subtract 8 hours
        utc_hour = (hour - 8) % 24
        scheduler.add_job(
            generate_all_reports,
            CronTrigger(hour=utc_hour, minute=0, timezone="UTC"),
            id=f"analysis_{hour:02d}00",
            name=f"Analysis at {hour:02d}:00 Beijing Time",
            replace_existing=True,
        )
        print(f"  Scheduled: {hour:02d}:00 Beijing → {utc_hour:02d}:00 UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print(f"\n🚀 {settings.PROJECT_NAME} v{settings.VERSION} starting...")
    print(f"  Tracking: {', '.join(settings.SYMBOLS)}")

    # Initialize database
    init_db()
    init_postmortem_table()
    print("  ✓ Database initialized (reports + postmortems)")

    # Setup scheduler
    _setup_scheduler()
    # Schedule post-mortem evaluation every 30 minutes
    scheduler.add_job(
        evaluate_all_expired,
        CronTrigger(minute="*/30", timezone="UTC"),
        id="postmortem_eval",
        name="Post-Mortem Signal Evaluation",
        replace_existing=True,
    )
    scheduler.start()
    print("  ✓ Scheduler started (reports + post-mortem evaluation)")

    # Start BTC price spike monitor
    start_monitor()
    print("  ✓ BTC Price Spike Monitor started")
    print(f"  ✓ API ready at http://localhost:8000\n")

    yield

    # Shutdown
    stop_monitor()
    scheduler.shutdown()
    print("👋 Scheduler stopped. Goodbye.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS - allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

