"""
Unit tests for build.py - Static site generation and statistics

Run with: uv run pytest tests/ -v
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from collections import OrderedDict

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from build import (
    format_date,
    format_short_date,
    compute_stats,
    escape_xml,
    format_rss_date,
)


class TestFormatDate:
    """Tests for format_date function"""

    def test_iso_format_with_z(self):
        result = format_date("2026-01-15T10:30:00Z")
        assert result == "January 15, 2026"

    def test_iso_format_with_timezone(self):
        result = format_date("2026-01-15T10:30:00+05:30")
        assert result == "January 15, 2026"

    def test_simple_date(self):
        result = format_date("2026-01-15")
        # Should return first 10 chars on parse failure
        assert "2026-01-15" in result or "January" in result

    def test_invalid_date_returns_truncated(self):
        result = format_date("invalid-date-string")
        assert result == "invalid-da"  # First 10 chars

    def test_short_string(self):
        result = format_date("short")
        assert result == "short"


class TestFormatShortDate:
    """Tests for format_short_date function"""

    def test_iso_format(self):
        result = format_short_date("2026-01-15T10:30:00Z")
        assert result == "Jan 15"

    def test_different_months(self):
        assert format_short_date("2026-03-01T00:00:00Z") == "Mar 01"
        assert format_short_date("2026-12-25T00:00:00Z") == "Dec 25"

    def test_invalid_date(self):
        result = format_short_date("invalid")
        assert result == "invalid"


class TestEscapeXml:
    """Tests for escape_xml function - security critical"""

    def test_ampersand(self):
        assert escape_xml("Tom & Jerry") == "Tom &amp; Jerry"

    def test_less_than(self):
        assert escape_xml("a < b") == "a &lt; b"

    def test_greater_than(self):
        assert escape_xml("a > b") == "a &gt; b"

    def test_double_quote(self):
        assert escape_xml('He said "hello"') == "He said &quot;hello&quot;"

    def test_single_quote(self):
        assert escape_xml("It's fine") == "It&apos;s fine"

    def test_multiple_special_chars(self):
        result = escape_xml('<script>alert("XSS")</script>')
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result

    def test_already_safe_string(self):
        assert escape_xml("Hello World") == "Hello World"

    def test_empty_string(self):
        assert escape_xml("") == ""

    def test_numeric_input(self):
        # Should handle non-string input
        assert escape_xml(123) == "123"


class TestFormatRssDate:
    """Tests for format_rss_date function"""

    def test_iso_format_with_time(self):
        result = format_rss_date("2026-01-15T10:30:00Z")
        assert "15 Jan 2026" in result
        assert "+0000" in result

    def test_simple_date_format(self):
        result = format_rss_date("2026-01-15")
        assert "15 Jan 2026" in result

    def test_invalid_date_returns_current(self):
        result = format_rss_date("invalid")
        # Should return current date on failure
        assert "2026" in result or "202" in result  # Flexible for current year


class TestComputeStats:
    """Tests for compute_stats function - complex calculations"""

    @pytest.fixture
    def sample_config(self):
        return {
            "location": {"timezone": "Asia/Kolkata"},
            "seasons": {
                "winter": [12, 1, 2],
                "summer": [3, 4, 5],
                "monsoon": [6, 7, 8, 9],
                "post-monsoon": [10, 11]
            }
        }

    def test_empty_sightings(self, sample_config):
        stats = compute_stats([], [], sample_config)
        assert stats["total_sightings"] == 0
        assert stats["unique_species"] == 0

    def test_total_sightings_count(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["total_sightings"] == 2

    def test_unique_species_count(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260101-003", "common_name": "Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T12:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["unique_species"] == 2  # Ant and Beetle

    def test_unique_species_case_insensitive(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "ANT", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260101-003", "common_name": "ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T12:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["unique_species"] == 1  # All same species

    def test_species_by_category_counts_unique(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260101-003", "common_name": "Spider", "category": "arachnid",
             "season": "winter", "captured_at": "2026-01-01T12:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["by_category"]["insect"] == 1  # Only 1 unique species
        assert stats["by_category"]["arachnid"] == 1

    def test_observations_included_in_unique_species(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
        ]
        observations = [
            {"common_name": "Beetle", "date": "2026-01-01"},
            {"common_name": "Spider", "date": "2026-01-01"},
        ]
        stats = compute_stats(sightings, observations, sample_config)
        assert stats["unique_species"] == 3  # Ant, Beetle, Spider

    def test_days_with_sightings(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T14:00:00Z"},
            {"id": "20260102-001", "common_name": "Spider", "category": "arachnid",
             "season": "winter", "captured_at": "2026-01-02T10:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["days_with_sightings"] == 2  # Jan 1 and Jan 2

    def test_top_species(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260101-003", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T12:00:00Z"},
            {"id": "20260101-004", "common_name": "Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T13:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        # Ant should be top with 3 sightings
        assert stats["top_species"][0] == ("Ant", 3)

    def test_single_sighting_species(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260101-003", "common_name": "Rare Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T12:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert "Rare Beetle" in stats["single_sighting_species"]
        assert "Ant" not in stats["single_sighting_species"]

    def test_by_season(self, sample_config):
        sightings = [
            {"id": "20260101-001", "common_name": "Ant", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T10:00:00Z"},
            {"id": "20260101-002", "common_name": "Beetle", "category": "insect",
             "season": "winter", "captured_at": "2026-01-01T11:00:00Z"},
            {"id": "20260601-001", "common_name": "Spider", "category": "arachnid",
             "season": "monsoon", "captured_at": "2026-06-01T10:00:00Z"},
        ]
        stats = compute_stats(sightings, [], sample_config)
        assert stats["by_season"]["winter"] == 2
        assert stats["by_season"]["monsoon"] == 1
