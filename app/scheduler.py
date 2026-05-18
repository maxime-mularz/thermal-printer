"""Scheduler pour les taches recurrentes (meteo du matin, etc)."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .config import settings
from .printer import printer, PrintJob
from .weather import fetch_weather, format_weather_text
from .fun import fetch_joke

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def print_weather_now(source: str = "scheduled/meteo"):
    """Recupere et imprime la meteo. Reutilisable depuis Telegram /meteo aussi."""
    try:
        data = await fetch_weather()
        title, body = format_weather_text(data)
        joke = await fetch_joke()
        body += f"\n\n{'- ' * 16}\nLe mot du jour:\n{joke}"
        await printer.submit(PrintJob(
            kind="text", text=body, title=title,
            source=source, align="left", skip_rate_limit=True,
        ))
        logger.info(f"Meteo imprimee ({source})")
    except Exception as e:
        logger.exception(f"Echec meteo: {e}")


async def start():
    global _scheduler
    if not settings.weather_enabled:
        logger.info("Meteo desactivee")
        return
    _scheduler = AsyncIOScheduler(timezone="Europe/Paris")
    _scheduler.add_job(
        print_weather_now,
        CronTrigger(hour=settings.weather_daily_hour, minute=settings.weather_daily_minute),
        id="daily_weather",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler demarre. Meteo quotidienne a {settings.weather_daily_hour:02d}:{settings.weather_daily_minute:02d}")


async def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        logger.info("Scheduler arrete")
