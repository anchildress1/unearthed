/**
 * PixiJS coal-dust particle overlay with tonnage ticker.
 *
 * Uses ParticleContainer with sprite batching for >= 30 FPS on low-end hardware.
 * Tonnage rate: annual_tons / seconds_in_year, displayed to two decimal places.
 */

const SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60;
const MAX_PARTICLES = 300;
const PARTICLE_SIZE = 3;
const SPAWN_RATE = 4; // particles per frame

// Hero images: pre-1980 public domain (Library of Congress)
const HERO_IMAGES = {
  Surface: "/static/img/hero-surface.jpg",
  Underground: "/static/img/hero-underground.jpg",
};

/**
 * Initialize the PixiJS particle overlay.
 * @param {HTMLCanvasElement} canvas
 * @param {string} mineType - "Surface" or "Underground"
 * @returns {PIXI.Application}
 */
export function createParticleOverlay(canvas) {
  const app = new PIXI.Application({
    view: canvas,
    resizeTo: canvas.parentElement,
    backgroundAlpha: 0,
    antialias: false,
    resolution: Math.min(window.devicePixelRatio, 2),
    autoDensity: true,
  });

  const particleContainer = new PIXI.ParticleContainer(MAX_PARTICLES, {
    position: true,
    alpha: true,
    scale: true,
  });
  app.stage.addChild(particleContainer);

  // Generate a small circular texture for particles
  const gfx = new PIXI.Graphics();
  gfx.beginFill(0xd4d0c8, 0.8);
  gfx.drawCircle(0, 0, PARTICLE_SIZE);
  gfx.endFill();
  const texture = app.renderer.generateTexture(gfx);
  gfx.destroy();

  const particles = [];

  app.ticker.add(() => {
    const { width, height } = app.screen;

    // Spawn new particles from the top
    for (let i = 0; i < SPAWN_RATE && particles.length < MAX_PARTICLES; i++) {
      const sprite = new PIXI.Sprite(texture);
      sprite.x = Math.random() * width;
      sprite.y = -PARTICLE_SIZE;
      sprite.alpha = 0.2 + Math.random() * 0.5;
      sprite.scale.set(0.5 + Math.random() * 1.0);
      sprite._vy = 0.3 + Math.random() * 0.8;
      sprite._vx = (Math.random() - 0.5) * 0.3;
      sprite._fadeRate = 0.001 + Math.random() * 0.002;
      particleContainer.addChild(sprite);
      particles.push(sprite);
    }

    // Update existing particles
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.y += p._vy;
      p.x += p._vx;
      p.alpha -= p._fadeRate;

      if (p.y > height + PARTICLE_SIZE || p.alpha <= 0) {
        particleContainer.removeChild(p);
        p.destroy();
        particles.splice(i, 1);
      }
    }
  });

  return app;
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
  heroEl.classList.add("reveal__hero--visible");
}

/**
 * Start the tonnage ticker.
 * @param {HTMLElement} tickerEl - The element to update with the current value
 * @param {number} annualTons - Annual tonnage
 * @returns {function} Stop function to cancel the ticker
 */
export function startTicker(tickerEl, annualTons) {
  const tonsPerSecond = annualTons / SECONDS_IN_YEAR;
  const startTime = performance.now();
  let rafId = null;

  function update() {
    const elapsed = (performance.now() - startTime) / 1000;
    const tons = tonsPerSecond * elapsed;
    tickerEl.textContent = tons.toFixed(2);
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
