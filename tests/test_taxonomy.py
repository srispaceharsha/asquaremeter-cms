"""
Unit tests for taxonomy.py - GBIF API integration and tree building

Run with: uv run pytest tests/ -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from taxonomy import (
    load_cache,
    save_cache,
    build_species_tree,
    get_species_stats,
)


class TestLoadCache:
    """Tests for load_cache function"""

    def test_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('taxonomy.CACHE_PATH', Path(tmpdir) / "nonexistent.json"):
                result = load_cache()
                assert result == {}

    def test_load_valid_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.json"
            data = {"oxyopes salticus": {"class": "Arachnida", "order": "Araneae"}}
            path.write_text(json.dumps(data))
            with patch('taxonomy.CACHE_PATH', path):
                result = load_cache()
                assert result == data


class TestSaveCache:
    """Tests for save_cache function"""

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.json"
            data = {
                "oxyopes salticus": {
                    "class": "Arachnida",
                    "order": "Araneae",
                    "family": "Oxyopidae"
                }
            }
            with patch('taxonomy.CACHE_PATH', path):
                save_cache(data)
                result = load_cache()
                assert result == data

    def test_save_preserves_unicode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.json"
            data = {"species": {"notes": "Found in São Paulo"}}
            with patch('taxonomy.CACHE_PATH', path):
                save_cache(data)
                result = load_cache()
                assert result["species"]["notes"] == "Found in São Paulo"


class TestBuildSpeciesTree:
    """Tests for build_species_tree function"""

    def test_empty_sightings(self):
        result = build_species_tree([], {})
        assert result["tree"] == {}
        assert result["unclassified"] == []

    def test_single_species_with_taxonomy(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Lynx Spider",
                "scientific_name": "Oxyopes salticus",
                "images": [{"filename": "20260101-001-a.jpg"}],
                "notes": "Found on leaf"
            }
        ]
        cache = {
            "oxyopes salticus": {
                "class": "Arachnida",
                "order": "Araneae",
                "family": "Oxyopidae",
                "genus": "Oxyopes",
                "gbif_key": 12345
            }
        }
        result = build_species_tree(sightings, cache)

        assert "Arachnida" in result["tree"]
        assert "Araneae" in result["tree"]["Arachnida"]
        assert "Oxyopidae" in result["tree"]["Arachnida"]["Araneae"]

        species_list = result["tree"]["Arachnida"]["Araneae"]["Oxyopidae"]
        assert len(species_list) == 1
        assert species_list[0]["common_name"] == "Lynx Spider"

    def test_unclassified_species(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Unknown Bug",
                "scientific_name": "Unknown sp.",
                "images": [{"filename": "20260101-001-a.jpg"}],
                "notes": ""
            }
        ]
        cache = {}  # No taxonomy data
        result = build_species_tree(sightings, cache)

        assert result["tree"] == {}
        assert len(result["unclassified"]) == 1
        assert result["unclassified"][0]["common_name"] == "Unknown Bug"

    def test_missing_class_goes_to_unclassified(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Partial Data Bug",
                "scientific_name": "Partial sp.",
                "images": [],
                "notes": ""
            }
        ]
        cache = {
            "partial sp.": {
                "class": None,  # Missing class
                "order": "SomeOrder",
                "family": "SomeFamily"
            }
        }
        result = build_species_tree(sightings, cache)

        assert len(result["unclassified"]) == 1

    def test_multiple_species_same_family(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Lynx Spider",
                "scientific_name": "Oxyopes salticus",
                "images": [{"filename": "20260101-001-a.jpg"}],
                "notes": ""
            },
            {
                "id": "20260101-002",
                "common_name": "Striped Lynx Spider",
                "scientific_name": "Oxyopes sertatus",
                "images": [{"filename": "20260101-002-a.jpg"}],
                "notes": ""
            }
        ]
        cache = {
            "oxyopes salticus": {
                "class": "Arachnida",
                "order": "Araneae",
                "family": "Oxyopidae",
                "genus": "Oxyopes",
                "gbif_key": 12345
            },
            "oxyopes sertatus": {
                "class": "Arachnida",
                "order": "Araneae",
                "family": "Oxyopidae",
                "genus": "Oxyopes",
                "gbif_key": 12346
            }
        }
        result = build_species_tree(sightings, cache)

        species_list = result["tree"]["Arachnida"]["Araneae"]["Oxyopidae"]
        assert len(species_list) == 2

    def test_deduplication_same_species(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Lynx Spider",
                "scientific_name": "Oxyopes salticus",
                "images": [{"filename": "20260101-001-a.jpg"}],
                "notes": ""
            },
            {
                "id": "20260102-001",
                "common_name": "Lynx Spider",
                "scientific_name": "Oxyopes salticus",
                "images": [{"filename": "20260102-001-a.jpg"}],
                "notes": ""
            }
        ]
        cache = {
            "oxyopes salticus": {
                "class": "Arachnida",
                "order": "Araneae",
                "family": "Oxyopidae",
                "genus": "Oxyopes",
                "gbif_key": 12345
            }
        }
        result = build_species_tree(sightings, cache)

        # Should only have one entry but with sighting_count > 1
        species_list = result["tree"]["Arachnida"]["Araneae"]["Oxyopidae"]
        assert len(species_list) == 1
        assert species_list[0]["sighting_count"] == 2

    def test_species_sorted_by_common_name(self):
        sightings = [
            {
                "id": "20260101-001",
                "common_name": "Zebra Spider",
                "scientific_name": "Zebra sp.",
                "images": [],
                "notes": ""
            },
            {
                "id": "20260101-002",
                "common_name": "Alpha Spider",
                "scientific_name": "Alpha sp.",
                "images": [],
                "notes": ""
            }
        ]
        cache = {
            "zebra sp.": {"class": "Arachnida", "order": "Araneae", "family": "TestFamily"},
            "alpha sp.": {"class": "Arachnida", "order": "Araneae", "family": "TestFamily"}
        }
        result = build_species_tree(sightings, cache)

        species_list = result["tree"]["Arachnida"]["Araneae"]["TestFamily"]
        assert species_list[0]["common_name"] == "Alpha Spider"
        assert species_list[1]["common_name"] == "Zebra Spider"


class TestGetSpeciesStats:
    """Tests for get_species_stats function"""

    def test_empty_tree(self):
        tree_data = {"tree": {}, "unclassified": []}
        stats = get_species_stats(tree_data)
        assert stats["total_species"] == 0
        assert stats["classes"] == 0
        assert stats["orders"] == 0
        assert stats["families"] == 0

    def test_counts_unclassified(self):
        tree_data = {
            "tree": {},
            "unclassified": [
                {"common_name": "Bug 1"},
                {"common_name": "Bug 2"}
            ]
        }
        stats = get_species_stats(tree_data)
        assert stats["total_species"] == 2

    def test_counts_classified_species(self):
        tree_data = {
            "tree": {
                "Insecta": {
                    "Coleoptera": {
                        "Chrysomelidae": [
                            {"common_name": "Beetle 1"},
                            {"common_name": "Beetle 2"}
                        ]
                    }
                }
            },
            "unclassified": []
        }
        stats = get_species_stats(tree_data)
        assert stats["total_species"] == 2
        assert stats["classes"] == 1
        assert stats["orders"] == 1
        assert stats["families"] == 1

    def test_counts_multiple_levels(self):
        tree_data = {
            "tree": {
                "Insecta": {
                    "Coleoptera": {
                        "Chrysomelidae": [{"common_name": "Beetle"}],
                        "Carabidae": [{"common_name": "Ground Beetle"}]
                    },
                    "Diptera": {
                        "Muscidae": [{"common_name": "Fly"}]
                    }
                },
                "Arachnida": {
                    "Araneae": {
                        "Salticidae": [{"common_name": "Jumping Spider"}]
                    }
                }
            },
            "unclassified": [{"common_name": "Unknown"}]
        }
        stats = get_species_stats(tree_data)
        assert stats["total_species"] == 5  # 4 classified + 1 unclassified
        assert stats["classes"] == 2  # Insecta, Arachnida
        assert stats["orders"] == 3  # Coleoptera, Diptera, Araneae
        assert stats["families"] == 4  # Chrysomelidae, Carabidae, Muscidae, Salticidae
