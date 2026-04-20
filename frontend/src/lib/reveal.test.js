import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { reveal } from './reveal.js';

describe('reveal action', () => {
	let observers;
	let originalMatchMedia;

	beforeEach(() => {
		observers = [];
		class MockIO {
			constructor(cb, opts) {
				this.cb = cb;
				this.opts = opts;
				this.observed = [];
				this.disconnected = false;
				observers.push(this);
			}
			observe(node) { this.observed.push(node); }
			unobserve(node) { this.observed = this.observed.filter((n) => n !== node); }
			disconnect() { this.disconnected = true; }
			trigger(node, isIntersecting) {
				this.cb([{ isIntersecting, target: node }]);
			}
		}
		vi.stubGlobal('IntersectionObserver', MockIO);
		originalMatchMedia = globalThis.matchMedia;
		globalThis.matchMedia = () => ({ matches: false, media: '', addEventListener() {}, removeEventListener() {} });
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		globalThis.matchMedia = originalMatchMedia;
	});

	it('applies initial hidden styles and observes the node', () => {
		const node = document.createElement('div');
		reveal(node, { delay: 100, distance: 32, threshold: 0.25 });
		expect(node.style.opacity).toBe('0');
		expect(node.style.transform).toBe('translateY(32px)');
		expect(observers).toHaveLength(1);
		expect(observers[0].observed).toContain(node);
		expect(observers[0].opts.threshold).toBe(0.25);
	});

	it('reveals and unobserves on intersection', () => {
		const node = document.createElement('div');
		reveal(node);
		observers[0].trigger(node, true);
		expect(node.style.opacity).toBe('1');
		expect(node.style.transform).toBe('translateY(0)');
		expect(observers[0].observed).not.toContain(node);
	});

	it('does not reveal when still below threshold', () => {
		const node = document.createElement('div');
		reveal(node);
		observers[0].trigger(node, false);
		expect(node.style.opacity).toBe('0');
	});

	it('disconnects observer on destroy', () => {
		const node = document.createElement('div');
		const action = reveal(node);
		action.destroy();
		expect(observers[0].disconnected).toBe(true);
	});

	it('skips animation when prefers-reduced-motion is set', () => {
		globalThis.matchMedia = () => ({ matches: true });
		const node = document.createElement('div');
		const action = reveal(node);
		expect(node.style.opacity).toBe('');
		expect(observers).toHaveLength(0);
		// destroy should still be callable without error.
		expect(() => action.destroy()).not.toThrow();
	});
});
