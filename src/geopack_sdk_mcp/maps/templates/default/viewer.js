/* Geopack map viewer runtime (shared). See viewer.html for the page shell. */
// Per-map values are injected by viewer.html into window.GP_VIEWER; this runtime
// itself is shared by every template (the shipped default and user drop-ins).
const BOOT = (typeof window !== 'undefined' && window.GP_VIEWER) || {};
const TEMPLATE = BOOT.template || {};
const MANIFEST_URL = BOOT.manifestUrl || '';
const TOKEN_EMBEDDED = BOOT.token || '';

function queryToken() {
  try { return new URLSearchParams(location.search).get('t') || ''; }
  catch (e) { return ''; }
}
function hashToken() {
  const m = (location.hash || '').match(/[#&]t=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}
// The server embeds a VALID token into the shell; otherwise read ?t= then #t=.
const TOKEN = TOKEN_EMBEDDED || queryToken() || hashToken();

// Optional view override from the URL, so an agent (or a user) can point an
// existing map at a place without recreating it: ?center=lon,lat&zoom=N (or
// ?lon=&lat=&z=). When present the auto-fit is suppressed so the view stays put.
const VIEW_OVERRIDE = (function () {
  try {
    const q = new URLSearchParams(location.search);
    const out = {};
    const center = q.get('center');
    if (center) {
      const parts = center.split(',').map(Number);
      if (parts.length === 2 && isFinite(parts[0]) && isFinite(parts[1])) {
        out.center = [parts[0], parts[1]];
      }
    }
    const lat = q.get('lat');
    const lon = q.get('lon') || q.get('lng');
    if (lat !== null && lon !== null && isFinite(Number(lat)) && isFinite(Number(lon))) {
      out.center = [Number(lon), Number(lat)];
    }
    const zoom = q.get('zoom') || q.get('z');
    if (zoom !== null && isFinite(Number(zoom))) out.zoom = Number(zoom);
    return out;
  } catch (e) { return {}; }
})();
const VIEW_OVERRIDE_ACTIVE = !!VIEW_OVERRIDE.center || VIEW_OVERRIDE.zoom != null;
function withToken(url) {
  if (!url) return url;
  if (/[?&]t=/.test(url)) return url;
  return url + (url.indexOf('?') >= 0 ? '&' : '?') + 't=' + encodeURIComponent(TOKEN);
}
function banner(message) {
  const el = document.getElementById('banner');
  el.textContent = message;
  el.style.display = 'block';
}

// XYZ tile loader (OSM basemaps and portal XYZ layers). The shell is served with
// `Referrer-Policy: no-referrer`, which makes OSM answer every tile with its
// "access blocked" policy image (a 200 whose body is a policy picture). A
// per-element referrer policy overrides the document policy, so each tile <img>
// sends the ORIGIN as Referer — never the path/query, so the session token is
// not leaked. This mirrors the frontend's OsmWebTileLayer (strict-origin referer).
function xyzTileLoad(imageTile, src) {
  const img = imageTile.getImage();
  img.referrerPolicy = 'strict-origin-when-cross-origin';
  img.src = src;
}

const BASE_STYLE = TEMPLATE.layerStyle || {};
const PALETTE = (Array.isArray(TEMPLATE.layerPalette) && TEMPLATE.layerPalette.length)
  ? TEMPLATE.layerPalette
  : ['#3ba776', '#3b7fa7', '#c2703b', '#8b5cf6', '#d1477a', '#2f9e8f'];

// Merge the template's base layer style with a layer's own `style`; a missing
// fill rotates through the palette so several layers are separable. This is the
// style ACTUALLY applied to vector features — not just the legend swatch.
function resolveStyle(spec, index) {
  const perLayer = (spec && spec.style) || {};
  const merged = Object.assign({}, BASE_STYLE, perLayer);
  if (!merged.fill) merged.fill = PALETTE[index % PALETTE.length];
  return merged;
}

function vectorStyle(layerStyle) {
  const s = layerStyle || BASE_STYLE;
  const stroke = new ol.style.Stroke({ color: s.stroke || '#14532d', width: s.weight || 2 });
  const fill = new ol.style.Fill({ color: s.fill || '#3ba776' });
  return new ol.style.Style({
    stroke: stroke,
    fill: fill,
    image: new ol.style.Circle({ radius: s.radius || 5,
      stroke: stroke, fill: fill })
  });
}

// The portable style spec (slice 033 §12) drives a style FUNCTION: uniqueValue
// matches a feature property, classBreaks buckets a numeric value, simple is
// constant. The legend is built from the SAME spec, so map and legend agree.
function symbologyStyleFn(sym) {
  const fallback = sym.simple || sym.default || BASE_STYLE;
  return function (feature) {
    let s = fallback;
    if (sym.type === 'uniqueValue' && sym.field) {
      const raw = feature.get(sym.field);
      const key = raw === null || raw === undefined ? '' : String(raw);
      const hit = (sym.unique || []).find(function (e) { return String(e.value) === key; });
      if (hit && hit.style) s = hit.style;
    } else if (sym.type === 'classBreaks' && sym.field) {
      const n = Number(feature.get(sym.field));
      if (isFinite(n)) {
        const hit = (sym.breaks || []).find(function (b) {
          const min = b.min === null || b.min === undefined ? -Infinity : b.min;
          const max = b.max === null || b.max === undefined ? Infinity : b.max;
          return n >= min && n <= max;
        });
        if (hit && hit.style) s = hit.style;
      }
    }
    return vectorStyle(s);
  };
}

// A GeoJSON feature may carry its own `properties.style` ({fill,stroke,weight,
// radius,opacity}); that styles it on top of the layer style. Styles are cached by
// value so a FeatureCollection only builds one Style per distinct style object.
function makeVectorStyle(baseStyle, sym) {
  const staticStyle = vectorStyle(baseStyle);
  const symFn = sym ? symbologyStyleFn(sym) : null;
  const cache = {};
  function perFeature(fs) {
    const key = JSON.stringify(fs);
    if (!cache[key]) {
      cache[key] = vectorStyle(Object.assign({}, baseStyle, {
        fill: fs.fill || baseStyle.fill,
        stroke: fs.stroke || baseStyle.stroke,
        weight: fs.weight != null ? fs.weight : baseStyle.weight,
        radius: fs.radius != null ? fs.radius : baseStyle.radius,
        opacity: fs.opacity != null ? fs.opacity : baseStyle.opacity
      }));
    }
    return cache[key];
  }
  return function (feature, resolution) {
    const fs = feature && feature.get ? feature.get('__style__') : null;
    if (fs && typeof fs === 'object' && !Array.isArray(fs)) return perFeature(fs);
    return symFn ? symFn(feature, resolution) : staticStyle;
  };
}

// WMS/WMTS/XYZ are images rendered elsewhere: a per-layer `style` cannot recolour
// them, and the legend must show a raster swatch rather than a vector colour.
function isRasterRender(render) {
  return render === 'wms' || render === 'wmts' || render === 'xyz' || render === 'cog';
}

function basemapLayer(entry) {
  if (!entry || entry.type === 'none') return null;
  return new ol.layer.Tile({
    source: new ol.source.XYZ({
      url: entry.url,
      attributions: entry.attribution || undefined,
      maxZoom: entry.maxZoom || 19,
      tileLoadFunction: xyzTileLoad
    }),
    properties: { basemap: entry.id }
  });
}

function buildLayer(spec, index) {
  const render = spec.render || (spec.kind === 'portal-publication' ? 'wms' : 'geojson');
  const resolved = resolveStyle(spec, index);
  // A dataset's saved symbology (if the MCP derived one) wins over the palette;
  // an explicit simple `style` still wins over the derived spec. `appliedSym` is
  // what the layer ACTUALLY draws with, and is the ONLY thing the legend reads —
  // so map and legend cannot disagree when a caller overrides the spec.
  const appliedSym = spec.symbology && !spec.style ? spec.symbology : null;
  const styleArg = makeVectorStyle(resolved, appliedSym);
  let source, layer;
  if (render === 'geojson') {
    // The source is left empty here; the GeoJSON is streamed by loadGeojsonLayer
    // so the legend can show real download progress for large datasets.
    source = new ol.source.Vector();
    layer = new ol.layer.Vector({ source: source, style: styleArg });
    layer.set('gpLoadUrl', spec.dataUrl);
  } else if (render === 'mvt') {
    source = new ol.source.VectorTile({ format: new ol.format.MVT(), url: withToken(spec.tileUrl) });
    layer = new ol.layer.VectorTile({ source: source, style: styleArg });
  } else if (render === 'wms') {
    source = new ol.source.TileWMS({ url: spec.wmsUrl, params: { t: TOKEN } });
    layer = new ol.layer.Tile({ source: source });
  } else if (render === 'wmts') {
    source = new ol.source.TileWMS({ url: spec.wmtsUrl, params: { t: TOKEN } });
    layer = new ol.layer.Tile({ source: source });
  } else if (render === 'xyz') {
    source = new ol.source.XYZ({ url: spec.xyzUrl, tileLoadFunction: xyzTileLoad });
    layer = new ol.layer.Tile({ source: source });
  } else if (render === 'cog') {
    // A Cloud-Optimized GeoTIFF is byte-served by the map service (/cog) with
    // Range forwarding; ol/source/GeoTIFF reads the IFDs and overviews on demand,
    // so the whole raster never downloads and the browser can pan/zoom into it.
    source = new ol.source.GeoTIFF({ sources: [{ url: withToken(spec.cogUrl) }] });
    layer = new ol.layer.WebGLTile({ source: source });
  } else {
    source = new ol.source.Vector();
    layer = new ol.layer.Vector({ source: source, style: styleArg });
    layer.set('gpLoadUrl', spec.dataUrl);
  }
  layer.set('title', spec.title || spec.id);
  layer.set('gpId', spec.id);
  layer.set('gpRender', render);
  layer.set('gpStyle', resolved);
  layer.set('gpSymbology', appliedSym);
  layer.set('gpRaster', !!spec.raster);
  layer.set('gpFields', Array.isArray(spec.fields) ? spec.fields : []);
  layer.set('gpWmsUrl', spec.wmsUrl || '');
  layer.set('gpIdentifyLayers', spec.identifyWmsLayers || '');
  layer.set('gpRasterBands', Array.isArray(spec.rasterBands) ? spec.rasterBands : []);
  layer.set('gpBbox', Array.isArray(spec.bbox) ? spec.bbox : null);
  return layer;
}

async function wfsLayer(spec, index) {
  const url = withToken(spec.wfsUrl) +
    '&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&outputFormat=application/json&srsName=EPSG:4326';
  const response = await fetch(url);
  if (!response.ok) throw new Error('WFS ' + response.status);
  const geo = await response.json();
  const source = new ol.source.Vector({
    features: new ol.format.GeoJSON().readFeatures(geo, { featureProjection: 'EPSG:3857' })
  });
  const resolved = resolveStyle(spec, index);
  const appliedSym = spec.symbology && !spec.style ? spec.symbology : null;
  const styleArg = makeVectorStyle(resolved, appliedSym);
  const layer = new ol.layer.Vector({ source: source, style: styleArg });
  layer.set('gpRender', 'wfs');
  layer.set('gpStyle', resolved);
  layer.set('gpSymbology', appliedSym);
  layer.set('gpRaster', false);
  layer.set('gpFields', Array.isArray(spec.fields) ? spec.fields : []);
  layer.set('gpBbox', Array.isArray(spec.bbox) ? spec.bbox : null);
  layer.set('title', spec.title || spec.id);
  layer.set('gpId', spec.id);
  return layer;
}

// A large GeoJSON layer (a "whole dataset" `limit:0` can be tens of MB) otherwise
// looks frozen while it downloads. These helpers stream the body so the legend
// shows a byte/percentage progress bar until the layer is on the map.
function progressEl(id) { return document.getElementById('gp-prog-' + id); }

function setProgress(id, received, total) {
  const el = progressEl(id);
  if (!el) return;
  const mb = function (n) { return (n / 1048576).toFixed(1); };
  if (total > 0) {
    const pct = Math.min(100, Math.round((received / total) * 100));
    el.innerHTML = '<span class="bar"><i style="width:' + pct + '%"></i></span>' +
      mb(received) + '/' + mb(total) + ' MB (' + pct + '%)';
  } else {
    el.innerHTML = '<span class="spin"></span>' + mb(received) + ' MB';
  }
}

function clearProgress(id) {
  const el = progressEl(id);
  if (el) el.remove();
}

async function streamGeojson(url, onProgress) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('data HTTP ' + response.status);
  const total = Number(response.headers.get('Content-Length') || 0);
  if (!response.body || typeof response.body.getReader !== 'function') {
    const geo = await response.json();
    if (onProgress) onProgress(total, total);
    return geo;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  for (;;) {
    const step = await reader.read();
    if (step.done) break;
    chunks.push(step.value);
    received += step.value.length;
    if (onProgress) onProgress(received, total);
  }
  return JSON.parse(await new Blob(chunks).text());
}

// A bare GeoJSON geometry (an inline-geometry layer may carry one) must be wrapped
// into a Feature so OL can read it; its `properties.style` (if present) is kept.
function asFeatureCollection(geo) {
  if (!geo || typeof geo !== 'object') return geo;
  if (geo.type === 'FeatureCollection' || geo.type === 'Feature') return geo;
  return {
    type: 'Feature',
    geometry: geo,
    properties: (geo.properties && typeof geo.properties === 'object') ? geo.properties : {}
  };
}

async function loadGeojsonLayer(layer, map) {
  const id = layer.get('gpId');
  const url = layer.get('gpLoadUrl');
  if (!url) return;
  try {
    const geo = await streamGeojson(withToken(url), function (received, total) {
      setProgress(id, received, total);
    });
    const features = new ol.format.GeoJSON().readFeatures(asFeatureCollection(geo), {
      featureProjection: 'EPSG:3857'
    });
    layer.getSource().addFeatures(features);
    clearProgress(id);
    if (TEMPLATE.view && TEMPLATE.view.mode === 'fit' && !VIEW_OVERRIDE_ACTIVE && features.length) {
      try { map.getView().fit(layer.getSource().getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17 }); } catch (e) {}
    }
  } catch (err) {
    clearProgress(id);
    banner('Layer "' + (layer.get('title') || id) + '" failed: ' + err.message);
  }
}

function loadPendingVectors(map, dataLayers) {
  dataLayers.forEach(function (layer) {
    if (layer.get('gpLoadUrl')) { loadGeojsonLayer(layer, map); }
  });
}

// Fit the view to a layer's extent: the manifest WGS84 bbox (present for every
// layer whose dataset extent is known) or, failing that, the vector source extent.
function zoomToLayer(map, layer) {
  let extent = null;
  const box = validWgs84BBox(layer.get('gpBbox'));
  if (box) extent = ol.proj.transformExtent(box, 'EPSG:4326', 'EPSG:3857');
  if (!extent) {
    const source = layer.getSource && layer.getSource();
    if (source && typeof source.getExtent === 'function') {
      try {
        const src = source.getExtent();
        if (src && isFinite(src[0]) && !ol.extent.isEmpty(src)) extent = src;
      } catch (e) { extent = null; }
    }
  }
  if (!extent || ol.extent.isEmpty(extent)) return;
  map.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 18 });
}

