/**
 * MapLibre GL JS map with animated reveal sequence.
 *
 * Sequence: user location -> power plant -> source mine.
 * Arc line drawn between all three points. Total time <= 8 seconds.
 */

const MAPTILER_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const STEP_DURATION_MS = 2200;
const PAUSE_BETWEEN_MS = 400;
const MAP_LOAD_TIMEOUT_MS = 15000;

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

    function startSequence() {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutId);

      addMarker(map, userLonLat, "You", "#c4956a");
      showCaption(captionEl, "Your location");

      // Step 1: Fly to user location
      map.flyTo({ center: userLonLat, zoom: 8, duration: STEP_DURATION_MS });

      setTimeout(() => {
        // Step 2: Add plant marker and fly there
        addMarker(map, plantLonLat, plantName, "#8aaa8a");
        showCaption(captionEl, plantName);
        map.flyTo({ center: plantLonLat, zoom: 8, duration: STEP_DURATION_MS });

        setTimeout(() => {
          // Step 3: Add mine marker and fly there
          addMarker(map, mineLonLat, mineName, "#d4d0c8");
          showCaption(captionEl, mineName);
          map.flyTo({ center: mineLonLat, zoom: 8, duration: STEP_DURATION_MS });

          setTimeout(() => {
            // Step 4: Draw arc and zoom out to show all three
            addArcLine(map, [userLonLat, plantLonLat, mineLonLat]);
            showCaption(captionEl, "");

            const bounds = new maplibregl.LngLatBounds();
            bounds.extend(userLonLat);
            bounds.extend(plantLonLat);
            bounds.extend(mineLonLat);

            map.fitBounds(bounds, {
              padding: { top: 60, bottom: 60, left: 40, right: 40 },
              duration: STEP_DURATION_MS,
            });

            setTimeout(resolve, STEP_DURATION_MS + PAUSE_BETWEEN_MS);
          }, STEP_DURATION_MS + PAUSE_BETWEEN_MS);
        }, STEP_DURATION_MS + PAUSE_BETWEEN_MS);
      }, STEP_DURATION_MS + PAUSE_BETWEEN_MS);
    }

    if (map.loaded()) {
      startSequence();
    } else {
      map.once("load", startSequence);
    }
  });
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
      new maplibregl.Popup({ offset: 12, closeButton: false }).setText(label),
    )
    .addTo(map)
    .togglePopup();
}

/**
 * Draw an arc line connecting multiple points.
 * Generates curved segments by interpolating intermediate points
 * with a slight latitude offset for visual curvature.
 * @param {maplibregl.Map} map
 * @param {Array<[number, number]>} points - Array of [lon, lat] pairs
 */
function addArcLine(map, points) {
  const arcCoords = [];
  for (let p = 0; p < points.length - 1; p++) {
    const start = points[p];
    const end = points[p + 1];
    const segments = 50;
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      const lon = start[0] + (end[0] - start[0]) * t;
      const lat = start[1] + (end[1] - start[1]) * t;
      // Arc offset: sine curve peaks at midpoint
      const arcHeight =
        Math.sin(t * Math.PI) *
        Math.abs(end[0] - start[0]) *
        0.15;
      arcCoords.push([lon, lat + arcHeight]);
    }
  }

  const sourceId = "arc-line";
  if (map.getSource(sourceId)) {
    map.removeLayer(sourceId);
    map.removeSource(sourceId);
  }

  map.addSource(sourceId, {
    type: "geojson",
    data: {
      type: "Feature",
      geometry: { type: "LineString", coordinates: arcCoords },
    },
  });

  map.addLayer({
    id: sourceId,
    type: "line",
    source: sourceId,
    paint: {
      "line-color": "#c4956a",
      "line-width": 2,
      "line-opacity": 0.7,
      "line-dasharray": [4, 3],
    },
  });
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
