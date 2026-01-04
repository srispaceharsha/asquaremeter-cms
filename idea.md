# asquaremeter — Project Specification

A CLI-based workflow and static site generator for documenting biodiversity within a 1 square meter plot over one year.

---

## Project Overview

**Goal:** Photograph and document every insect, plant, fungus, and critter found in a fixed 1m × 1m area across all seasons. Publish findings as a static website with weekly narrative posts.

**User:** Sri (solo maintainer, comfortable with Python, CLI, HTML/CSS, no Node.js)

**Tech Stack:**
- Python 3.10+ (CLI pipeline, build script)
- Jinja2 (HTML templating)
- Pillow (image resizing)
- Open-Meteo API (weather, no key required)
- Ephem or manual calculation (moon phase, sunrise/sunset)
- GitHub Pages (hosting)

---

## Folder Structure

```
onesqm/
├── pipeline.py           # CLI tool for processing new sightings
├── build.py              # Static site generator
├── config.json           # Location coords, site metadata
├── data/
│   └── sightings.json    # All sighting entries (append-only)
├── posts/                # Weekly markdown posts with frontmatter
│   └── 2025-01-07.md
├── inbox/                # Drop raw photos here for processing
├── catalog/              # Processed images (3 sizes per image)
│   ├── thumb/            # 150px wide thumbnails
│   ├── web/              # 800px wide web-friendly
│   └── full/             # Original resolution
├── templates/            # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── about.html
│   ├── browse.html
│   ├── sighting.html     # Individual sighting page
│   └── post.html         # Weekly post template
├── static/
│   ├── css/
│   │   └── style.css
│   └── images/           # Site assets (logo, hero, nav cards)
└── site/                 # Generated output (git-ignored, or separate repo)
    ├── index.html
    ├── about.html
    ├── browse.html
    ├── posts/
    ├── sightings/
    ├── css/
    └── images/
```

---

## Configuration

**config.json:**
```json
{
  "site_title": "One Square Meter",
  "site_description": "A year-long biodiversity study of 1m² in rural Tamil Nadu",
  "author": "Sri",
  "location": {
    "latitude": 10.0,
    "longitude": 78.0,
    "timezone": "Asia/Kolkata",
    "place_name": "My Village, Tamil Nadu"
  },
  "season_definitions": {
    "winter": ["12", "01", "02"],
    "summer": ["03", "04", "05"],
    "monsoon": ["06", "07", "08", "09"],
    "post-monsoon": ["10", "11"]
  },
  "categories": ["insect", "arachnid", "plant", "fungus", "mollusk", "other"]
}
```

---

## Data Schema

### Sighting Entry (in sightings.json)

```json
{
  "id": "20250101-001",
  "images": [
    {
      "filename": "20250101-001-a.jpg",
      "caption": "Dorsal view"
    }
  ],
  "common_name": "Garden Spider",
  "scientific_name": "Argiope anasuja",
  "category": "arachnid",
  "captured_at": "2025-01-01T08:30:00+05:30",
  "weather": {
    "temp_max_c": 28,
    "temp_min_c": 19,
    "precipitation_mm": 0,
    "conditions": "Clear sky"
  },
  "celestial": {
    "moon_phase": "Waxing Crescent",
    "moon_illumination": 0.15,
    "sunrise": "06:42",
    "sunset": "18:05"
  },
  "season": "winter",
  "notes": "Found on web between grass blades, approximately 3cm body length",
  "created_at": "2025-01-01T10:00:00+05:30"
}
```

**Notes:**
- `id` format: `YYYYMMDD-NNN` (date + sequence number for that day)
- `images` is an array to support multiple angles of same specimen
- `scientific_name` can be empty string if unknown
- `captured_at` is extracted from EXIF; falls back to user input
- `created_at` is when the entry was added to the system

### Weekly Post (Markdown with frontmatter)

```markdown
---
title: "Week 1: The Beginning"
date: 2025-01-07
cover_image: 20250101-001-a.jpg
sightings: ["20250101-001", "20250102-001", "20250103-001"]
---

The first week of January brought unexpected visitors...

[Narrative content here]
```

---

## Pipeline CLI (pipeline.py)

### Commands

```bash
# Process all images in inbox/
python pipeline.py add

# Process specific file
python pipeline.py add --file inbox/IMG_1234.jpg

# List recent sightings
python pipeline.py list --last 10

# Edit existing sighting (opens in $EDITOR or prompts)
python pipeline.py edit 20250101-001

# Show stats
python pipeline.py stats
```

