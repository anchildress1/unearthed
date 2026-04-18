/**
 * API client for the unearthed backend.
 * Two endpoints: /mine-for-me (reveal payload) and /ask (Cortex Analyst).
 */

const API_BASE = window.location.origin;

/**
 * Fetch the top mine-plant pair for a given eGRID subregion.
 * @param {string} subregionId - eGRID subregion code (e.g., "SRVC")
 * @returns {Promise<Object>} MineForMeResponse JSON
 * @throws {Error} on network or HTTP errors
 */
export async function fetchMineForMe(subregionId) {
  const resp = await fetch(`${API_BASE}/mine-for-me`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subregion_id: subregionId }),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || `HTTP ${resp.status}`;
    throw new Error(detail);
  }

  return resp.json();
}

/**
 * Ask a natural-language question via Cortex Analyst.
 * @param {string} question - The user's question (max 500 chars)
 * @param {string|null} subregionId - Optional subregion for context
 * @returns {Promise<Object>} AskResponse JSON
 * @throws {Error} on network errors
 */
export async function fetchAsk(question, subregionId = null) {
  const payload = { question };
  if (subregionId) {
    payload.subregion_id = subregionId;
  }

  const resp = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || `HTTP ${resp.status}`;
    throw new Error(detail);
  }

  return resp.json();
}
