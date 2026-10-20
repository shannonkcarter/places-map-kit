"""Optional: download GPX for every Strava link in the route columns of data/visits.csv and data/places.csv.

Usage: python3 scripts/fetch_strava.py

One-time setup:
  1. Create an API app at https://www.strava.com/settings/api
     (any name/website; set "Authorization Callback Domain" to localhost).
  2. Save its Client ID and Client Secret in strava_credentials.json at the repo root:
       {"client_id": "12345", "client_secret": "abc..."}
     (this file is git-ignored; never commit it)
The first run opens a browser to approve access; the token is cached in .strava_token.json.

Strava only lets you download routes and activities you own (or private ones you have access to),
so links shared by friends will usually fail. Ask them for a GPX export instead.
Downloads land in data/routes/strava/ (git-ignored) with an index.json that build.py reads.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import kit

CREDS = os.path.join(kit.ROOT, "strava_credentials.json")
TOKEN_FILE = os.path.join(kit.ROOT, ".strava_token.json")
OUT_DIR = os.path.join(kit.ROUTES, "strava")
INDEX = os.path.join(OUT_DIR, "index.json")
PORT = 8723
API = "https://www.strava.com/api/v3"


def load_creds():
    if not os.path.exists(CREDS):
        sys.exit("Missing strava_credentials.json. See the setup steps at the top of this script.")
    c = json.load(open(CREDS))
    return str(c["client_id"]), c["client_secret"]


def authorize(client_id, secret):
    code = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code["value"] = q.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Strava access approved. You can close this tab.")

        def log_message(self, *a):
            pass

    url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "approval_prompt": "auto",
        "redirect_uri": f"http://localhost:{PORT}/callback",
        "scope": "read,read_all,activity:read_all",
    })
    print("Opening browser to approve Strava access:\n" + url)
    webbrowser.open(url)
    server = HTTPServer(("localhost", PORT), Handler)
    while "value" not in code:
        server.handle_request()
    if not code["value"]:
        sys.exit("Authorization was declined.")
    return token_request(client_id, secret, grant_type="authorization_code", code=code["value"])


def token_request(client_id, secret, **params):
    data = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret, **params}).encode()
    tok = json.load(urllib.request.urlopen("https://www.strava.com/oauth/token", data))
    json.dump(tok, open(TOKEN_FILE, "w"))
    os.chmod(TOKEN_FILE, 0o600)
    return tok


def get_token():
    client_id, secret = load_creds()
    if not os.path.exists(TOKEN_FILE):
        return authorize(client_id, secret)["access_token"]
    tok = json.load(open(TOKEN_FILE))
    if tok["expires_at"] < time.time() + 60:
        tok = token_request(client_id, secret, grant_type="refresh_token", refresh_token=tok["refresh_token"])
    return tok["access_token"]


def api(path, token, raw=False):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(3):
        try:
            body = urllib.request.urlopen(req).read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                print("  rate limited, waiting 60s")
                time.sleep(60)
                continue
            raise


def resolve(url):
    """Return ('routes'|'activities', id) for a Strava URL, following strava.app.link share links."""
    m = re.search(r"strava\.com/(routes|activities)/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    if "strava.app.link" in url:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            html = urllib.parse.unquote(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore"))
        except Exception:
            return None
        m = re.search(r"strava\.com/(routes|activities)/(\d+)", html)
        if m:
            return m.group(1), m.group(2)
    return None


def activity_gpx(act_id, token):
    streams = api(f"/activities/{act_id}/streams?keys=latlng&key_by_type=true", token)
    trk = "".join(f'<trkpt lat="{lat}" lon="{lon}"/>' for lat, lon in streams.get("latlng", {}).get("data", []))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="places-map-kit"><trk><trkseg>{trk}</trkseg></trk></gpx>'.encode()


def main():
    urls = []
    for path, col in [(kit.VISITS_CSV, "route"), (kit.PLACES_CSV, "route")]:
        for r in kit.read_csv(path):
            urls += [v for v in kit.route_values(r.get(col, "")) if "strava" in v]
    urls = list(dict.fromkeys(urls))
    index = json.load(open(INDEX)) if os.path.exists(INDEX) else {}
    todo = [u for u in urls if u not in index]
    print(f"{len(urls)} Strava links, {len(urls) - len(todo)} already downloaded, {len(todo)} to fetch")
    if not todo:
        return
    token = get_token()
    os.makedirs(OUT_DIR, exist_ok=True)
    failed = []
    for url in todo:
        target = resolve(url)
        if not target:
            failed.append((url, "share link didn't resolve; open it and paste the full strava.com link instead"))
            continue
        kind, sid = target
        try:
            gpx = api(f"/routes/{sid}/export_gpx", token, raw=True) if kind == "routes" else activity_gpx(sid, token)
        except urllib.error.HTTPError as e:
            reason = {404: "not found, or not yours", 403: "no access"}.get(e.code, f"HTTP {e.code}")
            failed.append((url, reason))
            continue
        name = f"{kind}-{sid}.gpx"
        open(os.path.join(OUT_DIR, name), "wb").write(gpx)
        index[url] = {"file": f"strava/{name}", "kind": kind}
        print(f"  ok  {kind:10s} {url}")
        time.sleep(0.5)
    json.dump(index, open(INDEX, "w"), indent=1)
    for url, reason in failed:
        print(f"  failed: {url}  ({reason})")
    print(f"\nDownloaded {len(todo) - len(failed)}/{len(todo)}. Now run: python3 scripts/build.py")


if __name__ == "__main__":
    main()
