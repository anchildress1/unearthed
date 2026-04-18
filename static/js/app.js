/**
 * Main entry point for the unearthed frontend.
 *
 * Flow: parse share URL -> geolocation (or state picker) -> API call
 *       -> map reveal -> particle overlay + ticker -> prose -> chat
 */

import { fetchMineForMe } from "./api.js";
import { initChat } from "./chat.js";
import {
  findSubregion,
  hasCoalData,
  loadSubregionGeoJSON,
  requestLocation,
  STATE_TO_SUBREGION,
  subregionForState,
} from "./geo.js";
import { createMap, runRevealSequence } from "./map.js";
import { createParticleOverlay, showHeroImage, startTicker } from "./particles.js";

// --- CDN dependency check ---
if (typeof maplibregl === "undefined" || typeof PIXI === "undefined") {
  const msg = "Required libraries failed to load. Please check your network connection and reload.";
  document.body.textContent = msg;
  throw new Error(msg);
}

// --- DOM References ---
const introSection = document.getElementById("intro");
const contentSection = document.getElementById("content-section");
const infoPanel = document.getElementById("info-panel");

const btnLocate = document.getElementById("btn-locate");
const geoDenied = document.getElementById("geo-denied");
const geoOutsideUs = document.getElementById("geo-outside-us");
const statePicker = document.getElementById("state-picker");
const btnStateGo = document.getElementById("btn-state-go");
const loadingSpinner = document.getElementById("loading-spinner");
const errorMessage = document.getElementById("error-message");

const mapContainer = document.getElementById("map-container");
const mapCaption = document.getElementById("map-caption");

const heroImage = document.getElementById("hero-image");
const particleCanvas = document.getElementById("particle-canvas");
const tickerValue = document.getElementById("ticker-value");
const proseEl = document.getElementById("prose");

const detailMine = document.getElementById("detail-mine");
const detailOperator = document.getElementById("detail-operator");
const detailCounty = document.getElementById("detail-county");
const detailType = document.getElementById("detail-type");
const detailPlant = document.getElementById("detail-plant");
const detailTons = document.getElementById("detail-tons");

const chatChips = document.getElementById("chat-chips");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatTranscript = document.getElementById("chat-transcript");

const btnShare = document.getElementById("btn-share");
const shareCopied = document.getElementById("share-copied");

// --- Cleanup state for re-reveal safety ---
let tickerStop = null;
let pixiApp = null;
let mapInstance = null;
let shareHandler = null;
let geojsonData = null;
let userCoords = null;
let revealInProgress = false;

// --- Initialization ---
populateStatePicker();
checkShareUrl();

// --- Share URL ---
async function checkShareUrl() {
  const params = new URLSearchParams(window.location.search);
  const subregionParam = params.get("m");
  if (subregionParam && /^[A-Za-z0-9]{2,10}$/.test(subregionParam)) {
    try {
      await startReveal(subregionParam.toUpperCase(), null);
    } catch (err) {
      showSection(introSection);
      showLoading(false);
      showError(err.message || "Could not load mine data from share link.");
    }
  }
}

// --- Geolocation Flow ---
btnLocate.addEventListener("click", async () => {
  btnLocate.disabled = true;
  showLoading(true);
  hideError();

  try {
    const coords = await requestLocation();

    if (!coords) {
      // Geolocation denied or unavailable
      showLoading(false);
      btnLocate.disabled = false;
      document.getElementById("geo-prompt").classList.add("hidden");
      geoDenied.classList.remove("hidden");
      return;
    }

    userCoords = coords;

    // Load GeoJSON and find subregion
    if (!geojsonData) {
      geojsonData = await loadSubregionGeoJSON();
    }

    const subregion = findSubregion(coords.lat, coords.lon, geojsonData);

    if (!subregion) {
      // Outside US
      showLoading(false);
      btnLocate.disabled = false;
      document.getElementById("geo-prompt").classList.add("hidden");
      geoOutsideUs.classList.remove("hidden");
      geoDenied.classList.remove("hidden");
      return;
    }

    if (!hasCoalData(subregion)) {
      // Subregion has no coal data — show message and state picker
      showLoading(false);
      btnLocate.disabled = false;
      showError(
        `Your grid subregion (${subregion}) has no active coal supply chain in our data. ` +
          "Try the state picker to explore a coal-heavy region.",
      );
      document.getElementById("geo-prompt").classList.add("hidden");
      geoDenied.classList.remove("hidden");
      return;
    }

    await startReveal(subregion, [coords.lat, coords.lon]);
  } catch (err) {
    showLoading(false);
    btnLocate.disabled = false;
    showError(err.message || "Something went wrong. Please try again.");
  }
});

