"""Shared helpers for the places-map-kit scripts. Standard library only."""
import csv, datetime, json, math, os, re, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ROUTES = os.path.join(DATA, "routes")
PLACES_CSV = os.path.join(DATA, "places.csv")
VISITS_CSV = os.path.join(DATA, "visits.csv")
USER_AGENT = "places-map-kit (https://github.com/shannonkcarter/places-map-kit)"


def load_config():
    return json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def get_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return json.load(urllib.request.urlopen(req, timeout=30))


def km(a, b):
    """Great-circle distance between two (lat, lon) points."""
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def parse_gpx(text):
    """Return (points, recorded). Reads track and route points; recorded=True if points carry timestamps."""
    pts = []
    for tag in re.findall(r"<(?:trkpt|rtept)\b[^>]*>", text):
        lat, lon = re.search(r'lat="([-\d.]+)"', tag), re.search(r'lon="([-\d.]+)"', tag)
        if lat and lon:
            pts.append((float(lat.group(1)), float(lon.group(1))))
    return pts, "<time>" in text.split("</metadata>")[-1]


def parse_date(s):
    """Accept 2024-03-08, 3/8/2024 or 3/8/24. Returns ISO date string or '' if unparseable."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def route_values(cell):
    """A route cell may hold several routes separated by ; or whitespace."""
    return [v for v in re.split(r"[;\s]+", cell) if v]
