#!/usr/bin/env python3
"""
taxonomy.py - Fetch and cache taxonomy data from GBIF API

This module handles:
- Fetching taxonomy data from GBIF Species API
- Caching results to avoid repeated API calls
- Building tree structure for the species tree page
"""

import json
import time
from pathlib import Path
from typing import Optional

import requests

PROJECT_ROOT = Path(__file__).parent
CACHE_PATH = PROJECT_ROOT / "data" / "taxonomy_cache.json"

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"


def load_cache() -> dict:
    """Load taxonomy cache from disk"""
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    """Save taxonomy cache to disk"""
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def fetch_taxonomy(scientific_name: str, cache: dict) -> Optional[dict]:
    """
    Fetch taxonomy data from GBIF API for a species.

    Returns dict with: class, order, family, genus, gbif_key
    Returns None if species cannot be matched.
    """
    # Check cache first
    cache_key = scientific_name.lower().strip()
    if cache_key in cache:
        return cache[cache_key]

    # Query GBIF API
    try:
        response = requests.get(
            GBIF_MATCH_URL,
            params={"name": scientific_name},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Check if we got a match
        if data.get("matchType") == "NONE":
            print(f"  GBIF: No match for '{scientific_name}'")
            # Cache the miss to avoid repeated lookups
            cache[cache_key] = None
            return None

        # Extract taxonomy levels we care about
        taxonomy = {
            "kingdom": data.get("kingdom"),
            "phylum": data.get("phylum"),
            "class": data.get("class"),
            "order": data.get("order"),
            "family": data.get("family"),
            "genus": data.get("genus"),
            "species": data.get("species") or data.get("canonicalName"),
            "gbif_key": data.get("usageKey"),
            "canonical_name": data.get("canonicalName"),
            "match_type": data.get("matchType"),
        }

        # Cache the result
        cache[cache_key] = taxonomy

        return taxonomy

    except Exception as e:
        print(f"  GBIF API error for '{scientific_name}': {e}")
        return None


def fetch_all_taxonomy(sightings: list, delay: float = 0.3) -> dict:
    """
    Fetch taxonomy for all unique species in sightings.

    Args:
        sightings: List of sighting dicts with 'scientific_name' field
        delay: Seconds to wait between API calls (be nice to GBIF)

    Returns:
        Updated cache dict
    """
    cache = load_cache()

    # Get unique scientific names
    unique_species = set()
    for s in sightings:
        sci_name = s.get("scientific_name", "").strip()
        if sci_name:
            unique_species.add(sci_name)

    print(f"Fetching taxonomy for {len(unique_species)} unique species...")

    fetched = 0
    for sci_name in sorted(unique_species):
        cache_key = sci_name.lower().strip()
        if cache_key not in cache:
            print(f"  Fetching: {sci_name}")
            fetch_taxonomy(sci_name, cache)
            fetched += 1
            # Be nice to the API
            if fetched < len(unique_species):
                time.sleep(delay)
        else:
            print(f"  Cached: {sci_name}")

    # Save updated cache
    save_cache(cache)
    print(f"Taxonomy cache updated ({fetched} new, {len(cache)} total)")

    return cache


def build_species_tree(sightings: list, cache: dict) -> dict:
    """
    Build a nested tree structure from sightings and taxonomy data.

    Structure:
    {
        "Insecta": {
            "Coleoptera": {
                "Chrysomelidae": [
                    {species_data},
                    {species_data}
                ]
            }
        }
    }
    """
    tree = {}
    unclassified = []

    # Group sightings by species (use first/best sighting for each)
    species_sightings = {}
    for s in sightings:
        sci_name = s.get("scientific_name", "").strip().lower()
        if sci_name and sci_name not in species_sightings:
            species_sightings[sci_name] = s
        elif sci_name:
            # Count additional sightings
            if "sighting_count" not in species_sightings[sci_name]:
                species_sightings[sci_name]["sighting_count"] = 1
            species_sightings[sci_name]["sighting_count"] += 1

    for sci_name, sighting in species_sightings.items():
        taxonomy = cache.get(sci_name)

        if not taxonomy or not taxonomy.get("class"):
            # No taxonomy data - add to unclassified
            images = sighting.get("images") or []
            unclassified.append({
                "common_name": sighting.get("common_name", "Unknown"),
                "scientific_name": sighting.get("scientific_name", ""),
                "sighting_id": sighting.get("id"),
                "image": images[0].get("filename", "") if images else "",
                "notes": sighting.get("notes", ""),
                "sighting_count": sighting.get("sighting_count", 1),
            })
            continue

        # Get taxonomy levels
        class_name = taxonomy.get("class") or "Unknown Class"
        order_name = taxonomy.get("order") or "Unknown Order"
        family_name = taxonomy.get("family") or "Unknown Family"

        # Build nested structure
        if class_name not in tree:
            tree[class_name] = {}
        if order_name not in tree[class_name]:
            tree[class_name][order_name] = {}
        if family_name not in tree[class_name][order_name]:
            tree[class_name][order_name][family_name] = []

        # Add species to family
        images = sighting.get("images") or []
        tree[class_name][order_name][family_name].append({
            "common_name": sighting.get("common_name", "Unknown"),
            "scientific_name": sighting.get("scientific_name", ""),
            "sighting_id": sighting.get("id"),
            "image": images[0].get("filename", "") if images else "",
            "notes": sighting.get("notes", ""),
            "sighting_count": sighting.get("sighting_count", 1),
            "gbif_key": taxonomy.get("gbif_key"),
            "genus": taxonomy.get("genus"),
            "taxonomy": taxonomy,
        })

    # Sort species within each family by common name
    for class_name in tree:
        for order_name in tree[class_name]:
            for family_name in tree[class_name][order_name]:
                tree[class_name][order_name][family_name].sort(
                    key=lambda x: x["common_name"].lower()
                )

    return {"tree": tree, "unclassified": unclassified}


def get_species_stats(tree_data: dict) -> dict:
    """Calculate statistics from the tree"""
    tree = tree_data["tree"]
    unclassified = tree_data["unclassified"]

    stats = {
        "total_species": len(unclassified),
        "classes": len(tree),
        "orders": 0,
        "families": 0,
    }

    for class_name, orders in tree.items():
        stats["orders"] += len(orders)
        for order_name, families in orders.items():
            stats["families"] += len(families)
            for family_name, species_list in families.items():
                stats["total_species"] += len(species_list)

    return stats


if __name__ == "__main__":
    # Test run - fetch taxonomy for current sightings
    import json

    sightings_path = PROJECT_ROOT / "data" / "sightings.json"
    if sightings_path.exists():
        with open(sightings_path) as f:
            sightings = json.load(f)

        cache = fetch_all_taxonomy(sightings)
        tree_data = build_species_tree(sightings, cache)
        stats = get_species_stats(tree_data)

        print(f"\nTree Statistics:")
        print(f"  Classes: {stats['classes']}")
        print(f"  Orders: {stats['orders']}")
        print(f"  Families: {stats['families']}")
        print(f"  Species: {stats['total_species']}")
    else:
        print("No sightings.json found")
