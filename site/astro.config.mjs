import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import VitePWA from '@vite-pwa/astro';

export default defineConfig({
  site: 'https://adriens.github.io',
  base: '/aquavena',
  output: 'static',
  integrations: [
    tailwind(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Aquavena — Menus pour malvoyants',
        short_name: 'Aquavena',
        description: 'Menus Aquavena optimisés pour les malvoyants — Nouvelle-Calédonie',
        theme_color: '#0f766e',
        background_color: '#FFFBEB',
        display: 'standalone',
        start_url: '/aquavena/',
        lang: 'fr',
        icons: [
          { src: '/aquavena/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/aquavena/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{html,css,js,json}'],
        navigateFallback: '/aquavena/',
      },
    }),
  ],
});
