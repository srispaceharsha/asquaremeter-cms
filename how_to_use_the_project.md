# How to Use One Square Meter

A step-by-step guide to documenting biodiversity with this project.

---

## Initial Setup

### 1. Install Dependencies

```bash
cd /path/to/asquaremeter
uv sync
```

This installs all required Python packages in a virtual environment.

### 2. Configure Your Site

Edit `config.json` with your details:

```json
{
  "site_title": "One Square Meter",
  "site_description": "Your project description",
  "site_url": "https://yourusername.github.io/onesqm",
  "author": "Your Name",
  "location": {
    "latitude": 10.0,
    "longitude": 78.0,
    "timezone": "Asia/Kolkata",
    "place_name": "Your Location"
  }
}
```

**Important:** Set `site_url` to your actual GitHub Pages URL for RSS feed links to work correctly.

---

## Daily Workflow: Adding Sightings

### Step 1: Drop Photos into Inbox

Copy your photos into the `inbox/` folder:

```
inbox/
├── IMG_1234.jpg
├── spider_photo.png
└── beetle.jpg
```

### Step 2: Run the Pipeline

```bash
uv run python pipeline.py add
```

### Step 3: Answer the Prompts

For each image, you'll be asked:

```
Processing: IMG_1234.jpg (1 of 3)
Captured: 2025-01-15 08:30:00

Common name: Garden Spider
Scientific name (blank if unknown): Argiope anasuja
Category [insect/arachnid/plant/fungus/mollusk/other]: arachnid
Notes: Found on web between grass blades

Add another image to this sighting? [y/N]: n
```

### Step 4: Done!

The pipeline automatically:
- Extracts the date from photo EXIF data
- Fetches weather data from Open-Meteo API
- Calculates moon phase and sunrise/sunset
- Resizes images to 3 sizes (thumbnail, web, full)
- Saves entry to `data/sightings.json`
- Moves processed images to `catalog/`

```
✓ Added: 20250115-001 - Garden Spider (Argiope anasuja)
  Weather: 28°C max, Clear sky
  Moon: Waxing Crescent (15%)
```

---

## Building the Website

### Build the Site

```bash
uv run python build.py
```

Output goes to `site/` folder.

### Preview Locally

```bash
uv run python build.py --serve
```

Then open http://localhost:8000 in your browser.

### Build to Custom Directory

```bash
uv run python build.py --output /path/to/output
```

---

## Writing Weekly Posts

### Step 1: Create a Markdown File

Create a file in `posts/` with the date as filename:

```
posts/2025-01-15.md
```

### Step 2: Add Frontmatter and Content

**Minimal template (recommended):**

```markdown
---
title: "Week 1: Title Here"
date: 2025-01-15
cover_image: static/images/week1-cover.jpg
---

Your post content here...
```

**With all options:**

```markdown
---
title: "Week 1: Title Here"
date: 2025-01-15
cover_image: static/images/week1-cover.jpg
sightings: ["20250115-001", "20250114-002"]
---

Your post content here...
```

### Cover Image Options

You can use either:
- **Custom image**: `cover_image: static/images/my-photo.jpg` - Put your image in `static/images/` folder
- **Sighting image**: `cover_image: 20250115-001-a.jpg` - Use a processed sighting image from catalog

### Auto-Populated Sightings

If you omit the `sightings` field (or leave it empty), the build will **automatically include all sightings** between the previous post's date and the current post's date.

Example: If your first post is dated `2025-01-07`, it will include all sightings from the start of the project up to Jan 7. Your next post dated `2025-01-14` will automatically include sightings from Jan 8-14.

To manually specify sightings instead, add:
```yaml
sightings: ["20250115-001", "20250114-002", "20250113-001"]
```

### Step 3: Rebuild the Site

```bash
uv run python build.py
```

The post will appear in the Posts section and RSS feed.

---

## Quick Logging Common Species

For species you see frequently (like carpenter ants), you can quickly log sightings without adding photos. This keeps a count for your records without cluttering your site with repetitive images.

### Option 1: Web UI (Recommended)

```bash
uv run python pipeline.py logweb
```

Opens a local web page at http://localhost:8001 where you can:
- See all species with thumbnails
- Filter by category or search by name
- Check multiple species at once
- Submit with one click

Species already logged today are grayed out to avoid duplicates.

### Option 2: Command Line

```bash
# Interactive mode (shows known species, prompts for input)
uv run python pipeline.py log

# Single species
uv run python pipeline.py log "Carpenter Ant"

# Multiple species at once (comma-separated)
uv run python pipeline.py log "Carpenter Ant, Tropical Fire Ant, Wolf Spider"
```

Example session:
```
Known species:
  Carpenter Ant
  Tropical Fire Ant
  Wolf Spider
  ...

Species (comma-separated): carpenter ant, tropical fire ant
Time of day [morning/afternoon/evening/night]: morning

✓ Carpenter Ant (total: 5)
✓ Tropical Fire Ant (total: 3)

Logged 2 observation(s)
```

