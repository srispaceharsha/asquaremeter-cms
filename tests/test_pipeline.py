"""
Unit tests for pipeline.py - Core CMS functionality

Run with: uv run pytest tests/ -v
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import (
    to_title_case,
    normalize_name,
    get_time_of_day,
    get_season,
    generate_id,
    load_sightings,
    save_sightings,
    load_observations,
    get_moon_phase,
)


class TestToTitleCase:
    """Tests for to_title_case function"""

    def test_basic_lowercase(self):
        assert to_title_case("ground beetle") == "Ground Beetle"

    def test_all_caps(self):
        assert to_title_case("GROUND BEETLE") == "Ground Beetle"

    def test_mixed_case(self):
        assert to_title_case("gRouND beeTLE") == "Ground Beetle"

    def test_single_word(self):
        assert to_title_case("ant") == "Ant"

    def test_empty_string(self):
        assert to_title_case("") == ""

    def test_already_title_case(self):
        assert to_title_case("Ground Beetle") == "Ground Beetle"

    def test_extra_spaces(self):
        # strip() and split/join normalizes spaces
        result = to_title_case("  ground   beetle  ")
        assert result == "Ground Beetle"

    def test_hyphenated_words(self):
        # Python's title() capitalizes after hyphens only if lowercase follows
        assert to_title_case("red-tailed hawk") == "Red-tailed Hawk"

    def test_apostrophe(self):
        # Python's title() may not handle apostrophes ideally
        result = to_title_case("o'brien")
        # Just check it doesn't crash and produces something reasonable
        assert result.startswith("O")

    def test_with_numbers(self):
        assert to_title_case("type 2 beetle") == "Type 2 Beetle"


class TestNormalizeName:
    """Tests for normalize_name function"""

    def test_exact_match_different_case(self):
        existing = {"Ground Beetle", "Fire Ant"}
        assert normalize_name("ground beetle", existing) == "Ground Beetle"
        assert normalize_name("GROUND BEETLE", existing) == "Ground Beetle"
        assert normalize_name("Ground Beetle", existing) == "Ground Beetle"

    def test_no_match_converts_to_title_case(self):
        existing = {"Ground Beetle", "Fire Ant"}
        assert normalize_name("jumping spider", existing) == "Jumping Spider"

    def test_empty_existing_names(self):
        assert normalize_name("ground beetle", set()) == "Ground Beetle"

    def test_empty_input(self):
        existing = {"Ground Beetle"}
        assert normalize_name("", existing) == ""

    def test_whitespace_handling(self):
        existing = {"Ground Beetle"}
        # Strips whitespace before matching
        assert normalize_name("  ground beetle  ", existing) == "Ground Beetle"

    def test_partial_match_no_normalization(self):
        # "Ground" alone should not match "Ground Beetle"
        existing = {"Ground Beetle"}
        assert normalize_name("ground", existing) == "Ground"


class TestGetTimeOfDay:
    """Tests for get_time_of_day function - boundary testing is critical"""

    def test_morning_start_boundary(self):
        dt = datetime(2026, 1, 1, 5, 0, 0)  # 5:00 AM
        assert get_time_of_day(dt) == "morning"

    def test_morning_end_boundary(self):
        dt = datetime(2026, 1, 1, 11, 59, 59)  # 11:59 AM
        assert get_time_of_day(dt) == "morning"

    def test_afternoon_start_boundary(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)  # 12:00 PM
        assert get_time_of_day(dt) == "afternoon"

    def test_afternoon_end_boundary(self):
        dt = datetime(2026, 1, 1, 15, 59, 59)  # 3:59 PM
        assert get_time_of_day(dt) == "afternoon"

    def test_evening_start_boundary(self):
        dt = datetime(2026, 1, 1, 16, 0, 0)  # 4:00 PM
        assert get_time_of_day(dt) == "evening"

    def test_evening_end_boundary(self):
        dt = datetime(2026, 1, 1, 18, 59, 59)  # 6:59 PM
        assert get_time_of_day(dt) == "evening"

    def test_night_start_boundary(self):
        dt = datetime(2026, 1, 1, 19, 0, 0)  # 7:00 PM
        assert get_time_of_day(dt) == "night"

    def test_night_late(self):
        dt = datetime(2026, 1, 1, 23, 0, 0)  # 11:00 PM
        assert get_time_of_day(dt) == "night"

    def test_night_early_morning(self):
        dt = datetime(2026, 1, 1, 4, 59, 59)  # 4:59 AM
        assert get_time_of_day(dt) == "night"

    def test_midnight(self):
        dt = datetime(2026, 1, 1, 0, 0, 0)
        assert get_time_of_day(dt) == "night"


class TestGetSeason:
    """Tests for get_season function - uses month names, not numbers"""

    @pytest.fixture
    def seasons(self):
        # Config uses month names as strings
        return {
            "winter": ["december", "january", "february"],
            "summer": ["march", "april", "may"],
            "monsoon": ["june", "july", "august", "september"],
            "post-monsoon": ["october", "november"]
        }

    def test_winter_months(self, seasons):
        assert get_season(12, seasons) == "winter"
        assert get_season(1, seasons) == "winter"
        assert get_season(2, seasons) == "winter"

    def test_summer_months(self, seasons):
        assert get_season(3, seasons) == "summer"
        assert get_season(4, seasons) == "summer"
        assert get_season(5, seasons) == "summer"

    def test_monsoon_months(self, seasons):
        assert get_season(6, seasons) == "monsoon"
        assert get_season(9, seasons) == "monsoon"

    def test_post_monsoon_months(self, seasons):
        assert get_season(10, seasons) == "post-monsoon"
        assert get_season(11, seasons) == "post-monsoon"

    def test_month_not_in_any_season(self):
        seasons = {"winter": ["december", "january", "february"]}
        assert get_season(6, seasons) == "unknown"

    def test_empty_seasons(self):
        assert get_season(6, {}) == "unknown"


class TestGenerateId:
    """Tests for generate_id function - uniqueness is critical"""

    def test_first_sighting_of_day(self):
        dt = datetime(2026, 1, 15, 10, 30, 0)
        sightings = []
        assert generate_id(dt, sightings) == "20260115-001"

    def test_second_sighting_of_day(self):
        dt = datetime(2026, 1, 15, 14, 30, 0)
        sightings = [{"id": "20260115-001"}]
        assert generate_id(dt, sightings) == "20260115-002"

    def test_multiple_sightings_same_day(self):
        dt = datetime(2026, 1, 15, 16, 0, 0)
        sightings = [
            {"id": "20260115-001"},
            {"id": "20260115-002"},
            {"id": "20260115-003"},
        ]
        assert generate_id(dt, sightings) == "20260115-004"

    def test_different_day_resets_counter(self):
        dt = datetime(2026, 1, 16, 10, 0, 0)
        sightings = [
            {"id": "20260115-001"},
            {"id": "20260115-002"},
        ]
        assert generate_id(dt, sightings) == "20260116-001"

    def test_sightings_from_multiple_days(self):
        dt = datetime(2026, 1, 17, 10, 0, 0)
        sightings = [
            {"id": "20260115-001"},
            {"id": "20260116-001"},
            {"id": "20260116-002"},
            {"id": "20260117-001"},
        ]
        assert generate_id(dt, sightings) == "20260117-002"

    def test_id_format_padding(self):
        dt = datetime(2026, 1, 5, 10, 0, 0)  # Single digit day
        sightings = []
        result = generate_id(dt, sightings)
        assert result == "20260105-001"
        assert len(result) == 12  # YYYYMMDD-NNN


class TestLoadSaveSightings:
    """Tests for load_sightings and save_sightings - data integrity"""

    def test_load_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pipeline.SIGHTINGS_PATH', Path(tmpdir) / "nonexistent.json"):
                result = load_sightings()
                assert result == []

    def test_load_empty_array(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sightings.json"
            path.write_text("[]")
            with patch('pipeline.SIGHTINGS_PATH', path):
                result = load_sightings()
                assert result == []

    def test_load_valid_sightings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sightings.json"
            data = [{"id": "20260101-001", "common_name": "Ant"}]
            path.write_text(json.dumps(data))
            with patch('pipeline.SIGHTINGS_PATH', path):
                result = load_sightings()
                assert len(result) == 1
                assert result[0]["common_name"] == "Ant"

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sightings.json"
            data = [
                {"id": "20260101-001", "common_name": "Ground Beetle"},
                {"id": "20260101-002", "common_name": "Fire Ant"},
            ]
            with patch('pipeline.SIGHTINGS_PATH', path):
                save_sightings(data)
                result = load_sightings()
                assert result == data

    def test_save_preserves_unicode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sightings.json"
            data = [{"id": "20260101-001", "common_name": "Côte d'Ivoire Beetle"}]
            with patch('pipeline.SIGHTINGS_PATH', path):
                save_sightings(data)
                result = load_sightings()
                assert result[0]["common_name"] == "Côte d'Ivoire Beetle"


class TestLoadObservations:
    """Tests for load_observations"""

    def test_load_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pipeline.OBSERVATIONS_PATH', Path(tmpdir) / "nonexistent.json"):
                result = load_observations()
                assert result == []


class TestGetMoonPhase:
    """Tests for get_moon_phase - astronomical accuracy"""

    def test_full_moon_detection(self):
        # January 3, 2026 was a full moon
        dt = datetime(2026, 1, 3, 12, 0, 0)
        result = get_moon_phase(dt)
        assert result["moon_phase"] == "Full Moon"
        assert result["moon_illumination"] >= 0.98

    def test_waxing_before_full(self):
        # January 1-2, 2026 was waxing gibbous (before Jan 3 full moon)
        dt = datetime(2026, 1, 1, 12, 0, 0)
        result = get_moon_phase(dt)
        assert result["moon_phase"] == "Waxing Gibbous"

    def test_waning_after_full(self):
        # January 5-6, 2026 was waning gibbous (after Jan 3 full moon)
        dt = datetime(2026, 1, 5, 12, 0, 0)
        result = get_moon_phase(dt)
        assert result["moon_phase"] == "Waning Gibbous"

    def test_illumination_range(self):
        dt = datetime(2026, 1, 3, 12, 0, 0)
        result = get_moon_phase(dt)
        assert 0 <= result["moon_illumination"] <= 1

    def test_returns_dict_with_required_keys(self):
        dt = datetime(2026, 1, 15, 12, 0, 0)
        result = get_moon_phase(dt)
        assert "moon_phase" in result
        assert "moon_illumination" in result