function renderPanel(map, baseLayers, dataLayers) {
  const panel = document.getElementById('panel');
  let html = '';
  const showList = TEMPLATE.layerList !== false;
  const showLegend = TEMPLATE.legend !== false;
  if (TEMPLATE.basemaps && TEMPLATE.basemaps.length) {
    html += '<details class="gp-section" open><summary>Background</summary><div class="gp-section-body">';
    html += '<select id="basemap">';
    TEMPLATE.basemaps.forEach(function (entry) {
      const selected = entry.id === (TEMPLATE.basemap || '');
      html += '<option value="' + entry.id + '"' + (selected ? ' selected' : '') + '>' +
        (entry.label || entry.id) + '</option>';
    });
    html += '</select></div></details>';
  }
  if (showList) html += '<details class="gp-section" open><summary>Layers</summary>' +
    '<div id="layers" class="gp-section-body"></div></details>';
  if (showLegend) html += '<details class="gp-section" open><summary>Legend</summary>' +
    '<div id="legend" class="gp-section-body"></div></details>';
  panel.innerHTML = html;

  const select = document.getElementById('basemap');
  if (select) {
    select.addEventListener('change', function () {
      baseLayers.forEach(function (l) { l.setVisible(l.get('basemap') === select.value); });
    });
  }

  // Every manifest layer (all kinds) is listed here with a visibility toggle and
  // an opacity slider. Basemaps are the background selector, not listed.
  const listEl = document.getElementById('layers');
  if (listEl) {
    if (!dataLayers.length) {
      const empty = document.createElement('div');
      empty.className = 'gp-empty';
      empty.textContent = 'No layers';
      listEl.appendChild(empty);
    }
    // Newest layer = drawn on top; list it at the TOP so the panel mirrors the map
    // stacking (reverse of dataLayers, which is bottom→top).
    dataLayers.slice().reverse().forEach(function (layer) {
      const row = document.createElement('div');
      row.className = 'row';
      const top = document.createElement('div');
      top.className = 'row-top';
      const check = document.createElement('input');
      check.type = 'checkbox';
      check.checked = layer.getVisible();
      check.addEventListener('change', function () { layer.setVisible(check.checked); });
      const label = document.createElement('span');
      label.className = 'gp-name';
      label.textContent = layer.get('title');
      label.title = layer.get('title');
      const zoom = document.createElement('button');
      zoom.type = 'button';
      zoom.className = 'gp-zoom';
      zoom.title = 'Zoom to layer';
      zoom.setAttribute('aria-label', 'Zoom to layer');
      // Magnifier glyph (🔍) as a clean monochrome SVG so it stays legible on mobile.
      zoom.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" ' +
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20.5 20.5l-5-5"/></svg>';
      zoom.addEventListener('click', function () { zoomToLayer(map, layer); });
      top.appendChild(check); top.appendChild(label); top.appendChild(zoom);
      const slider = document.createElement('input');
      slider.type = 'range';
      slider.min = '0'; slider.max = '1'; slider.step = '0.05';
      slider.value = String(layer.getOpacity());
      slider.title = 'Opacity';
      slider.setAttribute('aria-label', 'Opacity');
      slider.addEventListener('input', function () { layer.setOpacity(parseFloat(slider.value)); });
      row.appendChild(top); row.appendChild(slider);
      listEl.appendChild(row);
    });
  }

  // The legend is drawn AFTER `panel.innerHTML` is set (drawing it earlier was
  // wiped by the innerHTML reset — why the legend looked empty).
  const legendEl = document.getElementById('legend');
  if (legendEl) {
    if (!dataLayers.length) {
      const empty = document.createElement('div');
      empty.className = 'gp-empty';
      empty.textContent = 'No layers';
      legendEl.appendChild(empty);
    }
    // Legend mirrors the same top-to-bottom stacking order as the layer list.
    dataLayers.slice().reverse().forEach(function (layer) {
      const render = layer.get('gpRender');
      const s = layer.get('gpStyle') || BASE_STYLE;
      const sym = layer.get('gpSymbology');
      const base = (sym && (sym.simple || sym.default)) || s;
      const legendEntries = sym && sym.legend && Array.isArray(sym.legend.entries)
        ? sym.legend.entries.filter(function (e) { return e && e.style; })
        : null;
      const item = document.createElement('div');
      item.className = 'item';
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      const label = document.createElement('span');
      label.style.flex = '1';
      if (isRasterRender(render) || layer.get('gpRaster')) {
        // An image layer (or a raster dataset) has no meaningful client colour;
        // show a raster swatch, not a fake vector fill.
        swatch.classList.add('raster');
        label.textContent = (layer.get('title') || '') + ' (raster)';
      } else {
        swatch.style.background = base.fill || '#3ba776';
        swatch.style.borderColor = base.stroke || 'rgba(0,0,0,.3)';
        label.textContent = layer.get('title');
      }
      item.appendChild(swatch); item.appendChild(label);
      if (layer.get('gpLoadUrl')) {
        const prog = document.createElement('span');
        prog.className = 'progress';
        prog.id = 'gp-prog-' + layer.get('gpId');
        prog.innerHTML = '<span class="spin"></span>';
        item.appendChild(prog);
      }
      if (legendEntries && legendEntries.length) {
        // A derived symbology legend (unique value / class breaks) is a block:
        // the layer title, then one swatch row per class — from the SAME spec the
        // style function draws with.
        const block = document.createElement('div');
        block.className = 'legend-block';
        block.appendChild(item);
        legendEntries.forEach(function (entry) {
          const es = entry.style || {};
          const row = document.createElement('div');
          row.className = 'item legend-sub';
          const sw = document.createElement('span');
          sw.className = 'swatch';
          sw.style.background = es.fill || es.stroke || '#3ba776';
          sw.style.borderColor = es.stroke || 'rgba(0,0,0,.3)';
          if (es.opacity !== undefined && es.opacity !== null) sw.style.opacity = String(es.opacity);
          const lb = document.createElement('span');
          lb.style.flex = '1';
          lb.textContent = (entry.label === null || entry.label === undefined || entry.label === '')
            ? '(no value)'
            : entry.label;
          row.appendChild(sw); row.appendChild(lb);
          block.appendChild(row);
        });
        legendEl.appendChild(block);
        return;
      }
      legendEl.appendChild(item);
    });
  }
}

