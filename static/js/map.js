/**
 * Google Maps with cinematic reveal sequence.
 *
 * Sequence:
 *   1. Zoom to user address, hold 2-3 seconds
 *   2. Zoom out to show the power plant, draw line user→plant
 *   3. Follow the path from plant to mine, draw line plant→mine
 *   4. Zoom in tight on the mine so you can see it in satellite
 *
 * Flow animation: animated dashed polyline mine → plant → user
 * using SVG symbol offset animation.
 */

const MAP_LOAD_TIMEOUT_MS = 15000;

// Timing (ms)
const FLY_DURATION = 2000;
const HOLD_DURATION = 2500;
const FLOW_ANIM_INTERVAL = 40;

/**
 * Initialize a Google Map in the given container.
 * @param {HTMLElement} container
 * @returns {google.maps.Map}
 */
export function createMap(container) {
  return new google.maps.Map(container, {
    center: { lat: 39.8, lng: -98.5 },
    zoom: 4,
    mapTypeId: "hybrid",
    disableDefaultUI: true,
    zoomControl: true,
    gestureHandling: "greedy",
  });
}

/**
 * Run the cinematic reveal sequence.
 *
 * @param {google.maps.Map} map
 * @param {Object} params
 * @param {[number, number]} params.userCoords - [lat, lon]
 * @param {[number, number]} params.plantCoords - [lat, lon]
 * @param {[number, number]} params.mineCoords - [lat, lon]
 * @param {string} params.plantName
 * @param {string} params.mineName
 * @param {HTMLElement} params.captionEl
 * @returns {Promise<void>}
 */
export function runRevealSequence(map, params) {
  const { userCoords, plantCoords, mineCoords, plantName, mineName, captionEl } =
    params;

  const userLatLng = { lat: userCoords[0], lng: userCoords[1] };
  const plantLatLng = { lat: plantCoords[0], lng: plantCoords[1] };
  const mineLatLng = { lat: mineCoords[0], lng: mineCoords[1] };

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

      // Step 1: Zoom to user address and hold
      addMarker(map, userLatLng, "You", "#c4956a");
      showCaption(captionEl, "Your location");
      await smoothPanZoom(map, userLatLng, 14, FLY_DURATION);
      await delay(HOLD_DURATION);

      // Step 2: Zoom out to show the plant, draw connection line
      addMarker(map, plantLatLng, plantName, "#8aaa8a");
      showCaption(captionEl, plantName);
      const userPlantBounds = new google.maps.LatLngBounds();
      userPlantBounds.extend(userLatLng);
      userPlantBounds.extend(plantLatLng);
      map.fitBounds(userPlantBounds, { top: 80, bottom: 80, left: 80, right: 80 });
      await delay(FLY_DURATION);
      drawStaticLine(map, [userLatLng, plantLatLng], "#ffffff", 1.5, 0.35);
      await delay(1500);

      // Step 3: Follow the path to the mine
      addMarker(map, mineLatLng, mineName, "#d4d0c8");
      showCaption(captionEl, mineName);
      const allBounds = new google.maps.LatLngBounds();
      allBounds.extend(userLatLng);
      allBounds.extend(plantLatLng);
      allBounds.extend(mineLatLng);
      map.fitBounds(allBounds, { top: 80, bottom: 80, left: 80, right: 80 });
      await delay(FLY_DURATION);

      // Draw the flow line mine → plant
      const stopFlow = drawFlowLine(map, mineLatLng, plantLatLng);
      map._stopFlowAnimation = stopFlow;
      await delay(1500);

      // Step 4: Zoom in tight on the mine
      showCaption(captionEl, `${mineName} — source mine`);
      await smoothPanZoom(map, mineLatLng, 16, FLY_DURATION);
      await delay(HOLD_DURATION);

      // Final: zoom back out to show the full picture
      showCaption(captionEl, "");
      map.fitBounds(allBounds, { top: 60, bottom: 60, left: 60, right: 60 });
      await delay(FLY_DURATION);

      resolve();
    }

    google.maps.event.addListenerOnce(map, "tilesloaded", startSequence);
    // If tiles already loaded
    if (map.getTilt !== undefined) {
      setTimeout(() => {
        if (!settled) startSequence();
      }, 500);
    }
  });
}

/**
 * Smooth pan and zoom to a target.
 */
function smoothPanZoom(map, target, zoom, duration) {
  return new Promise((resolve) => {
    map.panTo(target);
    map.setZoom(zoom);
    // Google Maps animates panTo/setZoom internally
    setTimeout(resolve, duration);
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Add a labeled marker.
 */
function addMarker(map, position, label, color) {
  const marker = new google.maps.marker.AdvancedMarkerElement({
    map,
    position,
    title: label,
    content: buildMarkerElement(color),
  });

  // Show label as an info window
  const info = new google.maps.InfoWindow({
    content: `<div style="font-family:system-ui;font-size:13px;font-weight:600;color:#1a1a1a;padding:2px 4px">${label}</div>`,
    disableAutoPan: true,
  });
  info.open({ anchor: marker, map });

  return marker;
}

function buildMarkerElement(color) {
  const el = document.createElement("div");
  el.style.cssText = `
    width: 16px; height: 16px;
    background: ${color};
    border: 2px solid #ffffff;
    border-radius: 50%;
    box-shadow: 0 0 10px ${color}80;
  `;
  return el;
}

/**
 * Draw a static dotted line (user → plant context).
 */
function drawStaticLine(map, path, color, weight, opacity) {
  return new google.maps.Polyline({
    map,
    path,
    strokeColor: color,
    strokeWeight: weight,
    strokeOpacity: 0,
    icons: [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: opacity,
          strokeWeight: weight,
          scale: 3,
        },
        offset: "0",
        repeat: "16px",
      },
    ],
  });
}

/**
 * Draw the animated flow line (mine → plant).
 * Returns a stop function to cancel the animation.
 */
function drawFlowLine(map, from, to) {
  // Glow backing
  new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#c4956a",
    strokeWeight: 10,
    strokeOpacity: 0.3,
  });

  // Animated dashes
  const flowLine = new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#ffb347",
    strokeWeight: 3.5,
    strokeOpacity: 0,
    icons: [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 1,
          strokeWeight: 3.5,
          scale: 4,
        },
        offset: "0%",
        repeat: "24px",
      },
    ],
  });

  // Animate the dash offset
  let offset = 0;
  let stopped = false;

  const intervalId = setInterval(() => {
    if (stopped) return;
    offset = (offset + 0.5) % 100;
    flowLine.set("icons", [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 1,
          strokeWeight: 3.5,
          scale: 4,
        },
        offset: offset + "%",
        repeat: "24px",
      },
    ]);
  }, FLOW_ANIM_INTERVAL);

  return function stop() {
    stopped = true;
    clearInterval(intervalId);
  };
}

/**
 * Show or hide a caption on the map.
 */
function showCaption(el, text) {
  if (text) {
    el.textContent = text;
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}
