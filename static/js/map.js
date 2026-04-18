/**
 * MapLibre GL JS map with animated reveal sequence.
 *
 * Sequence: user location -> power plant -> source mine.
 * Arc line drawn between all three points. Total time <= 8 seconds.
 *
 * Flow animation: continuous dash-offset cycling (timestamp-driven, 60fps)
 * with multi-layer glow stack for a visceral extraction feel.
 * All layers are native MapLibre WebGL — they pan/zoom with the map.
 */

// Basemap style evaluation — considered green topology alternatives:
// - Stamen Terrain / Stadia Maps: requires paid API key as of 2024 (Stadia acquired Stamen tiles)
// - OpenTopoMap: free XYZ raster tiles only; no vector style JSON; classic paper-toned look
//   incompatible with this dark aesthetic; loses crisp vector zoom; can't be used as MapLibre style
// - MapTiler terrain/outdoor styles: all require paid API key
// Verdict: no suitable free green topology MapLibre style without paid access.
// Keeping Carto dark-matter for aesthetic coherence with the coal/mining theme.
const MAPTILER_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const STEP_DURATION_MS = 1700;
const PAUSE_BETWEEN_MS = 200;
const MAP_LOAD_TIMEOUT_MS = 15000;

// Dash pattern: 4 units on, 3 units off = 7-unit repeat.
// The animation advances the phase continuously using wall-clock time so
// speed is frame-rate-independent and perfectly smooth at 60fps.
const DASH_LEN = 4;
const GAP_LEN = 3;
const PATTERN_LEN = DASH_LEN + GAP_LEN; // 7
// Full pattern cycle duration: chosen to match the previous visual speed.
// Previous: 14 frames × 55ms = 770ms per cycle ≈ 9.09 units/sec.
const DASH_CYCLE_MS = 770;

/**
 * Compute a MapLibre line-dasharray triplet from a continuous time offset.
 * The returned array creates the illusion of dashes flowing from mine → plant.
 *
 * MapLibre dasharray format: [segment0, segment1, segment2, ...]
 * where the segments alternate dash/gap starting with dash.
 * We use a 3-element array to represent one full DASH+GAP cycle split at
 * an arbitrary phase, giving sub-frame visual smoothness.
 *
 * @param {number} timeMs - Wall-clock milliseconds
 * @returns {[number, number, number]}
 */
function dashArrayAtTime(timeMs) {
  const phase = ((timeMs % DASH_CYCLE_MS) / DASH_CYCLE_MS) * PATTERN_LEN;

  if (phase < GAP_LEN) {
    // Phase is inside the gap region: leading gap fragment, full dash, trailing gap fragment
    return [phase, DASH_LEN, GAP_LEN - phase];
  } else {
    // Phase is inside the dash region: leading dash fragment, full gap, trailing dash fragment
    const inDash = phase - GAP_LEN;
    return [GAP_LEN + inDash, GAP_LEN, DASH_LEN - inDash];
  }
}

/**
 * Initialize a MapLibre GL map in the given container.
 * @param {string|HTMLElement} container - Container element or ID
 * @returns {maplibregl.Map}
 */
export function createMap(container) {
  return new maplibregl.Map({
    container,
    style: MAPTILER_STYLE,
    center: [-98.5, 39.8], // Center of US
    zoom: 3.5,
    attributionControl: false,
  });
}

/**
 * Run the cinematic reveal sequence: user -> plant -> mine.
 * Rejects if the map doesn't load within MAP_LOAD_TIMEOUT_MS.
 *
 * Attaches a stop function to map._stopFlowAnimation — call before map.remove().
 *
 * @param {maplibregl.Map} map
 * @param {Object} params
 * @param {[number, number]} params.userCoords - [lat, lon]
 * @param {[number, number]} params.plantCoords - [lat, lon]
 * @param {[number, number]} params.mineCoords - [lat, lon]
 * @param {string} params.plantName
 * @param {string} params.mineName
 * @param {HTMLElement} params.captionEl - Element for captions
 * @returns {Promise<void>} Resolves when sequence is complete
 */
