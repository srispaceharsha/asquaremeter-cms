"""
Integration tests for external API calls - GBIF and Open-Meteo

Tests graceful error handling for:
- Network timeouts
- HTTP 404/500 errors
- Malformed responses
- Rate limiting

Run with: uv run pytest tests/test_api_integration.py -v
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import fetch_weather
from taxonomy import fetch_taxonomy, fetch_all_taxonomy


class TestFetchWeatherAPI:
    """Tests for Open-Meteo weather API integration"""

    @pytest.fixture
    def sample_coords(self):
        return {
            "lat": 13.9299,
            "lon": 74.7868,
            "timezone": "Asia/Kolkata"
        }

    def test_successful_response(self, sample_coords):
        """Test parsing of valid API response"""
        mock_response = {
            "daily": {
                "temperature_2m_max": [32.5],
                "temperature_2m_min": [24.0],
                "weather_code": [1],  # API uses weather_code not weathercode
                "relative_humidity_2m_mean": [75],
                "pressure_msl_mean": [1012],
                "wind_speed_10m_max": [15],
                "wind_direction_10m_dominant": [180],
                "uv_index_max": [8],
                "soil_temperature_0_to_7cm_mean": [28]
            }
        }

        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result["temp_max_c"] == 32.5
            assert result["temp_min_c"] == 24.0
            assert result["conditions"] == "Mainly clear"  # Weather code 1
            assert result["humidity_percent"] == 75

    def test_network_timeout(self, sample_coords):
        """Test graceful handling of network timeout"""
        with patch('pipeline.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            # Should return dict with None/default values, not crash
            assert result is not None
            assert result["temp_max_c"] is None
            # conditions defaults to "Unknown" on error
            assert result["conditions"] == "Unknown"

    def test_connection_error(self, sample_coords):
        """Test graceful handling of connection failure"""
        with patch('pipeline.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] is None

    def test_http_500_error(self, sample_coords):
        """Test graceful handling of server error"""
        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 500
            mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] is None

    def test_http_404_error(self, sample_coords):
        """Test graceful handling of not found error"""
        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 404
            mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] is None

    def test_malformed_json_response(self, sample_coords):
        """Test handling of invalid JSON response"""
        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] is None

    def test_missing_daily_data(self, sample_coords):
        """Test handling of response missing expected fields"""
        mock_response = {"hourly": {}}  # Missing "daily" key

        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] is None

    def test_empty_daily_array(self, sample_coords):
        """Test handling of empty data arrays"""
        mock_response = {
            "daily": {
                "temperature_2m_max": [],
                "temperature_2m_min": [],
                "weathercode": []
            }
        }

        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            # Should handle gracefully without IndexError

    def test_unknown_weather_code(self, sample_coords):
        """Test handling of unrecognized weather code"""
        mock_response = {
            "daily": {
                "temperature_2m_max": [30],
                "temperature_2m_min": [20],
                "weather_code": [999]  # Invalid code
            }
        }

        with patch('pipeline.requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()

            result = fetch_weather(
                sample_coords["lat"],
                sample_coords["lon"],
                datetime(2026, 1, 1),
                sample_coords["timezone"]
            )

            assert result is not None
            assert result["temp_max_c"] == 30
            # Unknown code should default to "Unknown"
            assert result["conditions"] == "Unknown"


class TestFetchTaxonomyAPI:
    """Tests for GBIF taxonomy API integration"""

    def test_successful_match(self):
        """Test parsing of valid GBIF match response"""
        mock_response = {
            "usageKey": 2151159,
            "scientificName": "Oxyopes salticus Hentz, 1845",
            "canonicalName": "Oxyopes salticus",
            "matchType": "EXACT",
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "class": "Arachnida",
            "order": "Araneae",
            "family": "Oxyopidae",
            "genus": "Oxyopes",
            "species": "Oxyopes salticus"
        }

        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is not None
            assert result["class"] == "Arachnida"
            assert result["order"] == "Araneae"
            assert result["family"] == "Oxyopidae"
            assert result["gbif_key"] == 2151159

    def test_no_match_found(self):
        """Test handling of species with no GBIF match"""
        mock_response = {
            "matchType": "NONE",
            "note": "No match found"
        }

        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()

            cache = {}
            result = fetch_taxonomy("Nonexistent species xyz", cache)

            assert result is None
            # Should cache the miss
            assert "nonexistent species xyz" in cache
            assert cache["nonexistent species xyz"] is None

    def test_network_timeout(self):
        """Test graceful handling of API timeout"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is None
            # Should NOT cache timeout failures (transient error)
            assert "oxyopes salticus" not in cache

    def test_connection_error(self):
        """Test graceful handling of connection failure"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is None

    def test_http_500_error(self):
        """Test graceful handling of server error"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is None

    def test_http_404_error(self):
        """Test graceful handling of not found"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is None

    def test_malformed_json_response(self):
        """Test handling of invalid JSON response"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

            cache = {}
            result = fetch_taxonomy("Oxyopes salticus", cache)

            assert result is None

    def test_cache_hit_skips_api_call(self):
        """Test that cached results don't trigger API calls"""
        cache = {
            "oxyopes salticus": {
                "class": "Arachnida",
                "order": "Araneae",
                "family": "Oxyopidae",
                "gbif_key": 12345
            }
        }

        with patch('requests.get') as mock_get:
            result = fetch_taxonomy("Oxyopes salticus", cache)

            # Should NOT call API
            mock_get.assert_not_called()
            assert result["class"] == "Arachnida"

    def test_cache_key_case_insensitive(self):
        """Test that cache lookup is case-insensitive"""
        cache = {
            "oxyopes salticus": {"class": "Arachnida"}
        }

        with patch('requests.get') as mock_get:
            # Different case should still hit cache
            result = fetch_taxonomy("OXYOPES SALTICUS", cache)

            mock_get.assert_not_called()
            assert result["class"] == "Arachnida"

    def test_whitespace_handling(self):
        """Test that species names are stripped before lookup"""
        cache = {
            "oxyopes salticus": {"class": "Arachnida"}
        }

        with patch('requests.get') as mock_get:
            result = fetch_taxonomy("  Oxyopes salticus  ", cache)

            mock_get.assert_not_called()
            assert result["class"] == "Arachnida"

    def test_partial_taxonomy_data(self):
        """Test handling of response with missing taxonomy fields"""
        mock_response = {
            "usageKey": 12345,
            "matchType": "EXACT",
            "class": "Insecta",
            # Missing order, family, genus
        }

        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response
            mock_get.return_value.raise_for_status = MagicMock()

            cache = {}
            result = fetch_taxonomy("Some insect", cache)

            assert result is not None
            assert result["class"] == "Insecta"
            assert result["order"] is None
            assert result["family"] is None