### `add` Command Flow

1. **Scan inbox/** for `.jpg` and `.png` files (case-insensitive)

2. **For each image:**
   
   a. **Extract EXIF data:**
      - `DateTimeOriginal` → `captured_at`
      - If no EXIF date, prompt user for date/time
   
   b. **Display image filename and capture date**
   
   c. **Prompt for metadata:**
      ```
      Processing: IMG_1234.jpg
      Captured: 2025-01-01 08:30:00
      
      Common name: Garden Spider
      Scientific name (blank if unknown): Argiope anasuja
      Category [insect/arachnid/plant/fungus/mollusk/other]: arachnid
      Notes: Found on web between grass blades
      
      Add another image to this sighting? [y/N]: n
      ```
   
   d. **Fetch weather data** from Open-Meteo API for that date
   
   e. **Calculate celestial data:**
      - Moon phase (use `ephem` library or algorithm)
      - Sunrise/sunset for location and date
   
   f. **Determine season** from month using config
   
   g. **Generate ID:** `YYYYMMDD-NNN`
   
   h. **Process images into 3 sizes:**
      - `thumb/`: 150px wide (maintain aspect ratio)
      - `web/`: 800px wide (maintain aspect ratio)
      - `full/`: original (just copy)
      - Filename: `{id}-{letter}.jpg` (a, b, c for multiple images)
   
   i. **Move original** from `inbox/` to `catalog/full/`
   
   j. **Append entry** to `data/sightings.json`
   
   k. **Print confirmation:**
      ```
      ✓ Added: 20250101-001 - Garden Spider (Argiope anasuja)
        Weather: 28°C max, Clear sky
        Moon: Waxing Crescent (15%)
      ```

3. **After all images processed**, print summary

### Weather Fetching Logic

```python
def fetch_weather(lat: float, lon: float, date: str) -> dict:
    """
    Fetch weather for a specific date.
    
    - If date is within last 7 days: use forecast API
    - If date is older: use archive API
    
    API endpoints:
    - Recent: https://api.open-meteo.com/v1/forecast
    - Archive: https://archive-api.open-meteo.com/v1/archive
    
    Parameters:
    - latitude, longitude
    - start_date, end_date (same date)
    - daily: temperature_2m_max, temperature_2m_min, precipitation_sum, weathercode
    - timezone: from config
    
    Returns dict with: temp_max_c, temp_min_c, precipitation_mm, conditions
    """
```

**Weather code mapping** (WMO codes to human-readable):
```python
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
    99: "Thunderstorm with heavy hail"
}
```

### Moon Phase Calculation

Use `ephem` library or implement algorithm:

```python
def get_moon_phase(date: datetime) -> dict:
    """
    Returns:
    {
        "phase": "Waxing Crescent",  # New, Waxing Crescent, First Quarter, 
                                      # Waxing Gibbous, Full, Waning Gibbous,
                                      # Last Quarter, Waning Crescent
        "illumination": 0.15          # 0.0 to 1.0
    }
    """
```

### Sunrise/Sunset Calculation

Use `ephem` library or `astral` library:

```python
def get_sun_times(lat: float, lon: float, date: datetime, timezone: str) -> dict:
    """
    Returns:
    {
        "sunrise": "06:42",
        "sunset": "18:05"
    }
    """
```

---

## Build Script (build.py)

### Commands

```bash
# Full build
python build.py

# Build and serve locally (for preview)
python build.py --serve

# Build specific section only
python build.py --only index,browse
```

### Build Process

1. **Load data:**
   - Read `config.json`
   - Read `data/sightings.json`
   - Read all posts from `posts/*.md`

2. **Create output directory** (`site/`) if not exists

3. **Copy static assets:**
   - `static/css/` → `site/css/`
   - `static/images/` → `site/images/`
   - `catalog/thumb/` → `site/images/thumb/`
   - `catalog/web/` → `site/images/web/`
   - `catalog/full/` → `site/images/full/`

4. **Generate pages:**

   a. **index.html** (Home)
      - Hero section with project blurb
      - 3 navigation cards (About, Posts, Browse)
      - Latest 4 sightings strip
      - Data: latest 4 sightings, config
   
   b. **about.html**
      - Project description
      - Methodology
      - Location info (no exact coords)
      - Author info
   
   c. **browse.html**
      - All sightings in grid/list view
      - Filter by: category, season, month
      - Sort by: date (default), name
      - Data: all sightings
   
   d. **posts/index.html**
      - List of all weekly posts
      - Data: all posts sorted by date desc
   
   e. **posts/{date}.html** (for each post)
      - Full post content
      - Linked sightings displayed
      - Data: post content, linked sightings
   
   f. **sightings/{id}.html** (for each sighting)
      - Full-size image(s)
      - All metadata displayed nicely
      - Link to full resolution
      - Data: single sighting

5. **Generate browse data** (optional JSON for client-side filtering):
   - `site/data/sightings.json` (public subset of data)

6. **Print summary:**
   ```
   Built site:
   - 1 index page
   - 1 about page
   - 1 browse page (47 sightings)
   - 12 post pages
   - 47 sighting pages
   
   Output: ./site/
   ```

### `--serve` Flag

Use Python's built-in HTTP server:
```python
import http.server
import socketserver

os.chdir('site')
handler = http.server.SimpleHTTPRequestHandler
with socketserver.TCPServer(("", 8000), handler) as httpd:
    print("Serving at http://localhost:8000")
    httpd.serve_forever()
```

---

## HTML Templates (Jinja2)

### base.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}{{ config.site_title }}{% endblock %}</title>
    <link rel="stylesheet" href="{{ base_url }}/css/style.css">
</head>
<body>
    <header>
        <a href="{{ base_url }}/" class="site-title">{{ config.site_title }}</a>
        <nav>
            <a href="{{ base_url }}/about.html">About</a>
            <a href="{{ base_url }}/posts/">Posts</a>
            <a href="{{ base_url }}/browse.html">Browse</a>
        </nav>
    </header>
    
    <main>
        {% block content %}{% endblock %}
    </main>
    
    <footer>
        <p>{{ config.site_title }} by {{ config.author }}</p>
        <p>{{ sightings | length }} sightings documented</p>
    </footer>
</body>
</html>
```

### index.html
```html
{% extends "base.html" %}

{% block content %}
<section class="hero">
    <div class="hero-image">
        <!-- Wide image -->
    </div>
    <p class="hero-blurb">{{ config.site_description }}</p>
</section>

<section class="nav-cards">
    <a href="about.html" class="nav-card">
        <img src="images/about-card.jpg" alt="">
        <span>About</span>
    </a>
    <a href="posts/" class="nav-card">
        <img src="images/posts-card.jpg" alt="">
        <span>Posts</span>
    </a>
    <a href="browse.html" class="nav-card">
        <img src="images/browse-card.jpg" alt="">
        <span>Browse</span>
    </a>
</section>

<section class="latest">
    <h2>Latest Sightings</h2>
    <div class="latest-strip">
        {% for sighting in latest_sightings %}
        <a href="sightings/{{ sighting.id }}.html" class="latest-item">
            <img src="images/thumb/{{ sighting.images[0].filename }}" alt="{{ sighting.common_name }}">
        </a>
        {% endfor %}
        <a href="browse.html" class="latest-item more">More...</a>
    </div>
</section>
{% endblock %}
```

### browse.html
```html
{% extends "base.html" %}

{% block content %}
<h1>Browse Sightings</h1>

<div class="filters">
    <select id="filter-category">
        <option value="">All Categories</option>
        {% for cat in config.categories %}
        <option value="{{ cat }}">{{ cat | title }}</option>
        {% endfor %}
    </select>
    
    <select id="filter-season">
        <option value="">All Seasons</option>
        <option value="winter">Winter</option>
        <option value="summer">Summer</option>
        <option value="monsoon">Monsoon</option>
        <option value="post-monsoon">Post-monsoon</option>
    </select>
</div>

<div class="sightings-grid" id="sightings-grid">
    {% for sighting in sightings %}
    <a href="sightings/{{ sighting.id }}.html" 
       class="sighting-card"
       data-category="{{ sighting.category }}"
       data-season="{{ sighting.season }}">
        <img src="images/thumb/{{ sighting.images[0].filename }}" alt="">
        <div class="sighting-info">
            <span class="common-name">{{ sighting.common_name }}</span>
            <span class="date">{{ sighting.captured_at | date }}</span>
        </div>
    </a>
    {% endfor %}
</div>

<script>
// Simple client-side filtering
document.querySelectorAll('.filters select').forEach(select => {
    select.addEventListener('change', filterSightings);
});

function filterSightings() {
    const category = document.getElementById('filter-category').value;
    const season = document.getElementById('filter-season').value;
    
    document.querySelectorAll('.sighting-card').forEach(card => {
        const matchCategory = !category || card.dataset.category === category;
        const matchSeason = !season || card.dataset.season === season;
        card.style.display = (matchCategory && matchSeason) ? '' : 'none';
    });
}
</script>
{% endblock %}
```

---

## CSS Guidelines (style.css)

- Mobile-first responsive design
- Max content width: 1200px
- Thumbnail grid: 4 columns desktop, 2 columns mobile
- Cards with subtle shadows, rounded corners (8px)
- Color palette: earthy/natural tones (greens, browns, cream)
- Typography: system fonts, good readability
- Image aspect ratios maintained throughout
- Print stylesheet for sighting pages (optional)

---

## Image Processing Details

Using Pillow (PIL):

```python
from PIL import Image

def process_image(input_path: str, output_id: str, letter: str):
    """
    Creates three versions of the image:
    - thumb: 150px wide
    - web: 800px wide  
    - full: original size (just copy/convert)
    
    Maintains aspect ratio.
    Converts PNG to JPG for web/thumb (smaller files).
    Strips EXIF from web/thumb versions.
    Preserves EXIF in full version.
    """
    
    img = Image.open(input_path)
    filename = f"{output_id}-{letter}.jpg"
    
    # Thumbnail (150px wide)
    thumb = img.copy()
    thumb.thumbnail((150, 10000), Image.LANCZOS)
    thumb.save(f"catalog/thumb/{filename}", "JPEG", quality=80)
    
    # Web (800px wide)
    web = img.copy()
    web.thumbnail((800, 10000), Image.LANCZOS)
    web.save(f"catalog/web/{filename}", "JPEG", quality=85)
    
    # Full (original, but ensure JPG)
    if img.format == 'PNG':
        img = img.convert('RGB')
    img.save(f"catalog/full/{filename}", "JPEG", quality=95)
```

---

## Dependencies

**requirements.txt:**
```
Pillow>=10.0.0
Jinja2>=3.1.0
requests>=2.31.0
ephem>=4.1.0
python-dateutil>=2.8.0
markdown>=3.5.0
```

---

## Implementation Phases

### Phase 1: Core Pipeline
1. Set up folder structure
2. Implement `config.json` loading
3. Implement EXIF date extraction
4. Implement weather fetching (Open-Meteo)
5. Implement moon phase + sunrise/sunset
6. Implement image resizing
7. Implement `pipeline.py add` command
8. Test with sample images

### Phase 2: Build Script
1. Implement Jinja2 template loading
2. Create base template
3. Implement index page generation
4. Implement browse page generation
5. Implement sighting pages generation
6. Implement static file copying
7. Implement `--serve` flag

### Phase 3: Posts & Polish
1. Implement markdown post parsing
2. Implement post page generation
3. Create about page template
4. Write CSS stylesheet
5. Test responsive design
6. Add stats command to pipeline

### Phase 4: Deployment
1. Set up GitHub Pages repository
2. Add deployment instructions to README
3. Create sample data for testing
4. Write user documentation

---

## CLI Reference (Final)

```bash
# Add new sightings from inbox
python pipeline.py add

# Add specific file
python pipeline.py add --file path/to/image.jpg

# List recent entries
python pipeline.py list
python pipeline.py list --last 20
python pipeline.py list --category insect
python pipeline.py list --season monsoon

# Edit existing entry (interactive)
python pipeline.py edit 20250101-001

# Show project statistics
python pipeline.py stats

# Build static site
python build.py

# Build and preview locally
python build.py --serve

# Build to custom output directory
python build.py --output /path/to/output
```

---

## Notes for Implementation

1. **Error handling:** Graceful failures with clear messages. Don't lose data if API calls fail—prompt for manual entry instead.

2. **Idempotency:** Running `build.py` multiple times should produce identical output.

3. **Incremental:** Future enhancement could make builds incremental, but full rebuilds are fine for <500 sightings.

4. **Backup:** `sightings.json` is the source of truth. Should be committed to git.

5. **No JavaScript frameworks:** Keep it simple. Vanilla JS only for filtering.

6. **Accessibility:** Alt text on images, semantic HTML, keyboard navigation.

---

## Open Questions / Future Enhancements

- [ ] RSS feed for posts?
- [ ] Search functionality (client-side)?
- [ ] Map view (single point, just for context)?
- [ ] Integration with iNaturalist API for ID suggestions?
- [ ] Bulk import from existing photos with date range?
- [ ] Export to CSV for personal records?