// --- State Picker ---
function populateStatePicker() {
  const states = Object.keys(STATE_TO_SUBREGION).sort((a, b) => a.localeCompare(b));
  for (const code of states) {
    const opt = document.createElement("option");
    opt.value = code;
    opt.textContent = stateLabel(code);
    statePicker.appendChild(opt);
  }
}

statePicker.addEventListener("change", () => {
  btnStateGo.disabled = !statePicker.value;
});

btnStateGo.addEventListener("click", async () => {
  const code = statePicker.value;
  if (!code) return;

  const subregion = subregionForState(code);
  if (!subregion) {
    showError("Could not determine a grid subregion for that state.");
    return;
  }

  if (!hasCoalData(subregion)) {
    showError(
      `The grid subregion for ${stateLabel(code)} (${subregion}) has no active coal supply chain in our data. ` +
        "Try selecting a different state.",
    );
    return;
  }

  btnStateGo.disabled = true;
  showLoading(true);
  hideError();

  try {
    await startReveal(subregion, null);
  } catch (err) {
    showSection(introSection);
    showLoading(false);
    showError(err.message || "Could not load mine data. Please try again.");
    btnStateGo.disabled = false;
  }
});

// --- Main Reveal Flow ---
async function startReveal(subregionId, coords) {
  if (revealInProgress) return;
  revealInProgress = true;
  showLoading(true);
  hideError();

  // Clean up any previous reveal resources
  cleanup();

  try {
    const data = await fetchMineForMe(subregionId);

    // Use provided user coords, or midpoint between plant and mine as fallback
    const resolvedUserCoords = coords || [
      (data.mine_coords[0] + data.plant_coords[0]) / 2,
      (data.mine_coords[1] + data.plant_coords[1]) / 2 - 1,
    ];

    // Transition to content section (map fills viewport; info panel is hidden)
    showSection(contentSection);

    mapInstance = createMap(mapContainer);
    await runRevealSequence(mapInstance, {
      userCoords: resolvedUserCoords,
      plantCoords: data.plant_coords,
      mineCoords: data.mine_coords,
      plantName: data.plant,
      mineName: data.mine,
      captionEl: mapCaption,
    });

    // Reveal the info panel alongside the map
    infoPanel.classList.remove("hidden");

    // Hero image + particles (particles are non-critical — catch failures)
    showHeroImage(heroImage, data.mine_type);
    try {
      pixiApp = createParticleOverlay(particleCanvas);
    } catch (pixiErr) {
      console.warn("Particle overlay unavailable:", pixiErr.message);
    }
    tickerStop = startTicker(tickerValue, data.tons);

    // Prose (fade in)
    proseEl.textContent = data.prose;
    requestAnimationFrame(() => proseEl.classList.add("prose--visible"));

    // Update OG metadata for social sharing
    updateOgMeta(data.mine, data.mine_state, data.mine_type);

    // Mine details
    detailMine.textContent = data.mine;
    detailOperator.textContent = data.mine_operator;
    detailCounty.textContent = `${data.mine_county}, ${data.mine_state}`;
    detailType.textContent = data.mine_type;
    detailPlant.textContent = `${data.plant} (${data.plant_operator})`;
    detailTons.textContent = `${Number(data.tons).toLocaleString()} tons (${data.tons_year})`;

    // Chat
    chatTranscript.dataset.subregionId = subregionId;
    initChat({
      chipsContainer: chatChips,
      form: chatForm,
      input: chatInput,
      transcript: chatTranscript,
      subregionId,
      mineName: data.mine,
      mineOperator: data.mine_operator,
      mineState: data.mine_state,
    });

    // Share
    setupShare(subregionId);
    revealInProgress = false;
  } catch (err) {
    showSection(introSection);
    showLoading(false);
    showError(err.message || "Could not load mine data. Please try again.");
    btnLocate.disabled = false;
    btnStateGo.disabled = false;
    revealInProgress = false;
  }
}

/**
 * Clean up resources from a previous reveal to prevent leaks on re-reveal.
 */
