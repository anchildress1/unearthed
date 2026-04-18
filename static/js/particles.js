/**
 * Canvas 2D coal-dust atmospheric overlay with tonnage ticker.
 *
 * Replaces the PixiJS particle approach. Canvas 2D gives direct control over
 * blend modes and radial-gradient soft blobs — essential for haze, not circles.
 *
 * Visual approach:
 *   - globalCompositeOperation "screen": particles add luminosity against dark
 *     backgrounds without ever bleaching to white. Perfect for suspended haze.
 *   - Radial gradient per particle: soft falloff from center → transparent edge.
 *     No hard-edged circles. Each blob reads as a dust mote in diffuse light.
 *   - Two depth layers: many small/slow far particles (the atmosphere itself) +
 *     fewer larger/faster near particles (foreground drift).
 *   - Brownian motion with drag: zero net direction, no gravity, no spawning.
 *     All particles pre-seeded across the full canvas and edge-wrapped.
 *
 * Tonnage rate: annual_tons / seconds_in_year, displayed to two decimal places.
 */

const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;
const MAX_PARTICLES = 300;

// Warm gray-brown — coal haze reads as this under diffuse light
// rgb(160, 140, 120) with screen blend mode glows subtly against #0d0d0d
const DUST_RGB_FAR = "160, 140, 120";
const DUST_RGB_NEAR = "200, 180, 155";

// Brownian motion parameters — coal dust barely moves
const MAX_SPEED = 0.38;
const BROWNIAN_STRENGTH = 0.05;
const DRAG = 0.978;

// Layer definitions — far (atmosphere) + near (foreground motes)
const LAYERS = [
  // Far: dense, small, slow, slightly opaque — the haze field itself
  { count: 200, minR: 2.5, maxR: 7, minAlpha: 0.09, maxAlpha: 0.30, speedFactor: 0.35, rgb: DUST_RGB_FAR },
  // Near: sparse, larger, faster, more diffuse
  { count: 100, minR: 1.5, maxR: 4, minAlpha: 0.12, maxAlpha: 0.38, speedFactor: 0.85, rgb: DUST_RGB_NEAR },
];

// Hero images: pre-1980 public domain (Library of Congress)
const HERO_IMAGES = {
  Surface: "/static/img/hero-surface.jpg",
  Underground: "/static/img/hero-underground.jpg",
};

function rng(min, max) {
  return min + Math.random() * (max - min);
}

/**
 * Initialize the Canvas 2D particle overlay.
 * @param {HTMLCanvasElement} canvas
 * @returns {{ destroy: Function }}
 */
export function createParticleOverlay(canvas) {
  canvas.style.pointerEvents = "none";

  const ctx = canvas.getContext("2d");
  const particles = [];
  let w = 0;
  let h = 0;
  let rafId = null;

  // Size the backing buffer to match physical pixels
  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = rect.width;
    h = rect.height;
    if (w === 0 || h === 0) return;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function spawnAll() {
    particles.length = 0;
    for (const layer of LAYERS) {
      for (let i = 0; i < layer.count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = rng(0.02, MAX_SPEED * layer.speedFactor);
        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: rng(layer.minR, layer.maxR),
          baseAlpha: rng(layer.minAlpha, layer.maxAlpha),
          alphaPhase: Math.random() * Math.PI * 2,
          alphaRate: rng(0.005, 0.018),
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          rgb: layer.rgb,
        });
      }
    }
  }

  // Initial sizing — synchronous, no async resize surprise
  resize();
  if (w > 0 && h > 0) {
    spawnAll();
  }

  // Watch for layout changes (panel slide-in, mobile resize, etc.)
  const ro = new ResizeObserver(() => {
    resize();
    if (particles.length === 0 && w > 0 && h > 0) {
      spawnAll();
    }
  });
  ro.observe(canvas);

  function tick() {
    if (particles.length === 0 && w > 0 && h > 0) {
      spawnAll();
    }

    ctx.clearRect(0, 0, w, h);

    // "screen" blend: each particle adds luminosity, never bleaches to white.
    // Against the dark hero-bg (#0d0d0d) this produces subtle warm haze.
    ctx.globalCompositeOperation = "screen";

    for (const p of particles) {
      // Brownian perturbation — equal probability in every direction
      p.vx += (Math.random() - 0.5) * BROWNIAN_STRENGTH;
      p.vy += (Math.random() - 0.5) * BROWNIAN_STRENGTH;

      // Drag — prevents cumulative drift from winning
      p.vx *= DRAG;
      p.vy *= DRAG;

      // Speed cap — keeps particles suspended, not racing
      const spd = Math.hypot(p.vx, p.vy);
      if (spd > MAX_SPEED) {
        p.vx = (p.vx / spd) * MAX_SPEED;
        p.vy = (p.vy / spd) * MAX_SPEED;
      }

      p.x += p.vx;
      p.y += p.vy;

      // Edge wrap — seamless, no pop-in flash
      const r = p.r;
      if (p.x < -r) p.x = w + r;
      else if (p.x > w + r) p.x = -r;
      if (p.y < -r) p.y = h + r;
      else if (p.y > h + r) p.y = -r;

      // Alpha shimmer — each mote breathes independently
      p.alphaPhase += p.alphaRate;
      const alpha = p.baseAlpha * (0.6 + 0.4 * Math.sin(p.alphaPhase));

      // Radial gradient: solid center → transparent edge. Soft mote, not hard disc.
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
      grad.addColorStop(0, `rgba(${p.rgb}, ${alpha})`);
      grad.addColorStop(1, `rgba(${p.rgb}, 0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;

    rafId = requestAnimationFrame(tick);
  }

  rafId = requestAnimationFrame(tick);

  return {
    destroy(_removeView) {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      ro.disconnect();
      particles.length = 0;
    },
  };
}

/**
 * Show the hero image behind the particle overlay.
 * @param {HTMLElement} heroEl - The hero image div
 * @param {string} mineType - "Surface" or "Underground"
 */
export function showHeroImage(heroEl, mineType) {
  const url = HERO_IMAGES[mineType] || HERO_IMAGES.Surface;
  heroEl.style.backgroundImage = `url('${url}')`;
  // Fade in even if image fails to load (dark bg still works for particles)
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

/**
 * Calculate tons per second from annual tonnage.
 * Exported for testing.
 * @param {number} annualTons
 * @returns {number}
 */
export function tonsPerSecond(annualTons) {
  return annualTons / SECONDS_IN_YEAR;
}