export function runRevealSequence(map, params) {
  const { userCoords, plantCoords, mineCoords, plantName, mineName, captionEl } =
    params;

  // MapLibre uses [lon, lat] order
  const userLonLat = [userCoords[1], userCoords[0]];
  const plantLonLat = [plantCoords[1], plantCoords[0]];
  const mineLonLat = [mineCoords[1], mineCoords[0]];

  return new Promise((resolve, reject) => {
    let settled = false;

    const timeoutId = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error("Map failed to load. Please check your network connection."));
      }
    }, MAP_LOAD_TIMEOUT_MS);

    async function startSequence() {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutId);

      const stepDelay = STEP_DURATION_MS + PAUSE_BETWEEN_MS;

      // Step 1: Fly to user location
      addMarker(map, userLonLat, "You", "#c4956a");
      showCaption(captionEl, "Your location");
      map.flyTo({ center: userLonLat, zoom: 8, duration: STEP_DURATION_MS });
      await delay(stepDelay);

      // Step 2: Fly to power plant
      addMarker(map, plantLonLat, plantName, "#8aaa8a");
      showCaption(captionEl, plantName);
      map.flyTo({ center: plantLonLat, zoom: 8, duration: STEP_DURATION_MS });
      await delay(stepDelay);

      // Step 3: Fly to source mine
      addMarker(map, mineLonLat, mineName, "#d4d0c8");
      showCaption(captionEl, mineName);
      map.flyTo({ center: mineLonLat, zoom: 8, duration: STEP_DURATION_MS });
      await delay(stepDelay);

      // Step 4: Draw animated flow lines and zoom out to show all three
      const stopFlow = addFlowLine(map, userLonLat, plantLonLat, mineLonLat);
      map._stopFlowAnimation = stopFlow;

      showCaption(captionEl, "");

      const bounds = new maplibregl.LngLatBounds();
      bounds.extend(userLonLat);
      bounds.extend(plantLonLat);
      bounds.extend(mineLonLat);

      map.fitBounds(bounds, {
        padding: { top: 60, bottom: 60, left: 60, right: 60 },
        duration: STEP_DURATION_MS,
      });

      await delay(stepDelay);
      resolve();
    }

    if (map.loaded()) {
      startSequence();
    } else {
      map.once("load", startSequence);
    }
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Add a labeled marker to the map.
 * @param {maplibregl.Map} map
 * @param {[number, number]} lonLat
 * @param {string} label
 * @param {string} color - CSS color
 */
function addMarker(map, lonLat, label, color) {
  const el = document.createElement("div");
  el.className = "map-marker";
  el.style.cssText = `
    width: 14px; height: 14px;
    background: ${color};
    border: 2px solid #0a0a0a;
    border-radius: 50%;
    box-shadow: 0 0 8px ${color}80;
  `;

  new maplibregl.Marker({ element: el })
    .setLngLat(lonLat)
    .setPopup(
      new maplibregl.Popup({ offset: 12, closeButton: false, closeOnClick: false }).setText(label),
    )
    .addTo(map)
    .togglePopup();
}

/**
 * Generate arc coordinates between two points with a sine-curve bulge.
 * @param {[number,number]} from - [lon, lat]
 * @param {[number,number]} to   - [lon, lat]
 * @param {number} segments
 * @returns {Array<[number,number]>}
 */
function buildArc(from, to, segments) {
  const coords = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const lon = from[0] + (to[0] - from[0]) * t;
    const lat = from[1] + (to[1] - from[1]) * t;
    const arcHeight = Math.sin(t * Math.PI) * Math.abs(to[0] - from[0]) * 0.15;
    coords.push([lon, lat + arcHeight]);
  }
  return coords;
}

/**
 * Add a GeoJSON line source + layer pair to the map.
 * Removes any existing source/layer with the same id first.
 * @param {maplibregl.Map} map
 * @param {string} id
 * @param {Array<[number,number]>} coordinates
 * @param {Object} paint - MapLibre paint properties
 */
function addLineLayer(map, id, coordinates, paint) {
  if (map.getSource(id)) {
    map.removeLayer(id);
    map.removeSource(id);
  }
  map.addSource(id, {
    type: "geojson",
    data: {
      type: "Feature",
      geometry: { type: "LineString", coordinates },
    },
  });
  map.addLayer({ id, type: "line", source: id, paint });
}

/**
 * Add pulsing WebGL circles at the mine endpoint — the extraction source.
 * Two rings: a slow outer breath and a faster inner beat.
 * @param {maplibregl.Map} map
 * @param {[number,number]} mineLonLat
 */
function addSourcePulse(map, mineLonLat) {
  const sourceId = "mine-pulse";
  if (map.getSource(sourceId)) {
    map.removeLayer("mine-pulse-outer");
    map.removeLayer("mine-pulse-inner");
    map.removeSource(sourceId);
  }
  map.addSource(sourceId, {
    type: "geojson",
    data: {
      type: "Feature",
      geometry: { type: "Point", coordinates: mineLonLat },
    },
  });
  // Outer halo: slow, wide, earthy amber — the raw pressure of extraction
  map.addLayer({
    id: "mine-pulse-outer",
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": 18,
      "circle-color": "#7a3d10",
      "circle-opacity": 0.08,
      "circle-blur": 0.7,
    },
  });
  // Inner ring: faster beat, slightly brighter — heartbeat at the source
  map.addLayer({
    id: "mine-pulse-inner",
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": 10,
      "circle-color": "#c4956a",
      "circle-opacity": 0.15,
      "circle-blur": 0.4,
    },
  });
}

