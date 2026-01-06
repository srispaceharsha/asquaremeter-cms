#!/usr/bin/env python3
"""
build.py - Static site generator for One Square Meter

Commands:
    python build.py           Full build
    python build.py --serve   Build and serve locally
    python build.py --output  Build to custom directory
"""

import argparse
import http.server
import json
import os
import shutil
import socketserver
from datetime import datetime
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader

from taxonomy import fetch_all_taxonomy, build_species_tree, get_species_stats

# Project paths
PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
SIGHTINGS_PATH = PROJECT_ROOT / "data" / "sightings.json"
OBSERVATIONS_PATH = PROJECT_ROOT / "data" / "observations.json"
POSTS_PATH = PROJECT_ROOT / "posts"
TEMPLATES_PATH = PROJECT_ROOT / "templates"
STATIC_PATH = PROJECT_ROOT / "static"
CATALOG_PATH = PROJECT_ROOT / "catalog"
DEFAULT_OUTPUT = PROJECT_ROOT / "site"


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


def load_observations() -> list:
    """Load all quick observations from observations.json"""
    if not OBSERVATIONS_PATH.exists():
        return []
    with open(OBSERVATIONS_PATH) as f:
        return json.load(f)


def load_posts() -> list:
    """Load all markdown posts with frontmatter"""
    posts = []
    if not POSTS_PATH.exists():
        return posts

    for md_file in sorted(POSTS_PATH.glob("*.md"), reverse=True):
        with open(md_file) as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = {}
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        # Handle list values
                        if value.startswith("[") and value.endswith("]"):
                            value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
                        frontmatter[key] = value
                body = parts[2].strip()
            else:
                frontmatter = {}
                body = content
        else:
            frontmatter = {}
            body = content

        # Convert markdown to HTML
        html_content = markdown.markdown(body, extensions=["tables", "fenced_code"])

        posts.append({
            "slug": md_file.stem,
            "filename": md_file.name,
            "title": frontmatter.get("title", md_file.stem),
            "date": frontmatter.get("date", md_file.stem),
            "cover_image": frontmatter.get("cover_image", ""),
            "sightings": frontmatter.get("sightings", []),
            "content": html_content,
        })

    return posts


