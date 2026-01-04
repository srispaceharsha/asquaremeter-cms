#!/usr/bin/env python3
"""
backfill_weather.py - Update existing sightings with extended weather data

This script fetches additional weather parameters (humidity, pressure, wind,
soil temp, UV index) for all existing sightings that don't have them.

Usage:
    uv run python backfill_weather.py
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests
from dateutil import tz

PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
SIGHTINGS_PATH = PROJECT_ROOT / "data" / "sightings.json"

# Weather code mapping (WMO codes)
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_sightings():
    with open(SIGHTINGS_PATH) as f:
        return json.load(f)


def save_sightings(sightings):
    with open(SIGHTINGS_PATH, "w") as f:
        json.dump(sightings, f, indent=2, ensure_ascii=False)


def fetch_weather(lat, lon, date, timezone_str):
    """Fetch extended weather data from Open-Meteo API"""
    date_str = date.strftime("%Y-%m-%d")
    today = datetime.now().date()
    target_date = date.date()

    # Choose API based on date
    if (today - target_date).days <= 7:
        base_url = "https://api.open-meteo.com/v1/forecast"
    else:
        base_url = "https://archive-api.open-meteo.com/v1/archive"

    daily_params = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "weather_code",
        "relative_humidity_2m_mean",
        "pressure_msl_mean",
        "wind_speed_10m_max",
        "wind_direction_10m_dominant",
        "soil_temperature_0_to_7cm_mean",
        "uv_index_max",
    ]

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_str,
        "end_date": date_str,
        "daily": ",".join(daily_params),
        "timezone": timezone_str,
    }

    response = requests.get(base_url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    daily = data.get("daily", {})
    weather_code = daily.get("weather_code", [0])[0] or 0

    return {
        "temp_max_c": daily.get("temperature_2m_max", [None])[0],
        "temp_min_c": daily.get("temperature_2m_min", [None])[0],
        "precipitation_mm": daily.get("precipitation_sum", [0])[0] or 0,
        "conditions": WEATHER_CODES.get(weather_code, "Unknown"),
        "humidity_percent": daily.get("relative_humidity_2m_mean", [None])[0],
        "pressure_hpa": daily.get("pressure_msl_mean", [None])[0],
        "wind_speed_kmh": daily.get("wind_speed_10m_max", [None])[0],
        "wind_direction_deg": daily.get("wind_direction_10m_dominant", [None])[0],
        "soil_temp_c": daily.get("soil_temperature_0_to_7cm_mean", [None])[0],
        "uv_index": daily.get("uv_index_max", [None])[0],
    }


def main():
    config = load_config()
    sightings = load_sightings()

    lat = config["location"]["latitude"]
    lon = config["location"]["longitude"]
    timezone_str = config["location"]["timezone"]
    local_tz = tz.gettz(timezone_str)

    # Find sightings that need weather backfill
    to_update = []
    for i, s in enumerate(sightings):
        weather = s.get("weather", {})
        # Check if missing new fields
        if "humidity_percent" not in weather:
            to_update.append(i)

    if not to_update:
        print("All sightings already have extended weather data.")
        return

    print(f"Found {len(to_update)} sighting(s) to update")
    print()

    updated = 0
    for idx in to_update:
        s = sightings[idx]
        try:
            captured_at = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=local_tz)

            print(f"Fetching weather for {s['id']} ({s['common_name']})...", end=" ")

            weather = fetch_weather(lat, lon, captured_at, timezone_str)
            sightings[idx]["weather"] = weather

            print(f"OK (humidity: {weather.get('humidity_percent')}%)")
            updated += 1

            # Be nice to the API - wait 0.5 seconds between requests
            time.sleep(0.5)

        except Exception as e:
            print(f"FAILED: {e}")

    save_sightings(sightings)
    print(f"\nUpdated {updated} sighting(s)")


if __name__ == "__main__":
    main()
