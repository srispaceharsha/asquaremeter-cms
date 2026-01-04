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

```markdown
---
title: "Week 3: The Spider's Web"
date: 2025-01-15
cover_image: 20250115-001-a.jpg
sightings: ["20250115-001", "20250114-002", "20250113-001"]
---

This week brought unexpected visitors to the square meter...

The garden spider has built an impressive web spanning nearly
the entire plot. Each morning, dew drops cling to the silk threads,
creating a beautiful pattern.

[Your narrative continues...]
```

### Step 3: Rebuild the Site

```bash
uv run python build.py
```

The post will appear in the Posts section and RSS feed.

---

## Quick Logging Common Species

For species you see frequently (like carpenter ants), you can quickly log sightings without adding photos. This keeps a count for your records without cluttering your site with repetitive images.

### Quick Log a Sighting

```bash
# Interactive mode (will prompt for species name)
uv run python pipeline.py log

# With species name directly
uv run python pipeline.py log "Carpenter Ant"
```

You'll be asked:
```
Species name: Carpenter Ant
Time of day [morning/afternoon/evening/night]: morning
Note (optional): 3 spotted near the grass edge

✓ Logged: Carpenter Ant (morning)
  Total observations of this species: 5
```

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

# Quick log a common species (no photo)
uv run python pipeline.py log
uv run python pipeline.py log "Carpenter Ant"

# List sightings
uv run python pipeline.py list

# Edit sighting
uv run python pipeline.py edit 20250115-001

# Delete sighting
uv run python pipeline.py delete 20250115-001

# View stats
uv run python pipeline.py stats

# Build site
uv run python build.py

# Build and preview
uv run python build.py --serve
```