def format_date(date_str: str) -> str:
    """Format ISO date string to readable format"""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def format_short_date(date_str: str) -> str:
    """Format ISO date string to short format"""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def compute_stats(sightings: list, observations: list, config: dict) -> dict:
    """Compute all statistics from sightings and observations data"""
    from collections import Counter, OrderedDict

    stats = {}

    now = datetime.now()

    # Project start date: use first sighting date, or today if no sightings
    if sightings:
        first_sighting_date = min(
            datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            for s in sightings
        )
        project_start = datetime(first_sighting_date.year, first_sighting_date.month, first_sighting_date.day)
    else:
        project_start = now

    # Basic counts
    stats["total_sightings"] = len(sightings)
    stats["total_observations"] = len(observations)
    stats["generated_at"] = now.strftime("%B %d, %Y")

    # Unique species (by common_name, case-insensitive) - from both sightings and observations
    species_names = [s["common_name"].lower() for s in sightings]
    observation_species = [o["common_name"].lower() for o in observations]
    all_species = set(species_names) | set(observation_species)
    stats["unique_species"] = len(all_species)

    # Days elapsed since project start
    stats["days_elapsed"] = max(1, (now - project_start).days + 1)

    # Days with sightings
    sighting_dates = set()
    for s in sightings:
        try:
            dt = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            sighting_dates.add(dt.date())
        except:
            pass
    stats["days_with_sightings"] = len(sighting_dates)
    stats["days_documented"] = len(sighting_dates)
    stats["days_without_sightings"] = stats["days_elapsed"] - len(sighting_dates)
    stats["coverage_percent"] = round(len(sighting_dates) / stats["days_elapsed"] * 100)

    # By category
    by_category = Counter(s["category"] for s in sightings)
    stats["by_category"] = dict(sorted(by_category.items(), key=lambda x: -x[1]))
    stats["max_category"] = max(by_category.values()) if by_category else 1

    # By season
    by_season = Counter(s.get("season", "unknown") for s in sightings)
    # Order seasons logically
    season_order = ["winter", "summer", "monsoon", "post-monsoon"]
    stats["by_season"] = OrderedDict()
    for season in season_order:
        stats["by_season"][season] = by_season.get(season, 0)
    stats["max_season"] = max(by_season.values()) if by_season else 1

    # By month
    month_counts = Counter()
    for s in sightings:
        try:
            dt = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            month_key = dt.strftime("%b %Y")
            month_counts[month_key] += 1
        except:
            pass
    # Sort by date
    def month_sort_key(m):
        try:
            return datetime.strptime(m, "%b %Y")
        except:
            return datetime.min
    sorted_months = sorted(month_counts.keys(), key=month_sort_key)
    stats["by_month"] = OrderedDict((m, month_counts[m]) for m in sorted_months)
    stats["max_month"] = max(month_counts.values()) if month_counts else 1

    # New vs repeat this month (sightings + observations)
    current_month = now.strftime("%Y-%m")
    species_before_this_month = set()
    species_this_month = set()
    total_this_month = 0

    for s in sorted(sightings, key=lambda x: x["captured_at"]):
        try:
            dt = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            name = s["common_name"].lower()
            if dt.strftime("%Y-%m") == current_month:
                species_this_month.add(name)
                total_this_month += 1
            else:
                species_before_this_month.add(name)
        except:
            pass

    for o in observations:
        try:
            dt = datetime.strptime(o["date"], "%Y-%m-%d")
            name = o["common_name"].lower()
            if dt.strftime("%Y-%m") == current_month:
                species_this_month.add(name)
                total_this_month += 1
            else:
                species_before_this_month.add(name)
        except:
            pass

    new_this_month = species_this_month - species_before_this_month
    stats["new_species_this_month"] = len(new_this_month)
    stats["repeat_sightings_this_month"] = total_this_month - len(new_this_month)

    # Discovery curve (cumulative unique species by month)
    seen_species = set()
    discovery_curve = OrderedDict()
    for s in sorted(sightings, key=lambda x: x["captured_at"]):
        try:
            dt = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            month_key = dt.strftime("%b %Y")
            name = s["common_name"].lower()
            seen_species.add(name)
            discovery_curve[month_key] = len(seen_species)
        except:
            pass
    stats["discovery_curve"] = discovery_curve
    stats["max_discovery"] = max(discovery_curve.values()) if discovery_curve else 1

    # By weather condition
    by_weather = Counter()
    for s in sightings:
        weather = s.get("weather", {})
        condition = weather.get("conditions", "Unknown")
        if condition:
            by_weather[condition] += 1
    stats["by_weather"] = dict(sorted(by_weather.items(), key=lambda x: -x[1]))
    stats["max_weather"] = max(by_weather.values()) if by_weather else 1

    # By moon phase
    by_moon = Counter()
    for s in sightings:
        celestial = s.get("celestial", {})
        phase = celestial.get("moon_phase", "Unknown")
        if phase:
            by_moon[phase] += 1
    stats["by_moon_phase"] = dict(sorted(by_moon.items(), key=lambda x: -x[1]))
    stats["max_moon"] = max(by_moon.values()) if by_moon else 1

    # Top species (most frequently seen) - combine sightings + observations
    species_counts = Counter(s["common_name"] for s in sightings)
    for o in observations:
        species_counts[o["common_name"]] += 1
    stats["top_species"] = species_counts.most_common(5)

    # Single-sighting species (rare finds) - species seen only once total
    stats["single_sighting_species"] = [
        name for name, count in species_counts.items() if count == 1
    ]

    # First sighting by category
    first_by_category = {}
    for s in sorted(sightings, key=lambda x: x["captured_at"]):
        cat = s["category"]
        if cat not in first_by_category:
            try:
                dt = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
                first_by_category[cat] = {
                    "id": s["id"],
                    "name": s["common_name"],
                    "date": dt.strftime("%b %d, %Y"),
                }
            except:
                pass
    stats["first_by_category"] = first_by_category

    return stats


