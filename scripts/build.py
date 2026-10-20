"""Bundle config.json, data/places.csv, data/visits.csv and GPX routes into docs/data.json for the map.

Usage: python3 scripts/build.py

Route cells (in visits.csv, or a `route` column in places.csv) can hold:
  - a GPX file name in data/routes/ (e.g. my-loop.gpx)
  - a Strava route/activity link, after running scripts/fetch_strava.py
  - any other link, which just shows up as a "route" link with no line on the map
Recorded activities (GPX with timestamps, or Strava activities) have their first and last
`route_trim_m` metres cut off so nobody's front door ends up on a public map.
"""
import difflib, json, math, os

import kit

TOLERANCE_M = 8  # line simplification: drop points that move the line less than this
STRAVA_INDEX = os.path.join(kit.ROUTES, "strava", "index.json")


def to_xy(p, lat0):
    return (p[1] * 111320 * math.cos(math.radians(lat0)), p[0] * 110540)


def simplify(pts, tol):
    """Ramer-Douglas-Peucker on lat/lon points, tolerance in metres."""
    if len(pts) < 3:
        return pts
    lat0 = pts[0][0]
    xy = [to_xy(p, lat0) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        best, idx = 0, None
        for i in range(a + 1, b):
            # loops start and end at the same spot, so fall back to distance from that point
            d = (abs(dy * (xy[i][0] - ax) - dx * (xy[i][1] - ay)) / norm if norm > 1e-6
                 else math.hypot(xy[i][0] - ax, xy[i][1] - ay))
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def trim(pts, metres):
    def cut(seq):
        lat0, total = seq[0][0], 0
        for i in range(1, len(seq)):
            (x1, y1), (x2, y2) = to_xy(seq[i - 1], lat0), to_xy(seq[i], lat0)
            total += math.hypot(x2 - x1, y2 - y1)
            if total >= metres:
                return seq[i:]
        return seq
    return cut(cut(pts)[::-1])[::-1] if metres else pts


class Routes:
    def __init__(self, trim_m):
        self.trim_m = trim_m
        self.strava = json.load(open(STRAVA_INDEX)) if os.path.exists(STRAVA_INDEX) else {}
        self.warnings = []

    def load(self, value):
        """Return (link, raw points or None) for one route cell value."""
        link = value if value.startswith("http") else ""
        if link:
            hit = self.strava.get(value)
            if not hit:
                if "strava" in value:
                    self.warnings.append(f"Strava link not downloaded yet (run scripts/fetch_strava.py): {value}")
                return link, None
            rel, recorded = hit["file"], hit["kind"] == "activities"
        else:
            rel, recorded = value, None
        path = os.path.join(kit.ROUTES, rel)
        if not os.path.exists(path):
            self.warnings.append(f"Route file not found: data/routes/{rel}")
            return link, None
        pts, has_time = kit.parse_gpx(open(path, encoding="utf-8", errors="ignore").read())
        if len(pts) < 2:
            self.warnings.append(f"No track points in data/routes/{rel}")
            return link, None
        return link, (pts, has_time if recorded is None else recorded)

    def finish(self, pts, recorded):
        if recorded:
            pts = trim(pts, self.trim_m)
        return [[round(a, 5), round(b, 5)] for a, b in simplify(pts, TOLERANCE_M)]


def main():
    cfg = kit.load_config()
    routes = Routes(cfg.get("route_trim_m", 150))
    places, order = {}, []
    for r in kit.read_csv(kit.PLACES_CSV):
        if not r.get("name"):
            continue
        p = places.setdefault(r["name"], {
            "name": r["name"], "address": r.get("address", ""), "notes": r.get("notes", ""),
            "link": r.get("link", ""), "lat": r.get("lat", ""), "lon": r.get("lon", ""),
            "visits": [], "routes": [], "_raw": [],
        })
        order.append(r["name"])
        for v in kit.route_values(r.get("route", "")):
            _, raw = routes.load(v)
            if raw:
                p["_raw"].append(("", raw))

    unknown = {}
    for r in kit.read_csv(kit.VISITS_CSV):
        name = r.get("place", "")
        if name not in places:
            if name:
                unknown[name] = unknown.get(name, 0) + 1
            continue
        p = places[name]
        date = kit.parse_date(r.get("date", ""))
        links = []
        for v in kit.route_values(r.get("route", "")):
            link, raw = routes.load(v)
            if link:
                links.append(link)
            if raw:
                p["_raw"].append((date, raw))
        p["visits"].append({"date": date, "notes": r.get("notes", ""), "links": links})

    out, skipped = [], []
    for name in dict.fromkeys(order):
        p = places[name]
        # a loop route (ends within 300 m of where it started) almost always starts at the place itself
        if not (p["lat"] and p["lon"]):
            loops = [raw[0][0] for _, raw in p["_raw"] if kit.km(raw[0][0], raw[0][-1]) < 0.3]
            if loops:
                p["lat"], p["lon"] = f"{loops[0][0]:.6f}", f"{loops[0][1]:.6f}"
                routes.warnings.append(f"{name}: no lat/lon, so the pin was placed at its loop route's start")
        if not (p["lat"] and p["lon"]):
            skipped.append(name)
            continue
        p["lat"], p["lon"] = round(float(p["lat"]), 6), round(float(p["lon"]), 6)
        p["routes"] = [{"date": d, "coords": routes.finish(*raw)} for d, raw in p.pop("_raw")]
        p["visits"].sort(key=lambda v: v["date"] or "9999")
        out.append(p)

    data = {
        "config": {k: cfg.get(k) for k in ["title", "subtitle", "emoji", "place_word", "visit_word", "colors", "about"]},
        "places": out,
    }
    os.makedirs(os.path.join(kit.ROOT, "docs"), exist_ok=True)
    path = os.path.join(kit.ROOT, "docs", "data.json")
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    n_routes = sum(len(p["routes"]) for p in out)
    n_visits = sum(len(p["visits"]) for p in out)
    print(f"{len(out)} places, {n_visits} visits, {n_routes} routes, {os.path.getsize(path) // 1024} KB -> docs/data.json")
    for w in routes.warnings:
        print("  note:", w)
    if skipped:
        print(f"  skipped {len(skipped)} places with no lat/lon (run scripts/geocode.py):", ", ".join(skipped))
    for name, n in unknown.items():
        close = difflib.get_close_matches(name, list(places), n=1)
        hint = f' (did you mean "{close[0]}"?)' if close else ""
        print(f'  visits.csv has {n} row(s) for "{name}", which isn\'t in places.csv{hint}')


if __name__ == "__main__":
    main()
