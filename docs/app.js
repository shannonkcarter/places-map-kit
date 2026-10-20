(() => {
  const HOVER = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const PHONE = () => window.matchMedia('(max-width: 720px)').matches;
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const $ = id => document.getElementById(id);

  let cfg, places = [], map, heatLayer, highlightLayer, selected = null;
  const byName = new Map();
  const markers = new Map();

  // ---------- helpers ----------
  const plural = (n, word) => `${n} ${n === 1 ? word : word.replace(/([^aeiou])y$/, '$1ie').replace(/(s|x|ch|sh)$/, '$1e') + 's'}`;
  const parseDate = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const fmtDate = s => s ? parseDate(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'Undated';

  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => k === 'class' ? (n.className = v) : n.setAttribute(k, v));
    kids.flat().forEach(k => n.append(k));
    return n;
  }
  const link = (href, text) => el('a', { href, target: '_blank', rel: 'noopener' }, text);

  // ---------- setup from config ----------
  function applyConfig() {
    const root = document.documentElement.style;
    if (cfg.colors?.pin) root.setProperty('--pin', cfg.colors.pin);
    if (cfg.colors?.route) root.setProperty('--route', cfg.colors.route);
    document.title = cfg.title || 'Places Map';
    $('title').textContent = cfg.title || 'Places Map';
    $('emoji').textContent = cfg.emoji || '';
    if (cfg.emoji) {
      $('favicon').href = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>${cfg.emoji}</text></svg>`;
    }
    if (cfg.about) { $('about').textContent = cfg.about; $('about').hidden = false; }
    cfg.place_word = cfg.place_word || 'place';
    cfg.visit_word = cfg.visit_word || 'visit';
    $('listTitle').textContent = `All ${plural(2, cfg.place_word).slice(2)}`;
    $('search').placeholder = `Search ${plural(places.length, cfg.place_word)}`;

    const visits = places.flatMap(p => p.visits);
    const dates = visits.map(v => v.date).filter(Boolean).sort();
    const bits = [plural(places.length, cfg.place_word)];
    if (visits.length) bits.push(plural(visits.length, cfg.visit_word));
    if (dates.length) bits.push('since ' + parseDate(dates[0]).toLocaleDateString(undefined, { month: 'short', year: 'numeric' }));
    $('stats').textContent = cfg.subtitle ? `${cfg.subtitle} · ${bits.join(' · ')}` : bits.join(' · ');
  }

  // ---------- map ----------
  function initMap() {
    map = L.map('map', { renderer: L.canvas({ tolerance: 10 }), zoomSnap: 0.5 });  // tolerance = bigger tap target
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
    L.tileLayer(esri + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
    }).addTo(map);
    map.createPane('labels').style.zIndex = 400;
    map.getPane('labels').style.pointerEvents = 'none';
    L.tileLayer(esri + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, pane: 'labels' }).addTo(map);

    // every route drawn faintly on top of each other: busy streets glow
    map.createPane('heat').style.zIndex = 350;
    map.createPane('highlight').style.zIndex = 450;
    const heatRenderer = L.canvas({ pane: 'heat' });
    const allRoutes = places.flatMap(p => p.routes);
    heatLayer = L.layerGroup(allRoutes.map(rt => L.polyline(rt.coords, {
      renderer: heatRenderer, color: css('--route'), weight: 3, opacity: 0.16, interactive: false,
    })));
    if (allRoutes.length) {
      $('heatLabel').hidden = false;
      heatLayer.addTo(map);
      $('heatToggle').addEventListener('change', e => e.target.checked ? heatLayer.addTo(map) : heatLayer.remove());
    }
    highlightLayer = L.layerGroup().addTo(map);

    // Place details live in a card in the side panel (bottom sheet on phones), never over the map,
    // so the highlighted route stays visible. Mouse: hover selects. Touch: tap selects.
    let hoverTimer;
    places.forEach(place => {
      const m = L.circleMarker([place.lat, place.lon], { ...styleMarker(place), bubblingMouseEvents: false })
        .on('click', () => select(place, { move: !HOVER }))
        .addTo(map);
      if (HOVER) {
        m.on('mouseover', () => {
          clearTimeout(hoverTimer);
          hoverTimer = setTimeout(() => { if (selected !== place) select(place); }, 120);  // skip pins swept past
        }).on('mouseout', () => clearTimeout(hoverTimer));
      }
      markers.set(place.name, m);
    });
    map.on('click', () => select(null));
    map.fitBounds(places.map(p => [p.lat, p.lon]), { padding: [30, 30], animate: false, maxZoom: 15 });
  }

  function styleMarker(place) {
    const r = 6 + 2 * Math.sqrt(place.visits.length);
    const ring = selected === place ? { color: css('--ink'), weight: 3 } : { color: '#fff', weight: 1.5 };
    return { radius: r, ...ring, fillColor: css('--pin'), fillOpacity: 0.95 };
  }

  function showRoutes(place) {
    highlightLayer.clearLayers();
    place.routes.forEach(rt => L.polyline(rt.coords, {
      pane: 'highlight', color: css('--route'), weight: 4, opacity: 0.85, interactive: false,
    }).addTo(highlightLayer));
  }

  function select(place, { move = false } = {}) {
    selected = place;
    place ? showRoutes(place) : highlightLayer.clearLayers();
    history.replaceState(null, '', place ? '#' + encodeURIComponent(place.name) : location.pathname + location.search);
    render();
    if (place) markers.get(place.name).bringToFront();
    if (place && move) {
      // fit the pin and its routes into the part of the map not covered by the bottom sheet
      const pts = [[place.lat, place.lon], ...place.routes.flatMap(rt => rt.coords)];
      const sheet = PHONE() ? $('panel').offsetHeight : 0;
      map.flyToBounds(L.latLngBounds(pts), {
        paddingTopLeft: [24, 24], paddingBottomRight: [24, sheet + 24], maxZoom: 15, duration: 0.6,
      });
    }
  }

  // ---------- panel ----------
  function cardContent(place) {
    const x = el('button', { class: 'card-close', type: 'button', 'aria-label': 'Close' }, '×');
    x.addEventListener('click', () => select(null));
    const box = el('div', { class: 'pop' }, x, el('h3', {}, place.link ? link(place.link, place.name) : place.name));
    if (place.address) box.append(el('p', { class: 'addr' }, place.address));
    if (place.notes) box.append(el('p', { class: 'note' }, place.notes));

    const bits = [];
    if (place.visits.length) bits.push(plural(place.visits.length, cfg.visit_word));
    if (place.routes.length) bits.push(`${place.routes.length === 1 ? 'route' : 'routes'} highlighted on the map`);
    if (bits.length) box.append(el('p', { class: 'addr' }, bits.join(' · ')));
    if (place.visits.length) {
      box.append(el('ul', { class: 'visits' }, place.visits.slice().reverse().map(v => {
        const li = el('li', {}, fmtDate(v.date));
        if (v.notes) li.append(' · ', v.notes);
        v.links.forEach(href => li.append(' · ', link(href, 'route ↗')));
        return li;
      })));
    }
    return box;
  }

  // list rows: hover previews the place's routes and outlines its pin, click flies there
  function bindRow(li, place) {
    li.addEventListener('click', () => {
      if (PHONE()) $('panel').classList.remove('open');
      select(place, { move: true });
    });
    if (!HOVER) return;
    li.addEventListener('mouseenter', () => {
      showRoutes(place);
      markers.get(place.name).setStyle({ color: css('--ink'), weight: 3 }).bringToFront();
    });
    li.addEventListener('mouseleave', () => {
      markers.get(place.name).setStyle(styleMarker(place));
      selected ? showRoutes(selected) : highlightLayer.clearLayers();
    });
  }

  function render() {
    markers.forEach((m, name) => m.setStyle(styleMarker(byName.get(name))));
    $('card').hidden = !selected;
    $('card').replaceChildren(...(selected ? [cardContent(selected)] : []));

    const q = $('search').value.trim().toLowerCase();
    const shown = places.filter(p => !q || p.name.toLowerCase().includes(q) || p.notes.toLowerCase().includes(q));
    $('count').textContent = shown.length;
    $('list').replaceChildren(...(shown.length ? shown.map(p => {
      const li = el('li', { class: p === selected ? 'on' : '' },
        el('span', { class: 'name' }, p.name),
        el('span', { class: 'meta' }, p.visits.length > 1 ? plural(p.visits.length, cfg.visit_word) : ''));
      bindRow(li, p);
      return li;
    }) : [el('li', { class: 'empty' }, 'No matches')]));
  }

  // ---------- boot ----------
  async function boot() {
    const data = await fetch('data.json').then(r => r.json());
    cfg = data.config || {};
    // most-visited first, then alphabetical
    places = data.places.sort((a, b) => b.visits.length - a.visits.length || a.name.localeCompare(b.name));
    places.forEach(p => byName.set(p.name, p));
    applyConfig();
    initMap();
    render();

    $('search').addEventListener('input', render);
    $('panelHandle').addEventListener('click', () => {
      const p = $('panel');
      p.classList.toggle('open');
      $('panelHandle').setAttribute('aria-expanded', p.classList.contains('open'));
    });
    // a link like .../#Blacksmith opens straight to that place
    const fromHash = () => {
      const place = byName.get(decodeURIComponent(location.hash.slice(1)));
      if (place && place !== selected) select(place, { move: true });
    };
    window.addEventListener('hashchange', fromHash);
    fromHash();
  }

  boot().catch(err => {
    $('title').textContent = 'Could not load docs/data.json';
    $('stats').textContent = 'Run python3 scripts/build.py, then reload.';
    console.error(err);
  });
})();
