"""Fill in lat/lon for places in data/places.csv that don't have them yet.

Usage: python3 scripts/geocode.py

- Places with an address: US Census geocoder first (US only, very accurate), then Photon (OpenStreetMap).
- Places with only a name: Photon search for "<name> <city>" near the city in config.json, keeping the
  closest name match.
Rows that already have lat/lon are never touched, so to fix a bad pin just type the right lat/lon in.
Low-confidence matches get review=check; look at those on the map before publishing.
"""
import difflib, re, time

import kit

PHOTON = "https://photon.komoot.io/api/"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
MAX_KM = 60  # ignore matches farther than this from the city center


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", "and")).strip()


def similarity(name, candidate):
    a, b = norm(name), norm(candidate)
    if not a or not b:
        return 0
    sim = difflib.SequenceMatcher(None, a, b).ratio()
    core = norm(re.sub(r"\(.*?\)| - .*", "", name))  # drop "(downtown)", "- Levy Park"
    if core and re.search(rf"\b{re.escape(core)}\b", b):
        sim = max(sim, 0.9)  # "Blacksmith" -> "Blacksmith Coffee"
    elif core and re.search(rf"\b{re.escape(b)}\b", core):
        sim = max(sim, 0.8)  # "Tiny's No. 5" -> "Tiny's": maybe a sister location, so flag it
    return sim


def photon(q, center=None, limit=8):
    params = {"q": q, "limit": limit, "lang": "en"}
    if center:
        params.update(lat=center[0], lon=center[1])
    time.sleep(1)  # be polite to the free public server
    return kit.get_json(PHOTON, params)["features"]


def describe(p):
    street = " ".join(filter(None, [p.get("housenumber"), p.get("street")]))
    return ", ".join(filter(None, [street, p.get("city"), p.get("postcode")]))


def city_center(cfg):
    if cfg.get("center"):
        return tuple(cfg["center"])
    hits = photon(cfg["city"], limit=1)
    if not hits:
        raise SystemExit(f'Could not find the city "{cfg["city"]}". Add "center": [lat, lon] to config.json.')
    lon, lat = hits[0]["geometry"]["coordinates"]
    return lat, lon


def by_address(addr, center):
    try:
        m = kit.get_json(CENSUS, {"address": addr, "benchmark": "Public_AR_Current", "format": "json"})
        hits = m["result"]["addressMatches"]
        if hits:
            c = hits[0]["coordinates"]
            return c["y"], c["x"], "census: " + hits[0]["matchedAddress"], ""
    except Exception:
        pass  # outside the US or the service is down; fall through to Photon
    for f in photon(addr, center, limit=1):
        lon, lat = f["geometry"]["coordinates"]
        if kit.km(center, (lat, lon)) <= MAX_KM:
            return lat, lon, "osm: " + describe(f["properties"]), ""
    return None


def by_name(name, cfg, center):
    best = None
    base = re.sub(r"\(.*?\)", "", name).replace(" / ", " ").strip()
    for f in photon(f"{base} {cfg['city']}", center):
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        if kit.km(center, (lat, lon)) > MAX_KM or p.get("osm_key") in {"highway", "boundary", "place"}:
            continue
        sim = similarity(name, p.get("name", ""))
        if best is None or sim > best[0]:
            best = (sim, lat, lon, f"osm: {p.get('name', '')} ({describe(p)})")
    if not best:
        return None
    sim, lat, lon, label = best
    return lat, lon, label, "" if sim >= 0.85 else "check"


def main():
    cfg = kit.load_config()
    rows = kit.read_csv(kit.PLACES_CSV)
    if not rows:
        raise SystemExit("data/places.csv is empty. Add at least a name column.")
    fields = list(rows[0])
    for col in ["address", "lat", "lon", "geocoded_by", "review"]:
        if col not in fields:
            fields.append(col)

    todo = [r for r in rows if r.get("name") and not (r.get("lat") and r.get("lon"))]
    if not todo:
        print("Every place already has lat/lon. Nothing to do.")
        return
    center = city_center(cfg)
    print(f"Geocoding {len(todo)} places near {cfg['city']} ({center[0]:.3f}, {center[1]:.3f})\n")

    for r in todo:
        hit = (by_address(r["address"], center) if r.get("address") else None) or by_name(r["name"], cfg, center)
        if hit:
            lat, lon, label, review = hit
            r.update(lat=f"{lat:.6f}", lon=f"{lon:.6f}", geocoded_by=label, review=review)
        else:
            r.update(geocoded_by="no match", review="missing")
        print(f"  {(r['review'] or 'ok'):8s} {r['name'][:32]:32s} -> {r['geocoded_by']}")

    kit.write_csv(kit.PLACES_CSV, rows, fields)
    check = [r["name"] for r in rows if r.get("review") == "check"]
    missing = [r["name"] for r in rows if r.get("review") == "missing"]
    print(f"\nUpdated data/places.csv. {len(check)} to double-check, {len(missing)} not found.")
    if check:
        print("Double-check (best guess was a loose name match):", ", ".join(check))
    if missing:
        print("Not found: add an address or type lat/lon in by hand:", ", ".join(missing))
    print("Once a pin looks right, clear its review cell (or set it to ok).")


if __name__ == "__main__":
    main()
