/**
 * MapLibre GL JS map with animated reveal sequence.
 *
 * Sequence: user location -> power plant -> source mine.
 * Arc line drawn between all three points. Total time <= 8 seconds.
 *
 * Flow animation: animated dasharray cycling (MapLibre native) for the mine→plant
 * segment, conveying directional resource extraction. Runs at ~18fps to stay
 * well under budget when combined with the PixiJS coal-dust overlay.
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

// Dasharray animation sequence — 14 frames, 7-unit pattern (4 dash + 3 gap).
// Each frame advances 0.5 units. Line direction is mine → plant, so dashes
// appear to travel from the extraction source toward the receiving plant.
// Derived from MapLibre's animate-a-line pattern.
const DASH_SEQUENCE = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 3.5, 3.5],
  [0.5, 3.5, 3],
  [1, 3.5, 2.5],
  [1.5, 3.5, 2],
  [2, 3.5, 1.5],
  [2.5, 3.5, 1],
  [3, 3.5, 0.5],
];

// ~18fps for dash updates — imperceptibly smooth, cheaper than 60fps
const DASH_UPDATE_INTERVAL_MS = 55;

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
 * Add a pulsing glow circle at the mine (source end of the extraction flow).
 * The inner marker pin is a DOM element on top; this provides the WebGL halo.
 * @param {maplibregl.Map} map
 * @param {[number,number]} mineLonLat
 */
function addSourcePulse(map, mineLonLat) {
  const sourceId = "mine-pulse";
  if (map.getSource(sourceId)) {
    map.removeLayer("mine-pulse-outer");
    map.removeSource(sourceId);
  }
  map.addSource(sourceId, {
    type: "geojson",
    data: {
      type: "Feature",
      geometry: { type: "Point", coordinates: mineLonLat },
    },
  });
  map.addLayer({
    id: "mine-pulse-outer",
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": 11,
      "circle-color": "#c4956a",
      "circle-opacity": 0.1,
      "circle-blur": 0.6,
    },
  });
}

/**
 * Draw the full visual chain and start the animation loop.
 *
 * Layers added:
 *   user-arc     — static dim dotted line: user → plant (contextual)
 *   flow-trail   — static dark blur base: mine → plant (glow backing)
 *   flow-dashes  — animated amber dashes: mine → plant (the extraction flow)
 *   mine-pulse   — pulsing WebGL circle: mine endpoint (source glow)
 *
 * Flow direction: mine → plant. Coal is extracted at the mine and shipped
 * to the plant. The dash animation advances from the mine end toward the plant,
 * making the direction viscerally clear.
 *
 * @param {maplibregl.Map} map
 * @param {[number,number]} userLonLat
 * @param {[number,number]} plantLonLat
 * @param {[number,number]} mineLonLat
 * @returns {function} stop — cancel the animation loop before calling map.remove()
 */
function addFlowLine(map, userLonLat, plantLonLat, mineLonLat) {
  // User → plant: dim contextual connection (you are downstream of this plant)
  addLineLayer(map, "user-arc", buildArc(userLonLat, plantLonLat, 30), {
    "line-color": "#3a3a3a",
    "line-width": 1,
    "line-opacity": 0.3,
    "line-dasharray": [2, 5],
  });

  // Mine → plant: dark glow backing (makes the amber dashes pop)
  addLineLayer(map, "flow-trail", buildArc(mineLonLat, plantLonLat, 50), {
    "line-color": "#1a0d05",
    "line-width": 5,
    "line-opacity": 0.55,
    "line-blur": 3,
  });

  // Mine → plant: the animated extraction flow
  addLineLayer(map, "flow-dashes", buildArc(mineLonLat, plantLonLat, 50), {
    "line-color": "#c4956a",
    "line-width": 2,
    "line-opacity": 0.9,
    "line-dasharray": DASH_SEQUENCE[0],
  });

  // Mine pulse glow (behind the DOM marker pin)
  addSourcePulse(map, mineLonLat);

  // --- Animation loop ---
  let step = 0;
  let pulsePhase = 0;
  let rafId = null;
  let stopped = false;
  let lastUpdate = 0;

  function animate(timestamp) {
    if (stopped) return;
    rafId = requestAnimationFrame(animate);

    if (timestamp - lastUpdate < DASH_UPDATE_INTERVAL_MS) return;
    lastUpdate = timestamp;

    try {
      step = (step + 1) % DASH_SEQUENCE.length;
      map.setPaintProperty("flow-dashes", "line-dasharray", DASH_SEQUENCE[step]);

      // Pulse: slower sine on radius and opacity for heavy, relentless feel
      pulsePhase += 0.15;
      const r = 11 + 9 * Math.sin(pulsePhase);
      const a = 0.07 + 0.11 * Math.abs(Math.sin(pulsePhase));
      map.setPaintProperty("mine-pulse-outer", "circle-radius", r);
      map.setPaintProperty("mine-pulse-outer", "circle-opacity", a);
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
