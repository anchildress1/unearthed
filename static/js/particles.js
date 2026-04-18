/**
 * Hero image display and tonnage ticker.
 *
 * Tonnage rate: annual_tons / seconds_in_year, displayed to two decimal places.
 */

const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;

// Hero images: pre-1980 public domain (Library of Congress)
const HERO_IMAGES = {
  Surface: "/static/img/hero-surface.jpg",
  Underground: "/static/img/hero-underground.jpg",
};

/**
 * Show the hero image.
 * @param {HTMLElement} heroEl - The hero image div
 * @param {string} mineType - "Surface" or "Underground"
 */
export function showHeroImage(heroEl, mineType) {
  const url = HERO_IMAGES[mineType] || HERO_IMAGES.Surface;
  heroEl.style.backgroundImage = `url('${url}')`;
  heroEl.classList.add("hero-bg--visible");
}

/**
 * Start the tonnage ticker.
 * @param {HTMLElement} tickerEl - The element to update with the current value
 * @param {number} annualTons - Annual tonnage
 * @returns {function} Stop function to cancel the ticker
 */
export function startTicker(tickerEl, annualTons) {
  const rate = annualTons / SECONDS_IN_YEAR;
  const startTime = performance.now();
  let rafId = null;

  function update() {
    const elapsed = (performance.now() - startTime) / 1000;
    tickerEl.textContent = (rate * elapsed).toFixed(2);
    rafId = requestAnimationFrame(update);
  }

  rafId = requestAnimationFrame(update);

  return () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
    }
  };
}
