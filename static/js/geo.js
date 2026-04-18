/**
 * Geolocation, point-in-polygon, and state-to-subregion lookup.
 *
 * The eGRID GeoJSON uses MultiPolygon geometries with a "Subregion" property.
 * Point-in-polygon uses the ray-casting algorithm.
 */

/**
 * US state -> primary eGRID subregion mapping.
 * When a state spans multiple subregions, the one most likely to have
 * coal-fired generation is chosen.
 */
export const STATE_TO_SUBREGION = {
  AL: "SRSO",
  AK: "AKGD",
  AZ: "AZNM",
  AR: "SRMV",
  CA: "CAMX",
  CO: "RMPA",
  CT: "NEWE",
  DE: "RFCE",
  FL: "FRCC",
  GA: "SRSO",
  HI: "HIMS",
  ID: "NWPP",
  IL: "SRMW",
  IN: "RFCW",
  IA: "MROW",
  KS: "SPNO",
  KY: "SRTV",
  LA: "SRMV",
  ME: "NEWE",
  MD: "RFCE",
  MA: "NEWE",
  MI: "RFCM",
  MN: "MROW",
  MS: "SRMV",
  MO: "SRMW",
  MT: "NWPP",
  NE: "MROW",
  NV: "NWPP",
  NH: "NEWE",
  NJ: "RFCE",
  NM: "AZNM",
  NY: "NYUP",
  NC: "SRVC",
  ND: "MROW",
  OH: "RFCW",
  OK: "SPSO",
  OR: "NWPP",
  PA: "RFCE",
  RI: "NEWE",
  SC: "SRVC",
  SD: "MROW",
  TN: "SRTV",
  TX: "ERCT",
  UT: "NWPP",
  VT: "NEWE",
  VA: "SRVC",
  WA: "NWPP",
  WV: "SRVC",
  WI: "MROE",
  WY: "RMPA",
  DC: "RFCE",
};

/**
 * Subregions that have coal data in our fallback set.
 * NEWE and some others have no coal plants.
 */
const COAL_SUBREGIONS = new Set([
  "AKGD", "AZNM", "CAMX", "ERCT", "FRCC",
  "MROE", "MROW", "NWPP", "RFCE", "RFCM",
  "RFCW", "RMPA", "SPNO", "SPSO", "SRMV",
  "SRMW", "SRSO", "SRTV", "SRVC",
]);

/**
 * Request the user's location via the browser Geolocation API.
 * @param {number} timeout - Max wait in ms (default 10000)
 * @returns {Promise<{lat: number, lon: number}|null>} Coordinates or null if denied/unavailable
 */
export function requestLocation(timeout = 10000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve(null);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: false, timeout, maximumAge: 300000 },
    );
  });
}

/**
 * Load the eGRID subregion GeoJSON from the server.
 * @returns {Promise<Object>} Parsed GeoJSON FeatureCollection
 */
export async function loadSubregionGeoJSON() {
  const resp = await fetch("/assets/egrid_subregions.geojson");
  if (!resp.ok) {
    throw new Error(`Failed to load eGRID GeoJSON: HTTP ${resp.status}`);
  }
  return resp.json();
}

/**
 * Find which eGRID subregion contains the given point.
 * @param {number} lat - Latitude
 * @param {number} lon - Longitude
 * @param {Object} geojson - FeatureCollection with MultiPolygon features
 * @returns {string|null} Subregion ID or null if outside all subregions
 */
export function findSubregion(lat, lon, geojson) {
  for (const feature of geojson.features) {
    const geomType = feature.geometry.type;
    const coords = feature.geometry.coordinates;

    if (geomType === "MultiPolygon") {
      for (const polygon of coords) {
        if (pointInPolygonRings(lon, lat, polygon)) {
          return feature.properties.Subregion;
        }
      }
    } else if (geomType === "Polygon") {
      if (pointInPolygonRings(lon, lat, coords)) {
        return feature.properties.Subregion;
      }
    }
  }
  return null;
}

/**
 * Test if a point is inside a polygon defined by rings (outer + holes).
 * Uses the ray-casting algorithm.
 * @param {number} x - Longitude
 * @param {number} y - Latitude
 * @param {Array} rings - Array of rings; rings[0] is outer boundary, rest are holes
 * @returns {boolean}
 */
function pointInPolygonRings(x, y, rings) {
  let inside = pointInRing(x, y, rings[0]);
  // Subtract holes
  for (let h = 1; h < rings.length; h++) {
    if (pointInRing(x, y, rings[h])) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Ray-casting algorithm for a single ring.
 * @param {number} x - Longitude
 * @param {number} y - Latitude
 * @param {Array} ring - Array of [lon, lat] coordinate pairs
 * @returns {boolean}
 */
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];

    if (
      (yi > y) !== (yj > y) &&
      x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    ) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Check whether a subregion has coal data available.
 * @param {string} subregionId
 * @returns {boolean}
 */
export function hasCoalData(subregionId) {
  return COAL_SUBREGIONS.has(subregionId);
}

/**
 * Get the subregion for a US state abbreviation.
 * @param {string} stateCode - Two-letter state code (e.g., "WV")
 * @returns {string|null} Subregion ID or null if not found
 */
export function subregionForState(stateCode) {
  return STATE_TO_SUBREGION[stateCode.toUpperCase()] || null;
}