def build_site(output_path: Path):
    """Build the complete static site"""
    config = load_config()
    sightings = load_sightings()
    observations = load_observations()
    posts = load_posts()

    # Sort sightings by date descending
    sightings = sorted(sightings, key=lambda s: s["captured_at"], reverse=True)

    # Create sightings lookup by ID
    sightings_by_id = {s["id"]: s for s in sightings}

    # Setup Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATES_PATH))
    env.filters["date"] = format_date
    env.filters["short_date"] = format_short_date

    # Clean and create output directories
    if output_path.exists():
        for item in output_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "posts").mkdir(exist_ok=True)
    (output_path / "sightings").mkdir(exist_ok=True)
    (output_path / "css").mkdir(exist_ok=True)
    (output_path / "images").mkdir(exist_ok=True)
    (output_path / "images" / "thumb").mkdir(exist_ok=True)
    (output_path / "images" / "web").mkdir(exist_ok=True)
    (output_path / "images" / "full").mkdir(exist_ok=True)
    (output_path / "data").mkdir(exist_ok=True)

    # Copy static assets
    if (STATIC_PATH / "css").exists():
        for css_file in (STATIC_PATH / "css").glob("*"):
            shutil.copy(css_file, output_path / "css" / css_file.name)

    if (STATIC_PATH / "images").exists():
        for img_file in (STATIC_PATH / "images").glob("*"):
            if img_file.is_file():
                shutil.copy(img_file, output_path / "images" / img_file.name)

    # Copy CNAME if exists (for GitHub Pages custom domain)
    if (STATIC_PATH / "CNAME").exists():
        shutil.copy(STATIC_PATH / "CNAME", output_path / "CNAME")

    # Copy favicon if exists
    if (STATIC_PATH / "favicon.ico").exists():
        shutil.copy(STATIC_PATH / "favicon.ico", output_path / "favicon.ico")

    # Copy catalog images
    for size in ["thumb", "web", "full"]:
        src_dir = CATALOG_PATH / size
        if src_dir.exists():
            for img_file in src_dir.glob("*"):
                shutil.copy(img_file, output_path / "images" / size / img_file.name)

    # Common template context
    base_context = {
        "config": config,
        "sightings": sightings,
        "posts": posts,
        "base_url": "",
        "now": datetime.now().isoformat(),
    }

    # Generate index.html
    template = env.get_template("index.html")

    # Get featured sightings from config
    featured_ids = config.get("featured_sightings", [])
    featured_sightings = [sightings_by_id[sid] for sid in featured_ids if sid in sightings_by_id]

    html = template.render(
        **base_context,
        featured_sightings=featured_sightings,
        latest_sightings=sightings[:6],
    )
    (output_path / "index.html").write_text(html)

    # Generate about.html
    template = env.get_template("about.html")
    html = template.render(**base_context)
    (output_path / "about.html").write_text(html)

    # Generate browse.html
    template = env.get_template("browse.html")
    html = template.render(**base_context)
    (output_path / "browse.html").write_text(html)

    # Generate posts/index.html
    template = env.get_template("posts_index.html")
    html = template.render(**base_context)
    (output_path / "posts" / "index.html").write_text(html)

    # Generate individual post pages
    template = env.get_template("post.html")

    # Sort posts by date for determining date ranges
    sorted_posts = sorted(posts, key=lambda p: p["date"])

    for idx, post in enumerate(posts):
        # Determine cover_image_url based on path
        cover_image = post.get("cover_image", "")
        if cover_image:
            if cover_image.startswith("static/"):
                # Image from static/images folder - strip "static/images/" prefix
                post["cover_image_url"] = "/images/" + cover_image[14:]
            else:
                # Sighting image from catalog
                post["cover_image_url"] = "/images/web/" + cover_image
        else:
            post["cover_image_url"] = ""

        # Auto-populate sightings based on date range if not specified
        linked_sightings = []
        if post.get("sightings") and isinstance(post["sightings"], list) and len(post["sightings"]) > 0:
            # Use explicitly specified sightings
            for sid in post["sightings"]:
                if sid in sightings_by_id:
                    linked_sightings.append(sightings_by_id[sid])
        else:
            # Auto-populate: find sightings between previous post date and this post date
            post_date = post["date"]
            # Find previous post date
            post_idx_sorted = next((i for i, p in enumerate(sorted_posts) if p["slug"] == post["slug"]), 0)
            if post_idx_sorted > 0:
                prev_post_date = sorted_posts[post_idx_sorted - 1]["date"]
            else:
                prev_post_date = "1900-01-01"  # Include all sightings before first post

            # Get sightings in date range (after prev_post_date, up to and including post_date)
            for s in sightings:
                sighting_date = s["captured_at"][:10]
                if prev_post_date < sighting_date <= post_date:
                    linked_sightings.append(s)

            # Sort by date
            linked_sightings = sorted(linked_sightings, key=lambda s: s["captured_at"])

        html = template.render(
            **base_context,
            post=post,
            linked_sightings=linked_sightings,
        )
        (output_path / "posts" / f"{post['slug']}.html").write_text(html)

    # Generate individual sighting pages
    template = env.get_template("sighting.html")
    for idx, sighting in enumerate(sightings):
        # Prev/next navigation (sightings sorted newest first)
        prev_sighting = sightings[idx - 1] if idx > 0 else None
        next_sighting = sightings[idx + 1] if idx < len(sightings) - 1 else None
        html = template.render(
            **base_context,
            sighting=sighting,
            prev_sighting=prev_sighting,
            next_sighting=next_sighting,
        )
        (output_path / "sightings" / f"{sighting['id']}.html").write_text(html)

    # Generate public sightings JSON for client-side filtering
    public_sightings = [
        {
            "id": s["id"],
            "common_name": s["common_name"],
            "scientific_name": s["scientific_name"],
            "category": s["category"],
            "season": s["season"],
            "captured_at": s["captured_at"],
            "image": s["images"][0]["filename"] if s["images"] else "",
        }
        for s in sightings
    ]
    with open(output_path / "data" / "sightings.json", "w") as f:
        json.dump(public_sightings, f)

    # Generate stats page
    stats = compute_stats(sightings, observations, config)
    template = env.get_template("stats.html")
    html = template.render(
        **base_context,
        stats=stats,
    )
    (output_path / "stats.html").write_text(html)

    # Generate species tree page
    print("Fetching taxonomy data...")
    taxonomy_cache = fetch_all_taxonomy(sightings)
    tree_data = build_species_tree(sightings, taxonomy_cache)
    tree_stats = get_species_stats(tree_data)

    template = env.get_template("tree.html")
    html = template.render(
        **base_context,
        tree=tree_data["tree"],
        unclassified=tree_data["unclassified"],
        tree_stats=tree_stats,
    )
    (output_path / "tree.html").write_text(html)

    # Generate RSS feed
    generate_rss(output_path, config, sightings, posts)

    # Print summary
    print(f"\nBuilt site:")
    print(f"  - 1 index page")
    print(f"  - 1 about page")
    print(f"  - 1 browse page ({len(sightings)} sightings)")
    print(f"  - 1 tree page ({tree_stats['total_species']} species)")
    print(f"  - 1 stats page")
    print(f"  - {len(posts)} post pages")
    print(f"  - {len(sightings)} sighting pages")
    print(f"  - 1 RSS feed")
    print(f"\nOutput: {output_path}/")


