import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/mine-for-me': 'http://localhost:8001',
			'/ask': 'http://localhost:8001',
		},
	},
});
