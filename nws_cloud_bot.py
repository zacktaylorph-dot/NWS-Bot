#!/usr/bin/env python3
"""
NWS Forecast Telegram Bot
Send a city name to the bot, get back the NWS forecast.

Setup:
1. pip install python-telegram-bot requests
2. Create a bot via @BotFather on Telegram, paste your token below
3. Run: python nws_telegram_bot.py
4. Open Telegram, find your bot, send a city name like "Arcata CA"
"""

import logging
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")  # Set this in Railway environment variables

# How many forecast periods to return (each ~12 hrs; 6 = ~3 days)
PERIODS_TO_SEND = 6

# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def geocode_city(city: str) -> tuple[float, float, str]:
    """Convert a city name to lat/lon using Nominatim (OpenStreetMap)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city,
        "countrycodes": "us",
        "format": "json",
        "limit": 1
    }
    headers = {"User-Agent": "nws-telegram-bot/1.0 (personal use)"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()

    results = resp.json()
    if not results:
        raise ValueError(f"Could not find location: '{city}'")

    match = results[0]
    lat = float(match["lat"])
    lon = float(match["lon"])
    parts = match.get("display_name", city).split(",")
    matched_address = ", ".join(p.strip() for p in parts[:2])
    return lat, lon, matched_address


def get_nws_grid(lat: float, lon: float) -> tuple[str, int, int]:
    """Get NWS grid office and coordinates for a lat/lon."""
    url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    headers = {"User-Agent": "nws-telegram-bot/1.0 (personal use)"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()

    props = resp.json()["properties"]
    return props["gridId"], props["gridX"], props["gridY"]


def get_nws_forecast(office: str, grid_x: int, grid_y: int) -> list:
    """Fetch forecast periods from NWS."""
    url = f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}/forecast"
    headers = {"User-Agent": "nws-telegram-bot/1.0 (personal use)"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()["properties"]["periods"][:PERIODS_TO_SEND]


def format_forecast(periods: list, location_name: str) -> str:
    """Format forecast into a readable Telegram message."""
    lines = [f"📍 {location_name}", ""]
    for p in periods:
        emoji = period_emoji(p["shortForecast"])
        lines.append(
            f"{emoji} *{p['name']}*\n"
            f"{p['temperature']}°{p['temperatureUnit']} | "
            f"Wind: {p['windDirection']} {p['windSpeed']}\n"
            f"{p['shortForecast']}"
        )
        lines.append("")
    return "\n".join(lines).strip()


def period_emoji(short_forecast: str) -> str:
    """Pick a simple weather emoji based on the short forecast string."""
    f = short_forecast.lower()
    if any(w in f for w in ["thunder", "storm"]):
        return "⛈️"
    if any(w in f for w in ["snow", "blizzard", "flurr"]):
        return "❄️"
    if any(w in f for w in ["rain", "shower", "drizzle"]):
        return "🌧️"
    if any(w in f for w in ["fog", "mist"]):
        return "🌫️"
    if any(w in f for w in ["cloud", "overcast"]):
        return "☁️"
    if "partly" in f:
        return "⛅"
    if any(w in f for w in ["sun", "clear", "sunny"]):
        return "☀️"
    if "wind" in f:
        return "💨"
    return "🌡️"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages."""
    city = update.message.text.strip()
    if not city:
        await update.message.reply_text("Send me a city name, like:\nArcata CA\nDenver CO\nPortland OR")
        return

    await update.message.reply_text(f"Looking up forecast for '{city}'...")

    try:
        lat, lon, matched = geocode_city(city)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}\n\nTry a different format, e.g. 'Denver' or 'Denver, Colorado'.")
        return
    except Exception as e:
        await update.message.reply_text(f"❌ Geocoding error: {e}")
        return

    try:
        office, gx, gy = get_nws_grid(lat, lon)
    except Exception:
        await update.message.reply_text(
            "❌ NWS only covers the US. Make sure you're entering a US city."
        )
        return

    try:
        periods = get_nws_forecast(office, gx, gy)
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching forecast: {e}")
        return

    message = format_forecast(periods, matched)
    await update.message.reply_text(message, parse_mode="Markdown")


def main():
    print("Starting NWS Forecast Bot...")
    print("Send a city name in Telegram to get started.")
    print("Press Ctrl+C to stop.\n")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()

# ─────────────────────────────────────────────
# WINDOWS TASK SCHEDULER — run at startup:
#
# 1. Open Task Scheduler > Create Basic Task
# 2. Trigger: "When the computer starts"
# 3. Action: Start a program
#    Program: pythonw.exe
#    Arguments: C:\path\to\nws_telegram_bot.py
# ─────────────────────────────────────────────