def generate_rss(output_path: Path, config: dict, sightings: list, posts: list):
    """Generate RSS feed for sightings and posts"""
    site_url = config.get("site_url", "")

    # Combine sightings and posts into feed items
    items = []

    # Add sightings
    for s in sightings[:20]:  # Latest 20 sightings
        image_url = ""
        if s["images"]:
            image_url = f"{site_url}/images/web/{s['images'][0]['filename']}"

        items.append({
            "title": f"Sighting: {s['common_name']}",
            "link": f"{site_url}/sightings/{s['id']}.html",
            "description": build_sighting_description(s, image_url),
            "pub_date": format_rss_date(s["captured_at"]),
            "guid": f"{site_url}/sightings/{s['id']}.html",
            "sort_date": s["captured_at"],
        })

    # Add posts
    for p in posts[:20]:  # Latest 20 posts
        cover_url = ""
        if p["cover_image"]:
            cover_url = f"{site_url}/images/web/{p['cover_image']}"

        items.append({
            "title": p["title"],
            "link": f"{site_url}/posts/{p['slug']}.html",
            "description": build_post_description(p, cover_url),
            "pub_date": format_rss_date(p["date"]),
            "guid": f"{site_url}/posts/{p['slug']}.html",
            "sort_date": p["date"],
        })

    # Sort by date descending
    items.sort(key=lambda x: x["sort_date"], reverse=True)
    items = items[:30]  # Keep top 30

    # Build RSS XML
    rss_items = ""
    for item in items:
        rss_items += f"""
    <item>
      <title>{escape_xml(item['title'])}</title>
      <link>{item['link']}</link>
      <description><![CDATA[{item['description']}]]></description>
      <pubDate>{item['pub_date']}</pubDate>
      <guid>{item['guid']}</guid>
    </item>"""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape_xml(config['site_title'])}</title>
    <link>{site_url}</link>
    <description>{escape_xml(config['site_description'])}</description>
    <language>en</language>
    <lastBuildDate>{format_rss_date(datetime.now().isoformat())}</lastBuildDate>
    <atom:link href="{site_url}/feed.xml" rel="self" type="application/rss+xml"/>
{rss_items}
  </channel>