function cleanup() {
  if (tickerStop) {
    tickerStop();
    tickerStop = null;
  }
  if (pixiApp) {
    pixiApp.destroy(false);
    pixiApp = null;
  }
  if (mapInstance) {
    mapInstance._stopFlowAnimation?.();
    mapInstance.remove();
    mapInstance = null;
  }
  if (shareHandler) {
    btnShare.removeEventListener("click", shareHandler);
    shareHandler = null;
  }
  // Clear chat transcript
  chatTranscript.replaceChildren();
  proseEl.classList.remove("prose--visible");
  // Hide info panel so re-reveal starts with full-viewport map
  infoPanel.classList.add("hidden");
}

// --- Share ---
function setupShare(subregionId) {
  if (shareHandler) {
    btnShare.removeEventListener("click", shareHandler);
  }

  shareHandler = () => {
    const url = new URL(window.location.href);
    url.search = `?m=${encodeURIComponent(subregionId)}`;
    url.hash = "";

    if (navigator.clipboard) {
      navigator.clipboard.writeText(url.toString()).then(
        () => {
          shareCopied.classList.remove("hidden");
          setTimeout(() => shareCopied.classList.add("hidden"), 2000);
        },
        () => {
          shareCopied.textContent = "Could not copy link";
          shareCopied.classList.remove("hidden");
          setTimeout(() => {
            shareCopied.textContent = "Link copied";
            shareCopied.classList.add("hidden");
          }, 2000);
        },
      );
    } else {
      shareCopied.textContent = url.toString();
      shareCopied.classList.remove("hidden");
      setTimeout(() => {
        shareCopied.textContent = "Link copied";
        shareCopied.classList.add("hidden");
      }, 4000);
    }
  };

  btnShare.addEventListener("click", shareHandler);
}

// --- UI Helpers ---
function showSection(section) {
  introSection.classList.remove("section--active");
  introSection.classList.add("hidden");
  contentSection.classList.remove("section--active");
  contentSection.classList.add("hidden");

  section.classList.remove("hidden");
  section.classList.add("section--active");
}

function updateOgMeta(mineName, mineState, mineType) {
  const ogTitle = document.querySelector('meta[property="og:title"]');
  const ogDesc = document.querySelector('meta[property="og:description"]');
  const ogImage = document.querySelector('meta[property="og:image"]');
  if (ogTitle) {
    ogTitle.content = `unearthed — ${mineName}, ${mineState}`;
  }
  if (ogDesc) {
    ogDesc.content = `${mineName} in ${mineState} keeps your lights on. See the coal supply chain.`;
  }
  if (ogImage) {
    const heroFile = mineType === "Underground" ? "hero-underground.jpg" : "hero-surface.jpg";
    ogImage.content = `/static/img/${heroFile}`;
  }
  document.title = `unearthed — ${mineName}, ${mineState}`;
}

function showLoading(visible) {
  loadingSpinner.classList.toggle("hidden", !visible);
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.classList.remove("hidden");
}

function hideError() {
  errorMessage.classList.add("hidden");
}

function stateLabel(code) {
  const labels = {
    AL: "Alabama",
    AK: "Alaska",
    AZ: "Arizona",
    AR: "Arkansas",
    CA: "California",
    CO: "Colorado",
    CT: "Connecticut",
    DE: "Delaware",
    DC: "District of Columbia",
    FL: "Florida",
    GA: "Georgia",
    HI: "Hawaii",
    ID: "Idaho",
    IL: "Illinois",
    IN: "Indiana",
    IA: "Iowa",
    KS: "Kansas",
    KY: "Kentucky",
    LA: "Louisiana",
    ME: "Maine",
    MD: "Maryland",
    MA: "Massachusetts",
    MI: "Michigan",
    MN: "Minnesota",
    MS: "Mississippi",
    MO: "Missouri",
    MT: "Montana",
    NE: "Nebraska",
    NV: "Nevada",
    NH: "New Hampshire",
    NJ: "New Jersey",
    NM: "New Mexico",
    NY: "New York",
    NC: "North Carolina",
    ND: "North Dakota",
    OH: "Ohio",
    OK: "Oklahoma",
    OR: "Oregon",
    PA: "Pennsylvania",
    RI: "Rhode Island",
    SC: "South Carolina",
    SD: "South Dakota",
    TN: "Tennessee",
    TX: "Texas",
    UT: "Utah",
    VT: "Vermont",
    VA: "Virginia",
    WA: "Washington",
    WV: "West Virginia",
    WI: "Wisconsin",
    WY: "Wyoming",
  };
  return labels[code] || code;
}
