/**
 * Google Maps — cinematic reveal sequence.
 *
 * Uses panTo + fitBounds with Google's built-in smooth animation.
 * waitForIdle with timeout fallback so sequence completes even when
 * the tab isn't focused.
 *
 * Two identical animated flow lines:
 *   mine → plant (extraction)
 *   plant → user (delivery)
 *
 * The emotional arc:
 *   1. You are here. (Satellite close-up. You live here.)
 *   2. This is your power plant. (Zoom out. Line connects you.)
 *   3. This is the mine that feeds it. (Full chain. Both lines animate.)
 *   4. Look at it. (Zoom 17 on the mine. Hold 6 seconds.)
 *   5. This is the shape of your demand. (Pull back. Lines stay.)
 */

const MAP_LOAD_TIMEOUT_MS = 15000;
const IDLE_TIMEOUT_MS = 4000; // fallback if idle never fires (tab not visible)

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
      map.panTo(user);
      map.setZoom(15);
      await waitForIdle(map);
      addMarker(map, user, "You", "#c4956a");
      await hold(3500);

      // --- Act 2: Your power plant ---
      showCaption(captionEl, plantName);
      addMarker(map, plant, plantName, "#8aaa8a");
      const upBounds = toBounds([user, plant]);
      map.fitBounds(upBounds, 100);
      await waitForIdle(map);
      await hold(1500);

      // --- Act 3: The supply chain ---
      showCaption(captionEl, mineName);
      addMarker(map, mine, mineName, "#d4d0c8");
      const allBounds = toBounds([user, plant, mine]);
      map.fitBounds(allBounds, 100);
      await waitForIdle(map);
      await hold(1500);

      // Draw both flow lines — same style, same animation
      const stops = [
        drawFlowLine(map, mine, plant),
        drawFlowLine(map, plant, user),
      ];
      map._stopFlowAnimation = function stopAll() { stops.forEach((s) => s()); };
      await hold(3500);

      // --- Act 4: Look at it ---
      showCaption(captionEl, `${mineName} — source mine`);
      map.panTo(mine);
      map.setZoom(17);
      await waitForIdle(map);
      await hold(6000);

      // --- Act 5: Pull back ---
      showCaption(captionEl, "");
      map.fitBounds(allBounds, 80);
      await waitForIdle(map);
      await hold(1500);

      resolve();
    }

    google.maps.event.addListenerOnce(map, "tilesloaded", run);
  });
}

/**
 * Wait for the map to finish animating and loading tiles.
 * Falls back after IDLE_TIMEOUT_MS so the sequence completes
 * even when the tab isn't visible (idle won't fire without rendering).
 */
function waitForIdle(map) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    google.maps.event.addListenerOnce(map, "idle", finish);
    setTimeout(finish, IDLE_TIMEOUT_MS);
  });
}

function hold(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

function toBounds(points) {
  const b = new google.maps.LatLngBounds();
  for (const p of points) b.extend(p);
  return b;
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

  const el = document.createElement("div");
  el.style.cssText = "font-family:system-ui;font-size:13px;font-weight:600;color:#1a1a1a;padding:2px 4px";
  el.textContent = label;
  const info = new google.maps.InfoWindow({ content: el, disableAutoPan: true });
  info.open(map, marker);
  return marker;
}

// ---------------------------------------------------------------------------
// Flow lines
// ---------------------------------------------------------------------------

/**
 * Animated flow line — slow, deliberate crawl.
 * Same style for both mine→plant and plant→user.
 * Uses an arrow symbol that creeps along the line.
 * Returns a stop function.
 */
function drawFlowLine(map, from, to) {
  // Static backing line — always visible
  const backing = new google.maps.Polyline({
    map,
    path: [from, to],
    strokeColor: "#c4956a",
    strokeWeight: 3,
    strokeOpacity: 0.6,
    geodesic: true,
  });
  void backing;

  // Moving symbol — a small arrow that crawls along the line
  const arrow = {
    path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
    scale: 3,
    strokeColor: "#ffb347",
    strokeWeight: 2,
    fillColor: "#ffb347",
    fillOpacity: 1,
  };

  const line = new google.maps.Polyline({
    map,
    path: [from, to],
    strokeOpacity: 0,
    geodesic: true,
    icons: [
      { icon: arrow, offset: "0%" },
      { icon: arrow, offset: "25%" },
      { icon: arrow, offset: "50%" },
      { icon: arrow, offset: "75%" },
    ],
  });

  let count = 0;
  let stopped = false;

  // Crawl: 0.1% every 40ms — slow, relentless
  const id = setInterval(() => {
    if (stopped) return;
    count = (count + 1) % 1000;
    const pct = (count * 0.1) % 100;
    const icons = line.get("icons");
    icons[0].offset = pct + "%";
    icons[1].offset = ((pct + 25) % 100) + "%";
    icons[2].offset = ((pct + 50) % 100) + "%";
    icons[3].offset = ((pct + 75) % 100) + "%";
    line.set("icons", icons);
  }, 40);

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
