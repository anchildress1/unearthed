/**
 * Google Maps — cinematic reveal sequence.
 *
 * Uses moveCamera() with requestAnimationFrame for smooth, interpolated
 * camera transitions. No tween library — just easeInOutCubic and lerp.
 *
 * The emotional arc:
 *   1. You are here. (Satellite close-up of your neighborhood. You live here.)
 *   2. This is your power plant. (Zoom out. A line connects you to it.)
 *   3. This is the mine that feeds it. (The full supply chain, laid bare.)
 *   4. Look at it. (Zoom 18 on the mine. Scarred earth. Hold for 6 seconds.)
 *   5. This is the shape of your demand. (Pull back. The lines stay.)
 */

const MAP_LOAD_TIMEOUT_MS = 15000;

// Load Google Maps core library.
const { Map: GMap } = await google.maps.importLibrary("maps");

/**
 * Initialize a Google Map.
 */
export function createMap(container) {
  return new GMap(container, {
    center: { lat: 39.8, lng: -98.5 },
    zoom: 4,
    mapTypeId: "hybrid",
    disableDefaultUI: true,
    zoomControl: true,
    gestureHandling: "greedy",
    tilt: 0,
  });
}

/**
 * Run the cinematic reveal sequence.
 */
export function runRevealSequence(map, params) {
  const { userCoords, plantCoords, mineCoords, plantName, mineName, captionEl } =
    params;

  const user = { lat: userCoords[0], lng: userCoords[1] };
  const plant = { lat: plantCoords[0], lng: plantCoords[1] };
  const mine = { lat: mineCoords[0], lng: mineCoords[1] };

  return new Promise((resolve, reject) => {
    let settled = false;

    const tid = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error("Map failed to load. Please check your network connection."));
      }
    }, MAP_LOAD_TIMEOUT_MS);

    async function run() {
      if (settled) return;
      settled = true;
      clearTimeout(tid);

      // --- Act 1: You are here ---
      showCaption(captionEl, "Your location");
      await flyTo(map, { center: user, zoom: 15 }, 3000);
      addMarker(map, user, "You", "#c4956a");
      await hold(3000);

      // --- Act 2: Your power plant ---
      showCaption(captionEl, plantName);
      addMarker(map, plant, plantName, "#8aaa8a");
      const upBounds = toBounds([user, plant]);
      await flyTo(map, { center: midpoint(user, plant), zoom: boundsZoom(upBounds) }, 3000);
      await hold(1500);
      drawLine(map, [user, plant], "#ffffff", 2, 0.5);
      await hold(2000);

      // --- Act 3: The supply chain ---
      showCaption(captionEl, mineName);
      addMarker(map, mine, mineName, "#d4d0c8");
      const allBounds = toBounds([user, plant, mine]);
      await flyTo(map, { center: midpoint(user, mine), zoom: boundsZoom(allBounds) }, 3500);
      await hold(1500);
      const stopFlow = drawFlowLine(map, mine, plant);
      map._stopFlowAnimation = stopFlow;
      await hold(3000);

      // --- Act 4: Look at it ---
      showCaption(captionEl, mineName);
      await flyTo(map, { center: mine, zoom: 18 }, 4000);
      await hold(6000);

      // --- Act 5: Pull back ---
      showCaption(captionEl, "");
      await flyTo(map, { center: midpoint(user, mine), zoom: boundsZoom(allBounds) }, 3500);
      await hold(1000);

      resolve();
    }

    google.maps.event.addListenerOnce(map, "tilesloaded", run);
  });
}

// ---------------------------------------------------------------------------
// Camera animation
// ---------------------------------------------------------------------------

/**
 * Smooth camera flight using moveCamera + requestAnimationFrame.
 * Interpolates center, zoom, tilt, and heading with easeInOutCubic.
 */
function flyTo(map, target, durationMs) {
  return new Promise((resolve) => {
    const startCenter = map.getCenter();
    const startZoom = map.getZoom();
    const startTilt = map.getTilt() || 0;
    const startHeading = map.getHeading() || 0;

    const endCenter = target.center;
    const endZoom = target.zoom ?? startZoom;
    const endTilt = target.tilt ?? 0;
    const endHeading = target.heading ?? 0;

    const start = performance.now();

    function frame(now) {
      const elapsed = now - start;
      const t = Math.min(elapsed / durationMs, 1);
      const e = easeInOutCubic(t);

      map.moveCamera({
        center: {
          lat: lerp(startCenter.lat(), endCenter.lat, e),
          lng: lerp(startCenter.lng(), endCenter.lng, e),
        },
        zoom: lerp(startZoom, endZoom, e),
        tilt: lerp(startTilt, endTilt, e),
        heading: lerp(startHeading, endHeading, e),
      });

      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        resolve();
      }
    }

    requestAnimationFrame(frame);
  });
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function hold(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

function midpoint(a, b) {
  return { lat: (a.lat + b.lat) / 2, lng: (a.lng + b.lng) / 2 };
}

function toBounds(points) {
  const b = new google.maps.LatLngBounds();
  for (const p of points) b.extend(p);
  return b;
}

function boundsZoom(bounds) {
  const ne = bounds.getNorthEast();
  const sw = bounds.getSouthWest();
  const span = Math.max(Math.abs(ne.lat() - sw.lat()), Math.abs(ne.lng() - sw.lng()));
  if (span > 40) return 3;
  if (span > 20) return 4;
  if (span > 10) return 5;
  if (span > 5) return 6;
  if (span > 2) return 7;
  if (span > 1) return 8;
  if (span > 0.5) return 9;
  if (span > 0.2) return 10;
  return 11;
}

// ---------------------------------------------------------------------------
// Markers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Lines
// ---------------------------------------------------------------------------

function drawLine(map, path, color, weight, opacity) {
  return new google.maps.Polyline({
    map,
    path,
    strokeColor: color,
    strokeWeight: weight,
    strokeOpacity: opacity,
    geodesic: true,
  });
}

/**
 * Animated flow line — slow, deliberate crawl from mine toward plant.
 * The movement should feel heavy, inevitable. Not fast. Not fun.
 */
function drawFlowLine(map, from, to) {
  // Dim glow — the corridor
  new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#c4956a",
    strokeWeight: 8,
    strokeOpacity: 0.2,
    geodesic: true,
  });

  // Animated dashes — the extraction
  const line = new google.maps.Polyline({
    map,
    path: [from, to],
    strokeOpacity: 0,
    geodesic: true,
    icons: [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 0.8,
          strokeColor: "#ffb347",
          strokeWeight: 3,
          scale: 4,
        },
        offset: "0%",
        repeat: "32px",
      },
    ],
  });

  let offset = 0;
  let stopped = false;

  // 0.15% every 60ms — slow, heavy, relentless
  const id = setInterval(() => {
    if (stopped) return;
    offset = (offset + 0.15) % 100;
    line.set("icons", [
      {
        icon: {
          path: "M 0,-1 0,1",
          strokeOpacity: 0.8,
          strokeColor: "#ffb347",
          strokeWeight: 3,
          scale: 4,
        },
        offset: offset + "%",
        repeat: "32px",
      },
    ]);
  }, 60);

  return function stop() {
    stopped = true;
    clearInterval(id);
  };
}

// ---------------------------------------------------------------------------
// Caption
// ---------------------------------------------------------------------------

function showCaption(el, text) {
  if (text) {
    el.textContent = text;
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}
