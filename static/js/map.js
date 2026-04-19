/**
 * MapLibre GL JS map with animated reveal sequence.
 *
 * Sequence: user location -> power plant -> source mine.
 * Arc line drawn between all three points. Total time <= 8 seconds.
 *
 * Flow animation: static dasharray with linearly advancing dashoffset —
 * steady conveyor-belt feel. Two layers (glow + dashes), one pulse circle.
 * All layers are native MapLibre WebGL — they pan/zoom with the map.
 */

// Satellite basemap via ESRI World Imagery (public access, no API key required).
// Inline style spec feeds raster XYZ tiles into MapLibre's vector engine.
const SATELLITE_STYLE = {
  version: 8,
  sources: {
    esri: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Esri, Maxar, Earthstar Geographics",
      maxzoom: 18,
    },
  },
  layers: [{ id: "esri-satellite", type: "raster", source: "esri" }],
};

const STEP_DURATION_MS = 1700;
const PAUSE_BETWEEN_MS = 200;
const MAP_LOAD_TIMEOUT_MS = 15000;

// Dash pattern: 4 units on, 3 units off = 7-unit repeat.
const DASH_LEN = 4;
const GAP_LEN = 3;

// Flow speed in dasharray units per second.
// 9 units/sec → one full 7-unit cycle every ~0.78s — steady conveyor pace.
const FLOW_SPEED = 9;

/**
 * Initialize a MapLibre GL map in the given container.
 * @param {string|HTMLElement} container - Container element or ID
 * @returns {maplibregl.Map}
 */
export function createMap(container) {
  return new maplibregl.Map({
    container,
    style: SATELLITE_STYLE,
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
    border: 2px solid #ffffff;
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
 * Add a single pulsing WebGL circle at the mine endpoint.
 * One ring, slow sine breath — steady pressure at the source.
 * @param {maplibregl.Map} map
 * @param {[number,number]} mineLonLat
 */
function addMinePulse(map, mineLonLat) {
  const sourceId = "mine-pulse";
  if (map.getSource(sourceId)) {
    map.removeLayer("mine-pulse");
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
    id: "mine-pulse",
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": 14,
      "circle-color": "#ffb347",
      "circle-opacity": 0.15,
      "circle-blur": 0.6,
    },
  });
}

/**
 * Draw the extraction flow and start the animation loop.
 *
 * Layers (mine → plant direction):
 *   user-arc    — dim static dotted line: user → plant (contextual)
 *   flow-glow   — wide blurred amber backing: mine → plant (heat haze)
 *   flow-dashes — animated amber dashes: mine → plant (the extraction flow)
 *   mine-pulse  — single slow-breathing circle at the mine
 *
 * Dash animation: static dasharray [4, 3] with linearly advancing dashoffset.
 * One property updated per frame — frame-rate-independent, no branch switching.
 * Pulse: single sine wave at ~3.5s period — slow, ponderous, relentless.
 *
 * @param {maplibregl.Map} map
 * @param {[number,number]} userLonLat
 * @param {[number,number]} plantLonLat
 * @param {[number,number]} mineLonLat
 * @returns {function} stop — cancel the animation loop before calling map.remove()
 */
function addFlowLine(map, userLonLat, plantLonLat, mineLonLat) {
  const arc = buildArc(mineLonLat, plantLonLat, 60);

  // User → plant: contextual connection (you are downstream of this plant)
  addLineLayer(map, "user-arc", buildArc(userLonLat, plantLonLat, 30), {
    "line-color": "#ffffff",
    "line-width": 1.5,
    "line-opacity": 0.35,
    "line-dasharray": [2, 5],
  });

  // Mine → plant: wide blurred backing — heat haze of the extraction corridor
  addLineLayer(map, "flow-glow", arc, {
    "line-color": "#c4956a",
    "line-width": 12,
    "line-opacity": 0.4,
    "line-blur": 6,
  });

  // Mine → plant: amber dashes, static pattern, offset-animated
  addLineLayer(map, "flow-dashes", arc, {
    "line-color": "#ffb347",
    "line-width": 3.5,
    "line-opacity": 1,
    "line-dasharray": [DASH_LEN, GAP_LEN],
  });

  // Mine: single slow-breathing circle
  addMinePulse(map, mineLonLat);

  // --- Animation loop ---
  let rafId = null;
  let stopped = false;
  let startTime = null;

  function animate(timestamp) {
    if (stopped) return;
    rafId = requestAnimationFrame(animate);

    if (startTime === null) startTime = timestamp;
    const elapsed = (timestamp - startTime) / 1000; // seconds

    try {
      // Dashes: linearly advancing offset — steady conveyor belt, no branching
      map.setPaintProperty("flow-dashes", "line-dashoffset", elapsed * FLOW_SPEED);

      // Pulse: single slow sine breath (~3.5s period)
      const phase = elapsed * ((Math.PI * 2) / 3.5);
      const r = 12 + 8 * Math.abs(Math.sin(phase));
      const a = 0.1 + 0.2 * Math.abs(Math.sin(phase));
      map.setPaintProperty("mine-pulse", "circle-radius", r);
      map.setPaintProperty("mine-pulse", "circle-opacity", a);
    } catch {
      // Map removed before stop() was called — cancel the animation loop.
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
