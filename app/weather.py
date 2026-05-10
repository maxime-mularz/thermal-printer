"""Recuperation et formatage de la meteo via Open-Meteo (gratuit, sans cle API)."""
import asyncio
import logging
import httpx
from datetime import datetime
from .config import settings

logger = logging.getLogger(__name__)

WMO_CODES = {
    0: ("Ensoleille", "*"),
    1: ("Plutot ensoleille", "*"),
    2: ("Partiellement nuageux", "~"),
    3: ("Couvert", "##"),
    45: ("Brouillard", "==="),
    48: ("Brouillard givrant", "==="),
    51: ("Bruine legere", ".."),
    53: ("Bruine moderee", ".."),
    55: ("Bruine dense", ".."),
    61: ("Pluie faible", "...."),
    63: ("Pluie moderee", "...."),
    65: ("Pluie forte", "////"),
    66: ("Pluie verglacante", "////"),
    67: ("Pluie verglacante", "////"),
    71: ("Neige faible", "***"),
    73: ("Neige moderee", "***"),
    75: ("Neige forte", "***"),
    77: ("Grains de neige", "***"),
    80: ("Averses faibles", "...."),
    81: ("Averses moderees", "...."),
    82: ("Averses fortes", "////"),
    85: ("Averses de neige", "***"),
    86: ("Averses de neige", "***"),
    95: ("Orage", "/Z/"),
    96: ("Orage avec grele", "/Z/"),
    99: ("Orage avec grele", "/Z/"),
}


def _conseil_habillage(t_min: float, t_max: float, code: int, vent: float, pluie: float) -> str:
    parts = []
    if t_max < 0:
        parts.append("Tres froid, gros manteau")
    elif t_max < 10:
        parts.append("Frais, manteau chaud")
    elif t_max < 18:
        parts.append("Doux, veste legere")
    elif t_max < 25:
        parts.append("Agreable, t-shirt OK")
    else:
        parts.append("Chaud, vetements legers")
    if pluie > 1:
        parts.append("parapluie")
    if vent > 30:
        parts.append("attention au vent")
    if code in (71, 73, 75, 77, 85, 86):
        parts.append("bottes de neige")
    return ", ".join(parts) + "."


async def fetch_weather(max_retries: int = 3) -> dict:
    """Appelle l'API Open-Meteo avec retry automatique en cas d'echec reseau."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": settings.weather_latitude,
        "longitude": settings.weather_longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
        "current": "temperature_2m,weather_code",
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    # Timeouts genereux : 30s connect, 45s read (l'API peut etre lente le matin)
    timeout = httpx.Timeout(connect=30.0, read=45.0, write=15.0, pool=10.0)

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
            last_error = e
            logger.warning(f"Tentative meteo {attempt}/{max_retries} echouee: {type(e).__name__}: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)  # backoff exponentiel: 2s, 4s, 8s
    raise RuntimeError(f"Meteo indisponible apres {max_retries} tentatives: {last_error}")


def format_weather_text(data: dict) -> tuple[str, str]:
    daily = data["daily"]
    current = data.get("current", {})
    code = daily["weather_code"][0]
    desc, icon = WMO_CODES.get(code, ("?", ""))

    t_min = daily["temperature_2m_min"][0]
    t_max = daily["temperature_2m_max"][0]
    pluie = daily["precipitation_sum"][0]
    vent = daily["wind_speed_10m_max"][0]
    sunrise = daily["sunrise"][0].split("T")[1][:5]
    sunset = daily["sunset"][0].split("T")[1][:5]
    t_now = current.get("temperature_2m")

    title = f"METEO {settings.weather_city.upper()}"
    today = datetime.now().strftime("%A %d %B").capitalize()

    body_lines = [
        today, "",
        f"  {icon}  {desc}", "",
        f"Temperatures : {t_min:.0f}C / {t_max:.0f}C",
    ]
    if t_now is not None:
        body_lines.append(f"Maintenant   : {t_now:.0f}C")
    body_lines += [
        f"Pluie prevue : {pluie:.1f} mm",
        f"Vent max     : {vent:.0f} km/h",
        f"Soleil       : {sunrise} - {sunset}",
        "",
        _conseil_habillage(t_min, t_max, code, vent, pluie),
    ]
    return title, "\n".join(body_lines)
