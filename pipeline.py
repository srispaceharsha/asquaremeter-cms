#!/usr/bin/env python3
"""
pipeline.py - CLI tool for processing new sightings

Commands:
    add       Process all images in inbox/ or a specific file
    log       Quick log a sighting without images (for common species)
    list      List recent sightings
    edit      Edit an existing sighting
    delete    Delete a sighting and its images
    stats     Show project statistics
    status    Show what's been logged today
    addimage  Add additional images to an existing sighting
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import ephem
import requests
from dateutil import parser as date_parser
from dateutil import tz
from PIL import Image
from PIL.ExifTags import TAGS

# Project paths
PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
SIGHTINGS_PATH = PROJECT_ROOT / "data" / "sightings.json"
OBSERVATIONS_PATH = PROJECT_ROOT / "data" / "observations.json"
INBOX_PATH = PROJECT_ROOT / "inbox"
CATALOG_PATH = PROJECT_ROOT / "catalog"

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


def load_config() -> dict:
    """Load configuration from config.json"""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_sightings() -> list:
    """Load all sightings from sightings.json"""
    if not SIGHTINGS_PATH.exists():
        return []
    with open(SIGHTINGS_PATH) as f:
        return json.load(f)


def save_sightings(sightings: list) -> None:
    """Save sightings to sightings.json"""
    with open(SIGHTINGS_PATH, "w") as f:
        json.dump(sightings, f, indent=2, ensure_ascii=False)


def load_observations() -> list:
    """Load all quick observations from observations.json"""
    if not OBSERVATIONS_PATH.exists():
        return []
    with open(OBSERVATIONS_PATH) as f:
        return json.load(f)


def save_observations(observations: list) -> None:
    """Save observations to observations.json"""
    with open(OBSERVATIONS_PATH, "w") as f:
        json.dump(observations, f, indent=2, ensure_ascii=False)


def to_title_case(text: str) -> str:
    """Convert text to Title Case for consistent naming"""
    return " ".join(word.capitalize() for word in text.split())


def normalize_name(name: str, existing_names: set) -> str:
    """Normalize a species name, matching existing if similar"""
    title_name = to_title_case(name.strip())

    # Check for exact match (case-insensitive)
    for existing in existing_names:
        if existing.lower() == title_name.lower():
            return existing

    return title_name


def validate_scientific_name(name: str) -> tuple[bool, str, str]:
    """
    Validate and normalize scientific name format.
    Returns (is_valid, normalized_name, error_message)

    Rules:
    - Genus species (two words): Genus capitalized, species lowercase
    - Genus sp. (unknown species): ends with "sp."
    - Family/Order sp. also allowed
    """
    if not name or not name.strip():
        return True, "", ""  # Empty is allowed

    name = name.strip()
    words = name.split()

    if len(words) < 2:
        return False, name, "Scientific name needs at least two parts (e.g., 'Genus species' or 'Genus sp.')"

    # Normalize: First word capitalized, rest lowercase
    normalized = words[0].capitalize()
    for word in words[1:]:
        normalized += " " + word.lower()

    # Check for "sp" without period
    if normalized.endswith(" sp"):
        return False, normalized, "Did you mean 'sp.' with a period? (e.g., 'Camponotus sp.')"

    # Warn if more than 2 words and not ending in sp.
    if len(words) > 2 and not normalized.endswith(" sp."):
        print(f"  Note: '{normalized}' has more than 2 words. Is this correct?")

    return True, normalized, ""


def validate_common_name(name: str) -> tuple[bool, str, str]:
    """
    Validate common name format.
    Returns (is_valid, normalized_name, error_message)
    """
    if not name or not name.strip():
        return False, "", "Common name is required"

    name = name.strip()

    # Check for obvious issues
    if "(" in name and ")" in name:
        return False, name, "Common name should not contain scientific name in parentheses. Enter them separately."

    # Check minimum length
    if len(name) < 2:
        return False, name, "Common name too short"

    # Normalize to title case
    normalized = to_title_case(name)

    return True, normalized, ""


def validate_category(category: str, valid_categories: list) -> tuple[bool, str, str]:
    """Validate category against allowed values."""
    category = category.strip().lower()
    if category not in valid_categories:
        return False, category, f"Invalid category. Choose from: {', '.join(valid_categories)}"
    return True, category, ""


def prompt_with_validation(prompt_text: str, validator_fn, *validator_args, allow_empty: bool = False) -> str:
    """Generic prompt that keeps asking until valid input is provided."""
    while True:
        value = input(prompt_text).strip()

        if not value and allow_empty:
            return ""

        is_valid, normalized, error = validator_fn(value, *validator_args)

        if is_valid:
            if normalized != value and normalized:
                print(f"  → Normalized to: {normalized}")
            return normalized
        else:
            print(f"  ✗ {error}")


def get_exif_date(image_path: Path) -> Optional[datetime]:
    """Extract DateTimeOriginal from image EXIF data"""
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def prompt_for_date() -> datetime:
    """Prompt user for capture date/time"""
    print("No EXIF date found. Please enter capture date/time.")
    while True:
        date_str = input("Date (YYYY-MM-DD HH:MM or YYYY-MM-DD): ").strip()
        try:
            if " " in date_str:
                return datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            else:
                return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("Invalid format. Use YYYY-MM-DD HH:MM or YYYY-MM-DD")


def get_time_of_day(dt: datetime) -> str:
    """Infer time of day from datetime hour"""
    hour = dt.hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 16:
        return "afternoon"
    elif 16 <= hour < 19:
        return "evening"
    else:
        return "night"


def fetch_weather(lat: float, lon: float, date: datetime, timezone: str) -> dict:
    """Fetch weather data from Open-Meteo API"""
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
        "timezone": timezone,
    }

    try:
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
    except Exception as e:
        print(f"Warning: Could not fetch weather data: {e}")
        return {
            "temp_max_c": None,
            "temp_min_c": None,
            "precipitation_mm": None,
            "conditions": "Unknown",
            "humidity_percent": None,
            "pressure_hpa": None,
            "wind_speed_kmh": None,
            "wind_direction_deg": None,
            "soil_temp_c": None,
            "uv_index": None,
        }


def get_moon_phase(date: datetime) -> dict:
    """Calculate moon phase for a given date"""
    observer = ephem.Observer()
    date_str = date.strftime("%Y/%m/%d")
    observer.date = date_str

    moon = ephem.Moon(observer)
    illumination = moon.phase / 100.0  # 0 to 1

    # Determine if waxing or waning by comparing to next/previous full moon
    next_full = ephem.next_full_moon(date_str)
    prev_full = ephem.previous_full_moon(date_str)
    next_new = ephem.next_new_moon(date_str)
    prev_new = ephem.previous_new_moon(date_str)

    # Calculate days to/from key phases
    days_since_new = float(ephem.Date(date_str) - prev_new)
    days_to_full = float(next_full - ephem.Date(date_str))
    days_since_full = float(ephem.Date(date_str) - prev_full)
    days_to_new = float(next_new - ephem.Date(date_str))

    # Determine phase based on position in lunar cycle
    if days_to_full < 1.0 or days_since_full < 1.0:
        # Within 1 day of full moon
        phase_name = "Full Moon"
    elif days_to_new < 1.0 or days_since_new < 1.0:
        # Within 1 day of new moon
        phase_name = "New Moon"
    elif days_since_new < days_since_full:
        # We're in the first half (waxing) - between new and full
        if illumination < 0.50:
            phase_name = "Waxing Crescent"
        elif illumination < 0.55:
            phase_name = "First Quarter"
        else:
            phase_name = "Waxing Gibbous"
    else:
        # We're in the second half (waning) - between full and new
        if illumination > 0.55:
            phase_name = "Waning Gibbous"
        elif illumination > 0.45:
            phase_name = "Last Quarter"
        else:
            phase_name = "Waning Crescent"

    return {
        "moon_phase": phase_name,
        "moon_illumination": round(illumination, 2),
    }


def get_sun_times(lat: float, lon: float, date: datetime, timezone_str: str) -> dict:
    """Calculate sunrise and sunset times"""
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.date = date.strftime("%Y/%m/%d")

    sun = ephem.Sun()

    try:
        sunrise = observer.next_rising(sun)
        sunset = observer.next_setting(sun)

        # Convert to local timezone
        local_tz = tz.gettz(timezone_str)
        sunrise_local = ephem.Date(sunrise).datetime().replace(tzinfo=tz.UTC).astimezone(local_tz)
        sunset_local = ephem.Date(sunset).datetime().replace(tzinfo=tz.UTC).astimezone(local_tz)

        return {
            "sunrise": sunrise_local.strftime("%H:%M"),
            "sunset": sunset_local.strftime("%H:%M"),
        }
    except Exception:
        return {"sunrise": "Unknown", "sunset": "Unknown"}


def get_season(month: int, season_definitions: dict) -> str:
    """Determine season from month"""
    month_names = [
        "", "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    ]
    month_name = month_names[month]
    for season, months in season_definitions.items():
        if month_name in months:
            return season
    return "unknown"


def generate_id(date: datetime, sightings: list) -> str:
    """Generate sighting ID in format YYYYMMDD-NNN"""
    date_prefix = date.strftime("%Y%m%d")

    # Count existing sightings for this date
    existing = [s for s in sightings if s["id"].startswith(date_prefix)]
    sequence = len(existing) + 1

    return f"{date_prefix}-{sequence:03d}"


def process_image(input_path: Path, output_id: str, letter: str) -> str:
    """Process image into three sizes, upload to R2, return filename"""
    from r2_upload import is_r2_configured, upload_to_r2

    img = Image.open(input_path)

    # Convert RGBA to RGB if necessary
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    filename = f"{output_id}-{letter}.jpg"

    # Thumbnail (300px wide, higher quality)
    thumb = img.copy()
    thumb.thumbnail((300, 10000), Image.LANCZOS)
    thumb_path = CATALOG_PATH / "thumb" / filename
    thumb.save(thumb_path, "JPEG", quality=90)

    # Web (1200px wide, high quality)
    web = img.copy()
    web.thumbnail((1200, 10000), Image.LANCZOS)
    web_path = CATALOG_PATH / "web" / filename
    web.save(web_path, "JPEG", quality=92)

    # Full (original size as JPG)
    full_path = CATALOG_PATH / "full" / filename
    img.save(full_path, "JPEG", quality=95)

    # Upload to R2 if configured
    if is_r2_configured():
        upload_to_r2(thumb_path, f"thumb/{filename}")
        upload_to_r2(web_path, f"web/{filename}")
        upload_to_r2(full_path, f"full/{filename}")

    return filename


def cmd_add(args):
    """Process images from inbox and add as sightings"""
    config = load_config()
    sightings = load_sightings()

    # Get images to process
    if args.file:
        image_files = [Path(args.file)]
    else:
        image_files = sorted([
            f for f in INBOX_PATH.iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg", ".png")
        ])

    if not image_files:
        print("No images found in inbox/")
        return

    print(f"Found {len(image_files)} image(s) to process\n")
    added_count = 0

    for idx, image_path in enumerate(image_files, 1):
        print(f"Processing: {image_path.name} ({idx} of {len(image_files)})")

        # Get capture date
        captured_at = get_exif_date(image_path)
        if captured_at:
            print(f"Captured: {captured_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            captured_at = prompt_for_date()

        # Add timezone info
        local_tz = tz.gettz(config["location"]["timezone"])
        captured_at = captured_at.replace(tzinfo=local_tz)

        print()

        # Build set of existing species names for normalization
        observations = load_observations()
        existing_species = set(s["common_name"] for s in sightings)
        existing_species.update(o["common_name"] for o in observations)

        # Collect metadata with validation
        while True:
            common_name_input = input("Common name: ").strip()
            is_valid, common_name, error = validate_common_name(common_name_input)
            if is_valid:
                # Also check against existing names for normalization
                common_name = normalize_name(common_name, existing_species)
                if common_name != common_name_input:
                    print(f"  → Normalized to: {common_name}")
                break
            print(f"  ✗ {error}")

        while True:
            scientific_name_input = input("Scientific name (blank if unknown): ").strip()
            if not scientific_name_input:
                scientific_name = ""
                break
            is_valid, scientific_name, error = validate_scientific_name(scientific_name_input)
            if is_valid:
                if scientific_name != scientific_name_input:
                    print(f"  → Normalized to: {scientific_name}")
                break
            print(f"  ✗ {error}")

        # Category selection with validation
        categories = config["categories"]
        cat_str = "/".join(categories)
        while True:
            category_input = input(f"Category [{cat_str}]: ").strip()
            is_valid, category, error = validate_category(category_input, categories)
            if is_valid:
                break
            print(f"  ✗ {error}")

        notes = input("Notes: ").strip()

        # Size in mm (optional)
        size_input = input("Size in mm (optional): ").strip()
        size_mm = None
        if size_input:
            try:
                size_mm = float(size_input)
            except ValueError:
                print("Invalid size, skipping.")

        # ID Certainty (optional)
        print("ID Certainty: [H]igh, [M]edium, [L]ow, or skip")
        certainty_input = input("ID Certainty: ").strip().lower()
        id_certainty = None
        if certainty_input in ["h", "high"]:
            id_certainty = "high"
        elif certainty_input in ["m", "medium"]:
            id_certainty = "medium"
        elif certainty_input in ["l", "low"]:
            id_certainty = "low"

        # Time of day - infer from capture time
        inferred_tod = get_time_of_day(captured_at)
        times_of_day = ["morning", "afternoon", "evening", "night"]
        tod_input = input(f"Time of day [{inferred_tod}]: ").strip().lower()
        if tod_input and tod_input in times_of_day:
            time_of_day = tod_input
        elif tod_input and tod_input not in times_of_day:
            print(f"Invalid. Using inferred: {inferred_tod}")
            time_of_day = inferred_tod
        else:
            time_of_day = inferred_tod

        # Tags (comma-separated)
        existing_tags = set()
        for s in sightings:
            existing_tags.update(s.get("tags", []))
        if existing_tags:
            print(f"Existing tags: {', '.join(sorted(existing_tags))}")
        tags_input = input("Tags (comma-separated): ").strip()
        tags = [normalize_name(t, existing_tags) for t in tags_input.split(",") if t.strip()]

        # Collect additional images for same sighting
        images_to_process = [(image_path, "a")]
        letter_idx = 1  # b, c, d...

        while True:
            add_more = input("\nAdd another image to this sighting? [y/N]: ").strip().lower()
            if add_more != "y":
                break

            extra_path = input("Image path: ").strip()
            if extra_path and Path(extra_path).exists():
                letter = chr(ord("a") + letter_idx)
                images_to_process.append((Path(extra_path), letter))
                letter_idx += 1
            else:
                print("File not found")

        # Generate ID
        sighting_id = generate_id(captured_at, sightings)

        # Process all images
        processed_images = []
        for img_path, letter in images_to_process:
            filename = process_image(img_path, sighting_id, letter)

            caption = ""
            if len(images_to_process) > 1:
                caption = input(f"Caption for {img_path.name} (optional): ").strip()

            processed_images.append({
                "filename": filename,
                "caption": caption,
            })

            # Move original from inbox (if it's in inbox)
            if img_path.parent == INBOX_PATH:
                img_path.unlink()

        # Fetch weather
        print("\nFetching weather data...")
        weather = fetch_weather(
            config["location"]["latitude"],
            config["location"]["longitude"],
            captured_at,
            config["location"]["timezone"],
        )

        # Calculate celestial data
        moon_data = get_moon_phase(captured_at)
        sun_data = get_sun_times(
            config["location"]["latitude"],
            config["location"]["longitude"],
            captured_at,
            config["location"]["timezone"],
        )
        celestial = {**moon_data, **sun_data}

        # Determine season
        season = get_season(captured_at.month, config["season_definitions"])

        # Create sighting entry
        sighting = {
            "id": sighting_id,
            "images": processed_images,
            "common_name": common_name,
            "scientific_name": scientific_name,
            "category": category,
            "captured_at": captured_at.isoformat(),
            "time_of_day": time_of_day,
            "tags": tags,
            "weather": weather,
            "celestial": celestial,
            "season": season,
            "notes": notes,
            "size_mm": size_mm,
            "id_certainty": id_certainty,
            "created_at": datetime.now(local_tz).isoformat(),
        }

        sightings.append(sighting)
        save_sightings(sightings)
        added_count += 1

        # Print confirmation
        sci_name = f" ({scientific_name})" if scientific_name else ""
        temp_str = f"{weather['temp_max_c']}°C max" if weather['temp_max_c'] else "N/A"

        print(f"\n✓ Added: {sighting_id} - {common_name}{sci_name}")
        print(f"  Weather: {temp_str}, {weather['conditions']}")
        print(f"  Moon: {celestial['moon_phase']} ({int(celestial['moon_illumination']*100)}%)")
        print("-" * 50 + "\n")

    print(f"\nSummary: {added_count} sighting(s) added")


def cmd_log(args):
    """Quick log sightings without images (for common species)"""
    config = load_config()
    observations = load_observations()
    sightings = load_sightings()

    # Build species lookup: common_name -> list of (common_name, scientific_name) tuples
    # This handles cases where same common name has multiple scientific names
    species_lookup = {}
    for s in sightings:
        cn = s["common_name"].lower()
        sn = s.get("scientific_name", "")
        if cn not in species_lookup:
            species_lookup[cn] = []
        entry = (s["common_name"], sn)
        if entry not in species_lookup[cn]:
            species_lookup[cn].append(entry)

    # Build set of existing species names for normalization
    existing_species = set(s["common_name"] for s in sightings)
    existing_species.update(o["common_name"] for o in observations)

    # Get current date/time
    local_tz = tz.gettz(config["location"]["timezone"])
    now = datetime.now(local_tz)

    # Get species names - from argument or prompt (comma-separated)
    if args.species:
        species_input = args.species
    else:
        # Show known species in 3 columns with scientific names
        if species_lookup:
            print("Known species:")
            # Build list of "Common Name (Scientific Name)" strings
            species_list_display = []
            for cn_lower in sorted(species_lookup.keys()):
                for common_name, sci_name in species_lookup[cn_lower]:
                    if sci_name:
                        species_list_display.append(f"{common_name} ({sci_name})")
                    else:
                        species_list_display.append(common_name)

            # Print in 2 columns
            col_width = max(len(s) for s in species_list_display) + 2
            cols = 2
            for i in range(0, len(species_list_display), cols):
                row = species_list_display[i:i + cols]
                print("  " + "".join(s.ljust(col_width) for s in row))
            print()
        species_input = input("Species (comma-separated): ").strip()

    if not species_input:
        print("No species name provided.")
        return

    # Parse comma-separated species and normalize names
    species_list_raw = [s.strip() for s in species_input.split(",") if s.strip()]
    species_list = [normalize_name(s, existing_species) for s in species_list_raw]

    if not species_list:
        print("No species name provided.")
        return

    # Time of day (shared for all)
    times_of_day = ["morning", "afternoon", "evening", "night"]
    tod_str = "/".join(times_of_day)
    while True:
        time_of_day = input(f"Time of day [{tod_str}]: ").strip().lower()
        if time_of_day in times_of_day:
            break
        print(f"Invalid. Choose from: {tod_str}")

    # Fetch weather and celestial data for today (shared for all observations)
    print("Fetching weather data...")
    weather = fetch_weather(
        config["location"]["latitude"],
        config["location"]["longitude"],
        now,
        config["location"]["timezone"],
    )
    moon_data = get_moon_phase(now)
    sun_data = get_sun_times(
        config["location"]["latitude"],
        config["location"]["longitude"],
        now,
        config["location"]["timezone"],
    )
    celestial = {**moon_data, **sun_data}

    # Build lookup of species with sightings today (to avoid duplicates)
    today_str = now.strftime("%Y-%m-%d")
    sightings_today = set()
    for s in sightings:
        if s["captured_at"][:10] == today_str:
            sightings_today.add(s["common_name"].lower())

    # Log each species
    print()
    logged_count = 0
    for common_name in species_list:
        # Check if there's already a sighting for this species today
        if common_name.lower() in sightings_today:
            print(f"⚠ {common_name} - skipped (already has sighting today)")
            continue

        # Check if there are multiple species with this common name
        cn_lower = common_name.lower()
        scientific_name = ""

        if cn_lower in species_lookup and len(species_lookup[cn_lower]) > 1:
            # Multiple species with same common name - ask user to choose
            print(f"\nMultiple species found for \"{common_name}\":")
            options = species_lookup[cn_lower]
            for i, (cn, sn) in enumerate(options, 1):
                print(f"  {i}. {cn} ({sn})")

            while True:
                choice = input(f"Which one? [1-{len(options)}]: ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(options):
                        common_name, scientific_name = options[idx]
                        break
                except ValueError:
                    pass
                print(f"Invalid. Enter 1-{len(options)}")
        elif cn_lower in species_lookup:
            # Single species - use its scientific name
            common_name, scientific_name = species_lookup[cn_lower][0]

        observation = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "common_name": common_name,
            "scientific_name": scientific_name,
            "time_of_day": time_of_day,
            "note": "",
            "created_at": now.isoformat(),
            "weather": weather,
            "celestial": celestial,
        }

        observations.append(observation)
        logged_count += 1

        # Count total for this species (by scientific name if available, else common name)
        if scientific_name:
            sighting_count = sum(1 for s in sightings if s.get("scientific_name", "").lower() == scientific_name.lower())
            observation_count = sum(1 for o in observations if o.get("scientific_name", "").lower() == scientific_name.lower())
        else:
            sighting_count = sum(1 for s in sightings if s["common_name"].lower() == common_name.lower())
            observation_count = sum(1 for o in observations if o["common_name"].lower() == common_name.lower())
        total_count = sighting_count + observation_count

        if scientific_name:
            print(f"✓ {common_name} ({scientific_name}) - total: {total_count}")
        else:
            print(f"✓ {common_name} (total: {total_count})")

    save_observations(observations)
    skipped = len(species_list) - logged_count
    if skipped:
        print(f"\nLogged {logged_count} observation(s), skipped {skipped} (already had sighting today)")
    else:
        print(f"\nLogged {logged_count} observation(s)")


def cmd_list(args):
    """List recent sightings"""
    sightings = load_sightings()

    if not sightings:
        print("No sightings yet.")
        return

    # Filter by category or season if specified
    filtered = sightings
    if args.category:
        filtered = [s for s in filtered if s["category"] == args.category]
    if args.season:
        filtered = [s for s in filtered if s["season"] == args.season]

    # Sort by date descending and limit
    filtered = sorted(filtered, key=lambda s: s["captured_at"], reverse=True)
    filtered = filtered[: args.last]

    if not filtered:
        print("No matching sightings found.")
        return

    print(f"{'ID':<15} {'Date':<12} {'Name':<25} {'Category':<10}")
    print("-" * 65)

    for s in filtered:
        date = s["captured_at"][:10]
        name = s["common_name"][:24]
        print(f"{s['id']:<15} {date:<12} {name:<25} {s['category']:<10}")


def cmd_edit(args):
    """Edit an existing sighting"""
    sightings = load_sightings()

    # Find sighting by ID
    sighting = None
    sighting_idx = None
    for idx, s in enumerate(sightings):
        if s["id"] == args.id:
            sighting = s
            sighting_idx = idx
            break

    if not sighting:
        print(f"Sighting {args.id} not found.")
        return

    print(f"Editing: {sighting['id']} - {sighting['common_name']}")
    print("Press Enter to keep current value.\n")

    config = load_config()

    # Edit common name with validation
    while True:
        new_name = input(f"Common name [{sighting['common_name']}]: ").strip()
        if not new_name:
            break  # Keep current
        is_valid, normalized, error = validate_common_name(new_name)
        if is_valid:
            sighting["common_name"] = normalized
            if normalized != new_name:
                print(f"  → Normalized to: {normalized}")
            break
        print(f"  ✗ {error}")

    # Edit scientific name with validation
    while True:
        new_sci = input(f"Scientific name [{sighting['scientific_name']}]: ").strip()
        if not new_sci:
            break  # Keep current
        is_valid, normalized, error = validate_scientific_name(new_sci)
        if is_valid:
            sighting["scientific_name"] = normalized
            if normalized != new_sci:
                print(f"  → Normalized to: {normalized}")
            break
        print(f"  ✗ {error}")

    # Edit category with validation
    cat_str = "/".join(config["categories"])
    while True:
        new_cat = input(f"Category [{sighting['category']}] ({cat_str}): ").strip()
        if not new_cat:
            break  # Keep current
        is_valid, normalized, error = validate_category(new_cat, config["categories"])
        if is_valid:
            sighting["category"] = normalized
            break
        print(f"  ✗ {error}")

    new_notes = input(f"Notes [{sighting['notes']}]: ").strip()
    if new_notes:
        sighting["notes"] = new_notes

    # Size in mm
    current_size = sighting.get('size_mm', '')
    size_display = current_size if current_size else 'not set'
    new_size = input(f"Size in mm [{size_display}]: ").strip()
    if new_size:
        try:
            sighting["size_mm"] = float(new_size)
        except ValueError:
            print("Invalid size, keeping current value.")

    # ID Certainty
    current_certainty = sighting.get('id_certainty', '')
    certainty_display = current_certainty if current_certainty else 'not set'
    print(f"ID Certainty [{certainty_display}]: [H]igh, [M]edium, [L]ow, or skip")
    new_certainty = input("ID Certainty: ").strip().lower()
    if new_certainty in ["h", "high"]:
        sighting["id_certainty"] = "high"
    elif new_certainty in ["m", "medium"]:
        sighting["id_certainty"] = "medium"
    elif new_certainty in ["l", "low"]:
        sighting["id_certainty"] = "low"

    # Time of day
    current_tod = sighting.get('time_of_day', '')
    times_of_day = ["morning", "afternoon", "evening", "night"]
    tod_str = "/".join(times_of_day)
    new_tod = input(f"Time of day [{current_tod}] ({tod_str}): ").strip().lower()
    if new_tod and new_tod in times_of_day:
        sighting["time_of_day"] = new_tod

    # Tags
    current_tags = ", ".join(sighting.get('tags', []))
    new_tags_input = input(f"Tags [{current_tags}]: ").strip()
    if new_tags_input:
        sighting["tags"] = [t.strip().lower() for t in new_tags_input.split(",") if t.strip()]

    sightings[sighting_idx] = sighting
    save_sightings(sightings)
    print(f"\n✓ Updated: {sighting['id']}")


def cmd_delete(args):
    """Delete a sighting and its associated images"""
    sightings = load_sightings()

    # Find sighting by ID
    sighting = None
    sighting_idx = None
    for idx, s in enumerate(sightings):
        if s["id"] == args.id:
            sighting = s
            sighting_idx = idx
            break

    if not sighting:
        print(f"Sighting {args.id} not found.")
        return

    # Show sighting details
    print(f"\nSighting to delete:")
    print(f"  ID: {sighting['id']}")
    print(f"  Name: {sighting['common_name']}")
    if sighting['scientific_name']:
        print(f"  Scientific name: {sighting['scientific_name']}")
    print(f"  Category: {sighting['category']}")
    print(f"  Date: {sighting['captured_at'][:10]}")
    print(f"  Images: {len(sighting['images'])}")
    for img in sighting['images']:
        print(f"    - {img['filename']}")

    # Confirm deletion
    if not args.force:
        confirm = input("\nAre you sure you want to delete this sighting? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Delete image files (local and R2)
    deleted_images = []
    deleted_r2 = []

    # Check if R2 is configured
    try:
        from r2_upload import is_r2_configured, delete_from_r2
        r2_enabled = is_r2_configured()
    except ImportError:
        r2_enabled = False

    for img in sighting['images']:
        filename = img['filename']
        for size in ["thumb", "web", "full"]:
            # Delete local file
            img_path = CATALOG_PATH / size / filename
            if img_path.exists():
                img_path.unlink()
                deleted_images.append(f"{size}/{filename}")

            # Delete from R2
            if r2_enabled:
                r2_key = f"{size}/{filename}"
                if delete_from_r2(r2_key):
                    deleted_r2.append(r2_key)

    # Add as observation before deleting (to preserve the record)
    from datetime import datetime
    from dateutil import tz as dateutil_tz

    config = load_config()
    local_tz = dateutil_tz.gettz(config["location"]["timezone"])

    # Extract date/time from sighting
    captured_at = sighting["captured_at"]
    sighting_date = captured_at[:10]  # YYYY-MM-DD
    sighting_time = captured_at[11:16]  # HH:MM

    observation = {
        "date": sighting_date,
        "time": sighting_time,
        "common_name": sighting["common_name"],
        "time_of_day": sighting.get("time_of_day", ""),
        "note": f"Converted from deleted sighting {sighting['id']}",
        "created_at": datetime.now(local_tz).isoformat(),
    }

    # Copy weather/celestial from sighting if available
    if sighting.get("weather"):
        observation["weather"] = sighting["weather"]
    if sighting.get("celestial"):
        observation["celestial"] = sighting["celestial"]

    observations = load_observations()
    observations.append(observation)
    save_observations(observations)

    # Remove from sightings list
    sightings.pop(sighting_idx)
    save_sightings(sightings)

    print(f"\n✓ Deleted: {sighting['id']} - {sighting['common_name']}")
    print(f"  Added as observation for {sighting_date}")
    print(f"  Removed {len(deleted_images)} local image files")
    if deleted_r2:
        print(f"  Removed {len(deleted_r2)} images from R2")


def cmd_status(args):
    """Show what's been logged today"""
    from datetime import date

    today = date.today().isoformat()

    sightings = load_sightings()
    observations = load_observations()

    # Get today's sightings
    today_sightings = []
    for s in sightings:
        if s["captured_at"][:10] == today:
            today_sightings.append(s["common_name"])

    # Get today's observations
    today_observations = []
    for o in observations:
        if o["date"] == today:
            today_observations.append(o["common_name"])

    print(f"\nToday ({today})")
    print("=" * 40)

    print(f"\nSightings ({len(today_sightings)}):")
    if today_sightings:
        for name in sorted(set(today_sightings)):
            count = today_sightings.count(name)
            if count > 1:
                print(f"  {name} (x{count})")
            else:
                print(f"  {name}")
    else:
        print("  (none)")

    print(f"\nObservations ({len(today_observations)}):")
    if today_observations:
        for name in sorted(set(today_observations)):
            count = today_observations.count(name)
            if count > 1:
                print(f"  {name} (x{count})")
            else:
                print(f"  {name}")
    else:
        print("  (none)")

    print()


