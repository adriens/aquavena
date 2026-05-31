import { defineConfig, fontProviders } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import VitePWA from '@vite-pwa/astro';

export default defineConfig({
  site: 'https://adriens.github.io',
  base: '/aquavena',
  output: 'static',
  security: {
    csp: {
      algorithm: 'SHA-256',
      directives: [
        "default-src 'self'",
        "font-src 'self' https://cdnjs.cloudflare.com",
        "img-src 'self' data:",
        "worker-src 'self'",
      ],
      styleDirective: {
        resources: ["'self'", "https://cdnjs.cloudflare.com"],
      },
    },
  },
  fonts: [{
    provider: fontProviders.google(),
    name: 'Atkinson Hyperlegible',
    cssVariable: '--font-atkinson',
  }],
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