// ---------------------------------------------------------------------------
// Identify: click a vector feature (geojson/mvt/wfs) to read its attributes.
// Field labels + coded-value domains come from the layer's manifest `fields`
// (the portal dataset's aliases/domains), so a code shows its human value.
// ---------------------------------------------------------------------------
function escapeHtml(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function fieldsIndex(layer) {
  const index = {};
  const fields = layer.get('gpFields');
  (Array.isArray(fields) ? fields : []).forEach(function (field) {
    if (field && field.name) index[field.name] = field;
  });
  return index;
}

function rowsFromProps(props, layer) {
  const index = fieldsIndex(layer);
  const source = props || {};
  const seen = {};
  const names = [];
  // Known fields (those with an alias/domain) first, in manifest order, then the rest.
  (layer.get('gpFields') || []).forEach(function (field) {
    const name = field && field.name;
    if (name && !seen[name] && Object.prototype.hasOwnProperty.call(source, name)) {
      seen[name] = true; names.push(name);
    }
  });
  Object.keys(source).forEach(function (name) {
    if (name === 'geometry' || name.charAt(0) === '@' || name === '__style__' || seen[name]) return;
    seen[name] = true; names.push(name);
  });
  return names.map(function (name) {
    const meta = index[name] || {};
    const raw = source[name];
    let value;
    if (raw === null || raw === undefined || raw === '') {
      value = '\u2014';
    } else if (meta.domain && meta.domain[String(raw)] !== undefined) {
      value = meta.domain[String(raw)] + ' (' + raw + ')';
    } else {
      value = raw;
    }
    return { label: meta.alias || name, value: value };
  });
}

function identifyBlockHtml(title, rows) {
  let html = '<div class="gp-id-head"><span>' + escapeHtml(title) + '</span>' +
    '<button type="button" class="gp-id-close" aria-label="Close">&times;</button></div><table>';
  rows.forEach(function (row) {
    html += '<tr><th>' + escapeHtml(row.label) + '</th><td>' + escapeHtml(row.value) + '</td></tr>';
  });
  return html + '</table>';
}

// A COG layer is an ol/layer/WebGLTile; `getData(pixel)` reads the band value(s)
// the renderer decoded for that pixel (client-side, no server round-trip). It is
// null until the tile under the click is loaded.
function identifyRasterBlock(layer, pixel) {
  let data;
  try { data = layer.getData(pixel); } catch (e) { data = null; }
  if (data === null || data === undefined) return null;
  const bands = layer.get('gpRasterBands') || [];
  const values = Array.isArray(data) ? data : [data];
  const rows = values.map(function (value, i) {
    const meta = bands[i] || {};
    const noData = meta.noDataValue;
    let shown = value;
    if (value === null || value === undefined ||
        (noData !== undefined && noData !== null && Number(value) === Number(noData))) {
      shown = '\u2014 (no data)';
    } else if (typeof value === 'number' && isFinite(value)) {
      shown = Math.round(value * 1000) / 1000;
    }
    const label = meta.label ||
      (values.length === 1 ? 'Value' : 'Band ' + (meta.band || (i + 1)));
    return { label: label, value: shown };
  });
  return identifyBlockHtml(layer.get('title') || 'Raster', rows);
}

// A WMS/WMTS image layer is identified server-side with a GetFeatureInfo request
// (its features are not in the browser). The publication's queryable layer name
// travels in the manifest as `identifyWmsLayers`; the request is WMS 1.1.1 with
// SRS=EPSG:4326 (lon,lat) so the box is unambiguous across GeoServer versions.
function wmsFeatureInfoUrl(wmsUrl, coord, map, layers) {
  const view = map.getView();
  const size = map.getSize();
  const box = ol.proj.transformExtent(
    view.calculateExtent(size), view.getProjection(), 'EPSG:4326');
  const lonlat = ol.proj.toLonLat(coord);
  const width = size[0], height = size[1];
  const spanX = box[2] - box[0], spanY = box[3] - box[1];
  const x = Math.round((lonlat[0] - box[0]) / spanX * width);
  const y = Math.round((box[3] - lonlat[1]) / spanY * height);
  const params = {
    SERVICE: 'WMS', VERSION: '1.1.1', REQUEST: 'GetFeatureInfo',
    LAYERS: layers, QUERY_LAYERS: layers, STYLES: '',
    SRS: 'EPSG:4326', BBOX: box.join(','),
    WIDTH: String(width), HEIGHT: String(height),
    X: String(x), Y: String(y),
    INFO_FORMAT: 'application/json', FEATURE_COUNT: '10'
  };
  const query = Object.keys(params).map(function (key) {
    return encodeURIComponent(key) + '=' + encodeURIComponent(params[key]);
  }).join('&');
  // `withToken` always yields a `?...t=` query, so extend with `&` (a second `?`
  // would truncate the token and the service answers "missing or invalid token").
  return withToken(wmsUrl) + '&' + query;
}

function setupIdentify(map, dataLayers) {
  const popup = document.getElementById('identify');
  if (!popup || TEMPLATE.identify === false) return;
  const vectorLayers = dataLayers.filter(function (layer) {
    return !isRasterRender(layer.get('gpRender'));
  });
  const imageLayers = dataLayers.filter(function (layer) {
    const render = layer.get('gpRender');
    return (render === 'wms' || render === 'wmts') && layer.get('gpIdentifyLayers');
  });
  const rasterLayers = dataLayers.filter(function (layer) {
    return layer.get('gpRender') === 'cog';
  });
  if (!vectorLayers.length && !imageLayers.length && !rasterLayers.length) return;

  function hide() { popup.style.display = 'none'; popup.innerHTML = ''; }
  popup.addEventListener('click', function (evt) {
    const target = evt.target;
    if (target && target.classList && target.classList.contains('gp-id-close')) hide();
  });

  function show(blocks, pixel) {
    if (!blocks.length) { hide(); return; }
    popup.innerHTML = blocks.join('');
    popup.style.display = 'block';
    const size = map.getSize() || [0, 0];
    const left = Math.min(Math.max(8, pixel[0] + 10), Math.max(8, size[0] - 340));
    const top = Math.min(Math.max(8, pixel[1] + 10), Math.max(8, size[1] - 80));
    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
  }

  map.on('singleclick', async function (evt) {
    const blocks = [];
    const vectorHits = [];
    map.forEachFeatureAtPixel(evt.pixel, function (feature, layer) {
      if (vectorHits.indexOf(feature) === -1) vectorHits.push({ feature: feature, layer: layer });
    }, {
      hitTolerance: 4,
      layerFilter: function (layer) { return vectorLayers.indexOf(layer) !== -1; }
    });
    vectorHits.slice(0, 25).forEach(function (hit) {
      blocks.push(identifyBlockHtml(hit.layer.get('title') || 'Feature',
        rowsFromProps(hit.feature.getProperties(), hit.layer)));
    });

    // Raster (COG) layers: read the pixel value the renderer already decoded.
    rasterLayers.forEach(function (layer) {
      if (!layer.getVisible()) return;
      const block = identifyRasterBlock(layer, evt.pixel);
      if (block) blocks.push(block);
    });

    // Image layers: ask the server what is under the click (GetFeatureInfo).
    const visible = imageLayers.filter(function (layer) { return layer.getVisible(); });
    if (visible.length) {
      const coord = map.getCoordinateFromPixel(evt.pixel);
      const found = await Promise.all(visible.map(function (layer) {
        const layers = layer.get('gpIdentifyLayers');
        const url = wmsFeatureInfoUrl(layer.get('gpWmsUrl'), coord, map, layers);
        return fetch(url).then(function (response) {
          return response.ok ? response.json() : null;
        }).then(function (geo) {
          return ((geo && geo.features) || []).map(function (feature) {
            return identifyBlockHtml(layer.get('title') || 'Feature',
              rowsFromProps(feature.properties || {}, layer));
          });
        }).catch(function () { return []; });
      }));
      found.forEach(function (list) {
        list.slice(0, Math.max(0, 25 - blocks.length)).forEach(function (block) {
          blocks.push(block);
        });
      });
    }
    show(blocks, evt.pixel);
  });
}

// A bbox is [west, south, east, north] in EPSG:4326. Reject anything that is not
// a plausible lon/lat box (e.g. a projected native-CRS extent in metres, or a
// [lat, lon, ...] mix-up) so auto-fit never zooms to the wrong continent.
function validWgs84BBox(b) {
  if (!Array.isArray(b) || b.length !== 4) return null;
  if (!b.every(function (v) { return typeof v === 'number' && isFinite(v); })) return null;
  const w = b[0], s = b[1], e = b[2], n = b[3];
  if (Math.abs(w) > 180 || Math.abs(e) > 180 || Math.abs(s) > 90 || Math.abs(n) > 90) return null;
  if (w >= e || s >= n) return null;
  return [w, s, e, n];
}

async function main() {
  if (!TOKEN) banner('No access token in the URL. Open the exact viewerUrl returned by show_map ' +
    '(it carries ?t=...); if a linker dropped it, re-open the full URL.');
  let manifest;
  let manifestStatus = 0;
  try {
    const response = await fetch(withToken(MANIFEST_URL));
    manifestStatus = response.status;
    if (!response.ok) throw new Error('manifest HTTP ' + response.status);
    manifest = await response.json();
  } catch (err) {
    // A 401/403 means the link's token is stale/foreign (the token travels in the
    // fragment, so the server could not refuse the shell). Say so explicitly
    // instead of a blank canvas (issue report 2026-11-24, N6).
    if (manifestStatus === 401 || manifestStatus === 403) {
      banner('This map link has expired — the local map service issues a new token each run. ' +
        'Re-run show_map and open the fresh viewerUrl.');
    } else {
      banner('Could not load the map manifest: ' + err.message);
    }
    return;
  }

  const baseLayers = [];
  (TEMPLATE.basemaps || []).forEach(function (entry) {
    const layer = basemapLayer(entry);
    if (layer) { layer.setVisible(entry.id === (TEMPLATE.basemap || '')); baseLayers.push(layer); }
  });

  const startCenter = VIEW_OVERRIDE.center ||
    (TEMPLATE.view && TEMPLATE.view.center) || [0, 0];
  const startZoom = (VIEW_OVERRIDE.zoom != null)
    ? VIEW_OVERRIDE.zoom
    : ((TEMPLATE.view && TEMPLATE.view.zoom) || 2);
  const map = new ol.Map({
    target: 'map',
    layers: baseLayers,
    view: new ol.View({
      center: ol.proj.fromLonLat(startCenter),
      zoom: startZoom
    })
  });
  if (TEMPLATE.scale !== false) { map.addControl(new ol.control.ScaleLine()); }
  if (TEMPLATE.attribution === false) {
    map.getControls().forEach(function (c) {
      if (c instanceof ol.control.Attribution) { map.removeControl(c); }
    });
  }

  // Status bar: live WGS84 coordinates under the pointer (room for future tools
  // such as a measure readout; the container exists in the page shell).
  const statusbar = document.getElementById('statusbar');
  if (statusbar) {
    map.on('pointermove', function (evt) {
      if (evt.dragging) return;
      const lonlat = ol.proj.toLonLat(evt.coordinate);
      statusbar.textContent = 'Lon ' + lonlat[0].toFixed(5) + '   Lat ' + lonlat[1].toFixed(5);
    });
    map.getTargetElement().addEventListener('mouseleave', function () {
      statusbar.textContent = '';
    });
  }

  const extent = ol.extent.createEmpty();
  const dataLayers = [];
  for (const spec of (manifest.layers || [])) {
    const index = dataLayers.length;
    let layer;
    try {
      if ((spec.render || '') === 'wfs' || (spec.kind === 'portal-publication' && spec.render === 'wfs')) {
        layer = await wfsLayer(spec, index);
      } else {
        layer = buildLayer(spec, index);
      }
    } catch (err) {
      banner('Layer "' + (spec.title || spec.id) + '" failed: ' + err.message);
      continue;
    }
    map.addLayer(layer);
    dataLayers.push(layer);
    const box = validWgs84BBox(spec.bbox);
    if (box) {
      ol.extent.extend(extent, ol.proj.transformExtent(box, 'EPSG:4326', 'EPSG:3857'));
    }
  }

  if (TEMPLATE.view && TEMPLATE.view.mode === 'fit' && !VIEW_OVERRIDE_ACTIVE &&
      !ol.extent.isEmpty(extent)) {
    map.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 17 });
  }
  renderPanel(map, baseLayers, dataLayers);
  setupIdentify(map, dataLayers);
  // GeoJSON layers stream AFTER the panel exists so their legend shows progress.
  loadPendingVectors(map, dataLayers);
}

main();
