---
name: places-map
description: Turn the user's list of places (coffee shops, restaurants, parks, trailheads, club meetups...) into an interactive map with optional GPX or Strava routes, preview it, and publish it to GitHub Pages. Use when the user says "make my map", wants to add or fix places, routes or visits, change the map's look, or publish it.
---

# Places map

This repo is a template: CSVs in `data/` plus `config.json` → `scripts/build.py` → a static site in `docs/`
served by GitHub Pages. The scripts use only the Python standard library. The README documents every step for
people working by hand; keep what you do consistent with it.

Work through the steps in order, but skip any the user has already done. Keep the user in the loop with short
plain-language updates. Many users are not programmers, so explain what a step does rather than the command.

## 1. Gather the basics

Ask (together, in one message) for anything you can't infer:
- What the map is of, and the city or area. Use these for `title`, `city`, `place_word`, `visit_word` and a fitting `emoji`.
- Their list of places, in whatever form they have it: pasted text, a spreadsheet or CSV export, a Google
  Maps list they've typed out, notes. Addresses help but aren't required.
- Whether they have dates of visits and/or routes (GPX files or Strava links).

Offer a color pair for `colors.pin` and `colors.route` that suits the theme, and a one-line `about` text.
Update `config.json`.

## 2. Write the data

- Replace the example rows in `data/places.csv` (columns: name, address, notes, link, lat, lon).
  Keep names exactly as the user writes them; they're what the map shows.
- If they have visits, replace `data/visits.csv` (place, date, notes, route). `place` must match a name
  exactly. If not, write just the header row or delete the file.
- Delete the `data/routes/example-*.gpx` files once the examples are gone from the CSVs.
- If they pasted a messy list, show them the cleaned list of names before moving on.

## 3. Geocode

Run `python3 scripts/geocode.py`. It takes about a second per place, so warn them if the list is long.

Then review the results with the user. Don't just report counts:
- For each `review = check` row, say what it matched (the `geocoded_by` column) and ask if that's the right
  place. Chain locations and generic names are the usual problems.
- For `review = missing`, ask for an address or coordinates.
- Fix rows by editing lat/lon (or adding an address and clearing lat/lon, then rerunning). Set `review` to
  `ok` once confirmed. Rows that have lat/lon are never re-geocoded.

## 4. Routes (optional)

- GPX files: have the user drop them in `data/routes/` and reference the file names in the `route` column of
  visits.csv (or places.csv if they don't track visits).
- Strava links: put them in the `route` column, walk the user through the one-time API app setup in the
  README (they create `strava_credentials.json` themselves; never ask them to paste the secret into chat),
  then run `python3 scripts/fetch_strava.py`. Strava only allows downloading routes the user owns.
  `strava.app.link` share links sometimes don't resolve; ask for the full `strava.com/...` link instead.
- Privacy: recorded activities get `route_trim_m` metres trimmed off each end. Mention it, and suggest raising
  it if they record runs from home.

## 5. Build and preview

Run `python3 scripts/build.py` and act on every note it prints (unknown place names with "did you mean",
missing route files, places skipped for lack of coordinates).

Start a preview with `python3 -m http.server 8000 -d docs` in the background (try another port if 8000 is
busy) and give the user the link. If you can view pages yourself, look at it: pins far from the rest are
usually bad geocodes.

## 6. Publish

Check `git remote -v`. If they started from the template on GitHub, commit and push, then enable Pages:

```bash
gh api -X POST repos/OWNER/REPO/pages -f "source[branch]=main" -f "source[path]=/docs"
```

(or Settings → Pages → Deploy from a branch → main, /docs). Give them `https://OWNER.github.io/REPO/`.
Confirm before pushing: the repo is public. If there's no GitHub remote yet, help them create one with
`gh repo create` or point them to the README.

## Later changes

To add places or routes: edit the CSVs, run geocode (new places only), build, push. To change the look:
`config.json` for title, colors and labels; `docs/style.css` and `docs/app.js` for anything deeper. Bump the
`?v=` numbers in `docs/index.html` after changing CSS or JS so browsers pick up the new files.