def cmd_stats(args):
    """Show project statistics"""
    config = load_config()
    sightings = load_sightings()

    if not sightings:
        print("No sightings yet.")
        return

    # Basic counts
    total = len(sightings)

    # By category
    by_category = {}
    for s in sightings:
        cat = s["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    # By season
    by_season = {}
    for s in sightings:
        season = s["season"]
        by_season[season] = by_season.get(season, 0) + 1

    # Date range
    dates = [s["captured_at"][:10] for s in sightings]
    first_date = min(dates)
    last_date = max(dates)

    # Species count (unique common names)
    species = set(s["common_name"].lower() for s in sightings)

    print(f"\n{config['site_title']} - Statistics")
    print("=" * 40)
    print(f"Total sightings: {total}")
    print(f"Unique species: {len(species)}")
    print(f"Date range: {first_date} to {last_date}")

    print(f"\nBy Category:")
    for cat in sorted(by_category.keys()):
        print(f"  {cat}: {by_category[cat]}")

    print(f"\nBy Season:")
    for season in sorted(by_season.keys()):
        print(f"  {season}: {by_season[season]}")


def cmd_addimage(args):
    """Add additional images to an existing sighting"""
    sightings = load_sightings()

    # Find the sighting
    sighting = None
    for s in sightings:
        if s["id"] == args.id:
            sighting = s
            break

    if not sighting:
        print(f"Sighting not found: {args.id}")
        return

    # Check image path exists
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image not found: {args.image}")
        return

    if image_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        print("Only .jpg, .jpeg, and .png files are supported")
        return

    # Determine the next letter for the image
    existing_images = sighting.get("images", [])
    if existing_images:
        # Find the highest letter used
        last_letter = max(img["filename"].split("-")[-1].split(".")[0] for img in existing_images)
        next_letter = chr(ord(last_letter) + 1)
    else:
        next_letter = "a"

    print(f"Adding image to: {sighting['common_name']} ({args.id})")
    print(f"  Current images: {len(existing_images)}")
    print(f"  New image will be: {args.id}-{next_letter}.jpg")

    # Process the image
    filename = process_image(image_path, args.id, next_letter)

    # Add to sighting
    sighting["images"].append({
        "filename": filename,
        "caption": ""
    })

    save_sightings(sightings)

    print(f"  Added: {filename}")

    # Optionally delete source file
    if not args.keep:
        image_path.unlink()
        print(f"  Deleted source: {image_path.name}")

    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline CLI for One Square Meter biodiversity project"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # add command
    add_parser = subparsers.add_parser("add", help="Add new sightings from inbox")
    add_parser.add_argument("--file", "-f", help="Process specific file instead of inbox")

    # list command
    list_parser = subparsers.add_parser("list", help="List recent sightings")
    list_parser.add_argument("--last", "-n", type=int, default=10, help="Number of entries")
    list_parser.add_argument("--category", "-c", help="Filter by category")
    list_parser.add_argument("--season", "-s", help="Filter by season")

    # edit command
    edit_parser = subparsers.add_parser("edit", help="Edit existing sighting")
    edit_parser.add_argument("id", help="Sighting ID to edit")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a sighting and its images")
    delete_parser.add_argument("id", help="Sighting ID to delete")
    delete_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # log command
    log_parser = subparsers.add_parser("log", help="Quick log a sighting without images")
    log_parser.add_argument("species", nargs="?", help="Species name (optional, will prompt if not provided)")

    # stats command
    subparsers.add_parser("stats", help="Show project statistics")

    # status command
    subparsers.add_parser("status", help="Show what's been logged today")

    # addimage command
    addimage_parser = subparsers.add_parser("addimage", help="Add image to existing sighting")
    addimage_parser.add_argument("id", help="Sighting ID (e.g., 20260101-001)")
    addimage_parser.add_argument("image", help="Path to image file")
    addimage_parser.add_argument("--keep", "-k", action="store_true", help="Keep source file (don't delete)")

    # logweb command
    subparsers.add_parser("logweb", help="Open web UI for logging observations")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "edit":
        cmd_edit(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "addimage":
        cmd_addimage(args)
    elif args.command == "logweb":
        import logweb
        logweb.main()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
