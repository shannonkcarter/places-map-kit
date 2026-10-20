# Places Map Kit

Turn a list of places you've been into an interactive map, with optional routes (from GPX files or Strava).
Coffee shops, ice cream, breweries, trailheads, run club meetups: anything with a name and a location.

The example map shows coffee shops a Houston run club has started from, with the routes they ran.
**[See it live](https://shannonkcarter.github.io/places-map-kit/)**

What you get:

- A pin for every place, sized by how many times you've been
- Every route drawn faintly on top of each other, so popular streets glow
- Hover or tap a place to see its notes, visit dates and its own routes highlighted
- Search, a phone-friendly layout and shareable links to a single place (`.../#Blacksmith`)
- A plain static website (no build tools, no accounts, no API keys) hosted free on GitHub Pages

You need Python 3 (no extra packages) and a GitHub account.

## Two ways to use it

**With Claude Code (easiest).** Click **Use this template** above, clone your copy, open the folder in
[Claude Code](https://claude.com/claude-code) and say *"make my map"*. The included skill
(`.claude/skills/places-map/`) walks you through each step below: it turns whatever list you have into
the CSV files, finds the locations, flags anything it isn't sure about, builds the site, previews it and publishes it.

**By hand.** Follow the steps below.

## Step by step

### 1. Make your copy

Click **Use this template → Create a new repository**, then clone it:

```bash
git clone https://github.com/YOUR-NAME/YOUR-REPO.git
cd YOUR-REPO
```

### 2. Set the title and city in `config.json`

```json
{
  "title": "Coffee Shops We've Run To",
  "subtitle": "Houston's coffee shops, one Friday run at a time",
  "emoji": "☕",
  "city": "Houston, TX",
  "place_word": "shop",
  "visit_word": "run",
  "colors": { "pin": "#8a4b24", "route": "#e8590c" },
  "about": "Tap a pin to see when we went and the route we took.",
  "route_trim_m": 150
}
```

- `city` is where the location search looks. Add `"center": [lat, lon]` if your places are outside a single city.
- `place_word` and `visit_word` are used for labels like "14 shops · 30 runs". Try "brewery"/"visit" or "park"/"hike".
- `route_trim_m` cuts this many metres off both ends of *recorded* routes (see [Privacy](#privacy)).

### 3. List your places in `data/places.csv`

Only `name` is required. Replace the example rows with your own:

| column  | required | what it's for |
|---------|----------|---------------|
| name    | yes      | Shown on the map. Must match `place` in visits.csv exactly. |
| address | no       | Makes location lookup much more accurate. |
| notes   | no       | Shown on the place's card, and searchable. |
| link    | no       | Website; the place name becomes a link. |
| lat, lon| no       | Filled in by the next step. Type them in yourself to override. |
| route   | no       | Route(s) for this place if you don't track visits (see step 5). |

### 4. Find the locations

```bash
python3 scripts/geocode.py
```

This fills in `lat`/`lon` for every place that doesn't have them yet. It uses the free US Census geocoder for
addresses and OpenStreetMap (via [Photon](https://photon.komoot.io)) for names. No sign-up needed.

It marks anything it isn't sure of with `review = check`. Look at those on the map in step 6. To fix a
wrong pin, right-click the right spot in Google Maps to copy its coordinates and paste them into `lat`/`lon`.
Rows that already have coordinates are never changed, so your fixes stick.

### 5. Optional: visits and routes

`data/visits.csv` has one row per visit. Delete it if you only want pins.

| column | what it's for |
|--------|---------------|
| place  | Must match a `name` in places.csv. The build tells you about typos. |
| date   | `2024-03-08` or `3/8/2024` |
| notes  | Optional, shown next to the date. |
| route  | A GPX file name in `data/routes/`, a Strava link, or any other link. Separate several with `;`. |

**GPX files** can be exported from Strava, Garmin Connect, RideWithGPS, AllTrails, Komoot and most other
apps. Put them in `data/routes/` and put the file name in the `route` column.

**Strava links** work for routes and activities *you* own. One-time setup, then run the downloader:

1. Create an API app at <https://www.strava.com/settings/api>. Any name works; set *Authorization Callback Domain* to `localhost`.
2. Save the Client ID and Client Secret in `strava_credentials.json` at the repo root:
   `{"client_id": "12345", "client_secret": "..."}`. This file is git-ignored.
3. Run `python3 scripts/fetch_strava.py`. The first run opens your browser to approve access.

Strava won't share other people's routes with your app, so ask friends for a GPX export instead.

If a place has no coordinates but has a loop route (one that ends where it started), the build puts the pin at
the route's start.

### 6. Build and preview

```bash
python3 scripts/build.py
python3 -m http.server 8000 -d docs
```

Open <http://localhost:8000>. Rerun `build.py` and reload whenever you change the data.

### 7. Publish

```bash
git add -A && git commit -m "My map" && git push
```

On GitHub, go to **Settings → Pages**, set *Source* to **Deploy from a branch**, then pick **main** and
**/docs** and save. Your map appears at `https://YOUR-NAME.github.io/YOUR-REPO/` within a minute or two.

## Privacy

Your repo is public, so think about what goes on the map:

- **Recorded runs and rides start at your door.** For any GPX file with timestamps, and any Strava
  *activity*, the build cuts `route_trim_m` metres (default 150) off both ends. Planned routes are left whole.
  Raise the number if your home is close to a route.
- **Raw GPX files stay on your computer.** `data/routes/` is git-ignored (except the `example-*.gpx` files),
  and only the trimmed, simplified lines in `docs/data.json` are published.
- `strava_credentials.json` and `.strava_token.json` are git-ignored too. Never commit them.

## Customizing further

Everything is plain HTML, CSS and JavaScript in `docs/`. Colors live at the top of `docs/style.css`.
The map uses [Leaflet](https://leafletjs.com) with Esri's light gray basemap; swap the tile URLs in
`docs/app.js` for a different look.

## What's in here

```
config.json             title, city, colors, labels
data/places.csv         one row per place
data/visits.csv         one row per visit (optional)
data/routes/            GPX files (git-ignored apart from the examples)
scripts/geocode.py      fills in lat/lon
scripts/fetch_strava.py downloads Strava routes (optional)
scripts/build.py        combines everything into docs/data.json
docs/                   the website GitHub Pages serves
.claude/skills/         the Claude Code skill
```

Made by [January Advisors](https://www.januaryadvisors.com). MIT licensed.
