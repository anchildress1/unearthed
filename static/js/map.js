/**
 * Google Maps with cinematic reveal sequence.
 *
 * Sequence:
 *   1. Smooth zoom to user address, hold long enough to read
 *   2. Slow zoom out to show the power plant, draw connection
 *   3. Slow zoom out to show mine, draw animated flow line
 *   4. Slow zoom in on the mine at satellite level — hold morbidly long
 *   5. Ease back out to the full view with all lines visible
 *
 * All transitions use smooth recursive zoom to avoid jarring snaps.
 * Flow line animates at a slow, steady pace — not frantic.
 */

const MAP_LOAD_TIMEOUT_MS = 15000;

// Timing (ms) — deliberately slow, cinematic pacing
const HOLD_SHORT = 2000;
const HOLD_LONG = 4000;
const HOLD_MORBID = 5000;
const ZOOM_STEP_MS = 120; // ms per zoom level change — controls smoothness
const FLOW_ANIM_INTERVAL = 80; // slower dash crawl

// Load Google Maps core library.
const { Map: GMap } = await google.maps.importLibrary("maps");

/**
 * Initialize a Google Map in the given container.
 * @param {HTMLElement} container
 * @returns {google.maps.Map}
 */
export function createMap(container) {
  return new GMap(container, {
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

      // Step 1: Smooth zoom to user address — let them orient
      showCaption(captionEl, "Your location");
      map.panTo(userLatLng);
      await smoothZoom(map, 14, ZOOM_STEP_MS);
      addMarker(map, userLatLng, "You", "#c4956a");
      await delay(HOLD_LONG);

      // Step 2: Ease out to show plant
      showCaption(captionEl, plantName);
      addMarker(map, plantLatLng, plantName, "#8aaa8a");
      const userPlantBounds = new google.maps.LatLngBounds();
      userPlantBounds.extend(userLatLng);
      userPlantBounds.extend(plantLatLng);
      await smoothFitBounds(map, userPlantBounds, ZOOM_STEP_MS);
      await delay(HOLD_SHORT);
      drawStaticLine(map, [userLatLng, plantLatLng], "#ffffff", 1.5, 0.4);
      await delay(HOLD_SHORT);

      // Step 3: Ease out to show the mine
      showCaption(captionEl, mineName);
      addMarker(map, mineLatLng, mineName, "#d4d0c8");
      const allBounds = new google.maps.LatLngBounds();
      allBounds.extend(userLatLng);
      allBounds.extend(plantLatLng);
      allBounds.extend(mineLatLng);
      await smoothFitBounds(map, allBounds, ZOOM_STEP_MS);
      await delay(HOLD_SHORT);

      // Draw the flow line mine → plant — slow, deliberate
      const stopFlow = drawFlowLine(map, mineLatLng, plantLatLng);
      map._stopFlowAnimation = stopFlow;
      await delay(HOLD_LONG);

      // Step 4: Zoom in tight on the mine — satellite detail, hold morbidly long
      showCaption(captionEl, `${mineName} — source mine`);
      map.panTo(mineLatLng);
      await smoothZoom(map, 18, ZOOM_STEP_MS);
      await delay(HOLD_MORBID);

      // Step 5: Ease back out to the full picture
      showCaption(captionEl, "");
      await smoothFitBounds(map, allBounds, ZOOM_STEP_MS);
      await delay(HOLD_SHORT);

      resolve();
    }

    google.maps.event.addListenerOnce(map, "tilesloaded", startSequence);
  });
}

/**
 * Smooth zoom — steps one level at a time with a pause between each.
 * Prevents the jarring snap of setZoom().
 */
function smoothZoom(map, targetZoom, stepMs) {
  return new Promise((resolve) => {
    const current = map.getZoom();
    if (current === targetZoom) {
      resolve();
      return;
    }

    const direction = targetZoom > current ? 1 : -1;
    let level = current;

    const step = () => {
      level += direction;
      map.setZoom(level);
      if (level === targetZoom) {
        resolve();
      } else {
        setTimeout(step, stepMs);
      }
    };

    setTimeout(step, stepMs);
  });
}

/**
 * Smooth fitBounds — zoom out to target bounds one level at a time,
 * then let fitBounds do the final precise adjustment.
 */
function smoothFitBounds(map, bounds, stepMs) {
  return new Promise((resolve) => {
    // Figure out what zoom fitBounds would produce
    const targetZoom = getBoundsZoom(map, bounds);
    const current = map.getZoom();

    if (current <= targetZoom) {
      // Already zoomed out enough, just fit
      map.fitBounds(bounds, { top: 80, bottom: 80, left: 80, right: 80 });
      setTimeout(resolve, 500);
      return;
    }

    // Zoom out smoothly, then fit precisely
    let level = current;
    const step = () => {
      level -= 1;
      map.setZoom(level);
      map.panTo(bounds.getCenter());
      if (level <= targetZoom) {
        map.fitBounds(bounds, { top: 80, bottom: 80, left: 80, right: 80 });
        setTimeout(resolve, 500);
      } else {
        setTimeout(step, stepMs);
      }
    };

    setTimeout(step, stepMs);
  });
}

/**
 * Estimate the zoom level for a given bounds (rough approximation).
 */
function getBoundsZoom(map, bounds) {
  const ne = bounds.getNorthEast();
  const sw = bounds.getSouthWest();
  const latSpan = ne.lat() - sw.lat();
  const lngSpan = ne.lng() - sw.lng();
  const span = Math.max(latSpan, lngSpan);

  // Rough: each zoom level halves the span
  if (span > 40) return 3;
  if (span > 20) return 4;
  if (span > 10) return 5;
  if (span > 5) return 6;
  if (span > 2) return 7;
  if (span > 1) return 8;
  if (span > 0.5) return 9;
  return 10;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Add a labeled marker.
 */
function addMarker(map, position, label, color) {
  const marker = new google.maps.Marker({
    map,
    position,
    title: label,
    icon: {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 8,
      fillColor: color,
      fillOpacity: 1,
      strokeColor: "#ffffff",
      strokeWeight: 2,
    },
  });

  const info = new google.maps.InfoWindow({
    content: `<div style="font-family:system-ui;font-size:13px;font-weight:600;color:#1a1a1a;padding:2px 4px">${label}</div>`,
    disableAutoPan: true,
  });
  info.open(map, marker);

  return marker;
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
 * Slow, steady crawl — not frantic.
 * Returns a stop function to cancel the animation.
 */
function drawFlowLine(map, from, to) {
  // Glow backing
  new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#c4956a",
    strokeWeight: 8,
    strokeOpacity: 0.25,
  });

  // Animated dashes
  const flowLine = new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#ffb347",
    strokeWeight: 3,
    strokeOpacity: 0,
    icons: [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 0.9,
          strokeWeight: 3,
          scale: 4,
        },
        offset: "0%",
        repeat: "28px",
      },
    ],
  });

  // Slow, steady crawl — 0.2% every 80ms
  let offset = 0;
  let stopped = false;

  const intervalId = setInterval(() => {
    if (stopped) return;
    offset = (offset + 0.2) % 100;
    flowLine.set("icons", [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 0.9,
          strokeWeight: 3,
          scale: 4,
        },
        offset: offset + "%",
        repeat: "28px",
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
