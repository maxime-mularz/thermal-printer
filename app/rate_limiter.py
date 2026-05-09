"""Rate limiter base sur l'historique SQLite."""
from datetime import datetime, timedelta
from .config import settings
from .history import count_recent


def check_limit(source: str) -> tuple[bool, str]:
    """
    Verifie si la source a depasse les limites.
    Retourne (autorise: bool, message: str).
    Les sources "cron" et "system" ne sont jamais limitees.
    """
    if source.startswith(("cron", "system", "scheduled")):
        return True, ""

    now = datetime.now()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)

    n_hour = count_recent(source, hour_ago)
    if n_hour >= settings.rate_limit_per_hour:
        return False, f"Limite horaire atteinte ({n_hour}/{settings.rate_limit_per_hour}). Reessaye dans une heure."

    n_day = count_recent(source, day_ago)
    if n_day >= settings.rate_limit_per_day:
        return False, f"Limite journaliere atteinte ({n_day}/{settings.rate_limit_per_day}). Reessaye demain."

    return True, ""