</rss>
"""

    (output_path / "feed.xml").write_text(rss)


def build_sighting_description(sighting: dict, image_url: str) -> str:
    """Build HTML description for sighting RSS item"""
    desc = ""
    if image_url:
        desc += f'<p><img src="{image_url}" alt="{escape_xml(sighting["common_name"])}" style="max-width:100%;"></p>'

    sci_name = f" (<em>{sighting['scientific_name']}</em>)" if sighting["scientific_name"] else ""
    desc += f"<p><strong>{escape_xml(sighting['common_name'])}</strong>{sci_name}</p>"
    desc += f"<p>Category: {sighting['category'].title()} | Season: {sighting['season'].title()}</p>"

    if sighting["notes"]:
        desc += f"<p>{escape_xml(sighting['notes'])}</p>"

    weather = sighting.get("weather", {})
    if weather.get("temp_max_c"):
        desc += f"<p>Weather: {weather['temp_max_c']}°C, {weather['conditions']}</p>"

    return desc


def build_post_description(post: dict, cover_url: str) -> str:
    """Build HTML description for post RSS item"""
    desc = ""
    if cover_url:
        desc += f'<p><img src="{cover_url}" alt="{escape_xml(post["title"])}" style="max-width:100%;"></p>'

    # Include full post content
    desc += post["content"]

    return desc


def format_rss_date(date_str: str) -> str:
    """Format date for RSS pubDate"""
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")


def escape_xml(text: str) -> str:
    """Escape special XML characters"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def serve(output_path: Path, port: int = 8000):
    """Serve the site locally"""
    os.chdir(output_path)

    # Custom handler that skips DNS lookup (much faster)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def address_string(self):
            # Skip reverse DNS lookup
            return self.client_address[0]

        def log_message(self, format, *args):
            # Quieter logging
            pass

    # Custom server that ignores broken pipe errors
    class QuietServer(socketserver.TCPServer):
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            # Silently ignore broken pipe errors (browser cancelled request)
            pass

    with QuietServer(("", port), QuietHandler) as httpd:
        print(f"\nServing at http://localhost:{port}")
        print("Press Ctrl+C to stop\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Build static site for One Square Meter")
    parser.add_argument("--serve", "-s", action="store_true", help="Build and serve locally")
    parser.add_argument("--output", "-o", type=str, help="Output directory")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port for local server")

    args = parser.parse_args()

    output_path = Path(args.output) if args.output else DEFAULT_OUTPUT

    build_site(output_path)

    if args.serve:
        serve(output_path, args.port)


if __name__ == "__main__":
    main()