### Auto-Correction & Validation

Names are automatically validated and normalized:

**Common names:**
- Converted to Title Case: `carpenter ant` → `Carpenter Ant`
- Matched against existing species to prevent duplicates
- Cannot contain scientific names in parentheses (enter them separately)

**Scientific names:**
- Format: `Genus species` or `Genus sp.` for unknown species
- Genus is capitalized, species is lowercase: `Camponotus parius`
- Must end with `sp.` (with period) for unknown species
- Example error: `Camponotus sp` → "Did you mean 'sp.' with a period?"

Quick logs are saved to `data/observations.json` and included in your statistics (total count and unique species), but they don't create individual pages on the site.

**When to use Quick Log vs Add:**
- **Quick Log**: Common species you see regularly, no remarkable photo
- **Add**: New species, interesting behavior, spectacular photo, or species you want to document on the site

---

## Other Pipeline Commands

### List Recent Sightings

```bash
# List last 10 sightings (default)
uv run python pipeline.py list

# List last 20 sightings
uv run python pipeline.py list --last 20

# Filter by category
uv run python pipeline.py list --category insect

# Filter by season
uv run python pipeline.py list --season monsoon
```

### Edit a Sighting

```bash
uv run python pipeline.py edit 20250115-001
```

You can update: common name, scientific name, category, notes.

### Delete a Sighting

```bash
uv run python pipeline.py delete 20250115-001
```

This will:
- Show you the sighting details
- Ask for confirmation
- Remove the entry from `sightings.json`
- Delete all associated images (thumb, web, full)

Use `--force` or `-f` to skip the confirmation prompt:

```bash
uv run python pipeline.py delete 20250115-001 --force
```

### View Statistics

```bash
uv run python pipeline.py stats
```

Shows:
- Total sightings count
- Unique species count
- Date range
- Breakdown by category
- Breakdown by season

---

## RSS Feed

The RSS feed is automatically generated when you build the site:

```
site/feed.xml
```

It includes:
- Latest 20 sightings (with images)
- Latest 20 posts (with full content)
- Sorted by date, combined into one feed

Subscribers will see new sightings and posts as you add them.

---

## Deploying to GitHub Pages

### Option 1: Publish `site/` folder

1. Create a GitHub repository
2. Push your project (excluding `site/`)
3. Build locally: `uv run python build.py`
4. Push `site/` to a `gh-pages` branch or use GitHub Actions

### Option 2: GitHub Actions (Recommended)

Create `.github/workflows/build.yml`:

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Build site
        run: |
          uv sync
          uv run python build.py

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
```

---

## Folder Structure Reference

```
asquaremeter/
├── pipeline.py           # CLI for adding sightings
├── build.py              # Static site generator
├── config.json           # Site configuration
├── pyproject.toml        # Python dependencies
│
├── data/
│   ├── sightings.json    # All sighting data (source of truth)
│   └── observations.json # Quick log entries (common species)
│
├── posts/                # Weekly markdown posts
│   └── 2025-01-15.md
│
├── inbox/                # Drop raw photos here
│
├── catalog/              # Processed images
│   ├── thumb/            # 300px thumbnails
│   ├── web/              # 1200px web-friendly
│   └── full/             # Original resolution
│
├── templates/            # Jinja2 HTML templates
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── images/           # Site assets (logo, etc.)
│
└── site/                 # Generated output (deployable)
```

---

## Tips

1. **Backup `sightings.json`** - This is your source of truth. Commit it to git.

2. **EXIF dates** - The pipeline reads dates from photo metadata. If your camera doesn't embed dates, you'll be prompted to enter them manually.

3. **Multiple angles** - When prompted "Add another image to this sighting?", say yes to add multiple photos of the same specimen.

4. **Scientific names** - Leave blank if you're not sure. You can always edit later with `pipeline.py edit <id>`.

5. **Weather data** - Works for dates within the last few years. Very old dates may not have weather data available.

6. **Rebuilding** - Always rebuild after adding sightings or posts: `uv run python build.py`

---

## Quick Reference

```bash
# Add new sightings
uv run python pipeline.py add

# Add specific file
uv run python pipeline.py add --file path/to/image.jpg

# Quick log via web UI (recommended)
uv run python pipeline.py logweb

# Quick log via command line
uv run python pipeline.py log
uv run python pipeline.py log "Carpenter Ant"
uv run python pipeline.py log "Carpenter Ant, Wolf Spider, Tropical Fire Ant"

# List sightings
uv run python pipeline.py list

# Edit sighting
uv run python pipeline.py edit 20250115-001

# Delete sighting
uv run python pipeline.py delete 20250115-001

# View stats
uv run python pipeline.py stats

# Backfill weather data for old sightings
uv run python backfill_weather.py

# Build site
uv run python build.py

# Build and preview
uv run python build.py --serve
```

## Post Template

Copy this for new posts:

```markdown
---
title: "Week X: Title Here"
date: 2026-01-07
cover_image: static/images/weekX-cover.jpg
---

Your post content here...
```