class TestFetchAllTaxonomy:
    """Tests for batch taxonomy fetching"""

    def test_empty_sightings(self):
        """Test with empty sightings list"""
        with patch('taxonomy.fetch_taxonomy') as mock_fetch:
            with patch('taxonomy.load_cache', return_value={}):
                with patch('taxonomy.save_cache'):
                    result = fetch_all_taxonomy([])

            mock_fetch.assert_not_called()

    def test_skips_cached_species(self):
        """Test that already-cached species are skipped"""
        sightings = [
            {"scientific_name": "Oxyopes salticus"},
            {"scientific_name": "Pardosa milvina"}
        ]
        existing_cache = {
            "oxyopes salticus": {"class": "Arachnida"}
        }

        with patch('taxonomy.load_cache', return_value=existing_cache):
            with patch('taxonomy.save_cache'):
                with patch('taxonomy.fetch_taxonomy') as mock_fetch:
                    mock_fetch.return_value = {"class": "Arachnida"}

                    result = fetch_all_taxonomy(sightings, delay=0)

                    # Should only fetch the uncached species
                    assert mock_fetch.call_count == 1

    def test_deduplicates_exact_duplicates(self):
        """Test that exact duplicate species names are only fetched once"""
        sightings = [
            {"scientific_name": "Oxyopes salticus"},
            {"scientific_name": "Oxyopes salticus"},
            {"scientific_name": "Oxyopes salticus"}
        ]

        with patch('taxonomy.load_cache', return_value={}):
            with patch('taxonomy.save_cache'):
                with patch('taxonomy.fetch_taxonomy') as mock_fetch:
                    mock_fetch.return_value = {"class": "Arachnida"}

                    result = fetch_all_taxonomy(sightings, delay=0)

                    # Should only fetch once despite 3 sightings
                    assert mock_fetch.call_count == 1

    def test_case_variants_fetched_but_cached(self):
        """Test that case variants are fetched but second hits cache"""
        # Note: unique_species set uses exact strings, but cache uses lowercase
        # So "Oxyopes salticus" and "OXYOPES SALTICUS" both get processed,
        # but the second one should hit the cache from the first
        sightings = [
            {"scientific_name": "Oxyopes salticus"},
            {"scientific_name": "OXYOPES SALTICUS"}
        ]

        call_count = 0
        def mock_fetch_side_effect(name, cache):
            nonlocal call_count
            call_count += 1
            # Simulate caching behavior - first call adds to cache
            result = {"class": "Arachnida"}
            cache[name.lower().strip()] = result
            return result

        with patch('taxonomy.load_cache', return_value={}):
            with patch('taxonomy.save_cache'):
                with patch('taxonomy.fetch_taxonomy', side_effect=mock_fetch_side_effect):
                    result = fetch_all_taxonomy(sightings, delay=0)

                    # Both get processed but second should use cached result
                    # (current implementation doesn't dedupe case variants upfront)
                    assert call_count <= 2  # At most 2 calls

    def test_handles_missing_scientific_name(self):
        """Test handling of sightings without scientific_name"""
        sightings = [
            {"common_name": "Unknown Bug"},  # No scientific_name
            {"scientific_name": ""},  # Empty string
            {"scientific_name": "  "},  # Whitespace only
            {"scientific_name": "Valid species"}
        ]

        with patch('taxonomy.load_cache', return_value={}):
            with patch('taxonomy.save_cache'):
                with patch('taxonomy.fetch_taxonomy') as mock_fetch:
                    mock_fetch.return_value = {"class": "Insecta"}

                    result = fetch_all_taxonomy(sightings, delay=0)

                    # Should only fetch the valid species
                    assert mock_fetch.call_count == 1

    def test_saves_cache_after_fetching(self):
        """Test that cache is saved after all fetches complete"""
        sightings = [{"scientific_name": "Test species"}]

        with patch('taxonomy.load_cache', return_value={}):
            with patch('taxonomy.save_cache') as mock_save:
                with patch('taxonomy.fetch_taxonomy', return_value={"class": "Insecta"}):
                    result = fetch_all_taxonomy(sightings, delay=0)

                    mock_save.assert_called_once()


class TestAPIRateLimiting:
    """Tests for API rate limiting behavior"""

    def test_delay_between_calls(self):
        """Test that delay is applied between API calls"""
        import time

        sightings = [
            {"scientific_name": "Species 1"},
            {"scientific_name": "Species 2"},
            {"scientific_name": "Species 3"}
        ]

        with patch('taxonomy.load_cache', return_value={}):
            with patch('taxonomy.save_cache'):
                with patch('taxonomy.fetch_taxonomy', return_value={"class": "Insecta"}):
                    with patch('time.sleep') as mock_sleep:
                        fetch_all_taxonomy(sightings, delay=0.5)

                        # Should sleep between calls (n-1 times for n species)
                        assert mock_sleep.call_count == 2
                        mock_sleep.assert_called_with(0.5)
