import { sveltekit } from '@sveltejs/kit/vite';
import { svelteTesting } from '@testing-library/svelte/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit(), svelteTesting()],
	test: {
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./vitest.setup.js'],
		include: ['src/**/*.{test,spec}.{js,ts}'],
		exclude: ['node_modules', 'e2e', '.svelte-kit', '**/*.test.svelte'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'html', 'lcov'],
			include: ['src/lib/**/*.{js,svelte}'],
			exclude: ['src/lib/assets/**', '**/*.d.ts'],
		},
	},
});