/**
 * Draw the full visual chain and start the animation loop.
 *
 * Layers (mine → plant direction):
 *   user-arc        — dim static dotted line: user → plant (contextual)
 *   flow-glow-outer — wide heat-haze backing: mine → plant (deep shadow glow)
 *   flow-glow-inner — medium amber haze: mine → plant (glow mid-tone)
 *   flow-dashes     — animated amber dashes: mine → plant (the extraction flow)
 *   mine-pulse-outer — slow, wide WebGL halo at the mine (raw extraction pressure)
 *   mine-pulse-inner — fast WebGL ring at the mine (heartbeat at the source)
 *
 * Animation runs at full rAF rate (60fps). Dash phase is driven by wall-clock
 * time so speed is frame-rate-independent. Pulse rings update every frame for
 * smooth sine interpolation.
 *
 * @param {maplibregl.Map} map
 * @param {[number,number]} userLonLat
 * @param {[number,number]} plantLonLat
 * @param {[number,number]} mineLonLat
 * @returns {function} stop — cancel the animation loop before calling map.remove()
 */
function addFlowLine(map, userLonLat, plantLonLat, mineLonLat) {
  const arc = buildArc(mineLonLat, plantLonLat, 60);

  // User → plant: dim contextual connection (you are downstream of this plant)
  addLineLayer(map, "user-arc", buildArc(userLonLat, plantLonLat, 30), {
    "line-color": "#3a3a3a",
    "line-width": 1,
    "line-opacity": 0.3,
    "line-dasharray": [2, 5],
  });

  // Mine → plant: deep shadow layer — makes the whole corridor feel heavy
  addLineLayer(map, "flow-glow-outer", arc, {
    "line-color": "#1a0800",
    "line-width": 16,
    "line-opacity": 0.45,
    "line-blur": 10,
  });

  // Mine → plant: amber haze mid-layer — the heat of extraction
  addLineLayer(map, "flow-glow-inner", arc, {
    "line-color": "#5c2d0a",
    "line-width": 6,
    "line-opacity": 0.55,
    "line-blur": 3,
  });

  // Mine → plant: the animated extraction flow — continuous, relentless
  addLineLayer(map, "flow-dashes", arc, {
    "line-color": "#c4956a",
    "line-width": 3,
    "line-opacity": 1.0,
    "line-dasharray": dashArrayAtTime(0),
  });

  // Mine pulse rings (behind the DOM marker pin)
  addSourcePulse(map, mineLonLat);

  // --- Animation loop (60fps, timestamp-driven) ---
  let rafId = null;
  let stopped = false;
  // Track last rendered dasharray to skip setPaintProperty when unchanged.
  // Dashes update ~13× per second (770ms cycle / 7 notional frames).
  let lastDashKey = "";

  function animate(timestamp) {
    if (stopped) return;
    rafId = requestAnimationFrame(animate);

    try {
      // Dashes: computed from wall clock — smooth, consistent speed at any framerate
      const dashArray = dashArrayAtTime(timestamp);
      const dashKey = dashArray.join(",");
      if (dashKey !== lastDashKey) {
        lastDashKey = dashKey;
        map.setPaintProperty("flow-dashes", "line-dasharray", dashArray);
      }

      // Outer halo: slow, ponderous breath (period ~4s)
      const outerPhase = timestamp * 0.0016;
      const outerR = 16 + 14 * Math.sin(outerPhase);
      const outerA = 0.05 + 0.10 * Math.abs(Math.sin(outerPhase));
      map.setPaintProperty("mine-pulse-outer", "circle-radius", outerR);
      map.setPaintProperty("mine-pulse-outer", "circle-opacity", outerA);

      // Inner ring: faster beat (period ~1.8s) — feels like a pulse under pressure
      const innerPhase = timestamp * 0.0035;
      const innerR = 7 + 8 * Math.abs(Math.sin(innerPhase));
      const innerA = 0.12 + 0.18 * (1 - Math.abs(Math.sin(innerPhase)));
      map.setPaintProperty("mine-pulse-inner", "circle-radius", innerR);
      map.setPaintProperty("mine-pulse-inner", "circle-opacity", innerA);
    } catch (_) {
      // Map was removed — stop silently
      stopped = true;
    }
  }

  rafId = requestAnimationFrame(animate);

  return function stop() {
    stopped = true;
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  };
}

/**
 * Show or hide a caption on the map.
 * @param {HTMLElement} el
 * @param {string} text
 */
function showCaption(el, text) {
  if (text) {
    el.textContent = text;
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}
