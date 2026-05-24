import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  site: 'https://adriens.github.io',
  base: '/aquavena-sdk',
  output: 'static',
  integrations: [tailwind()],
});
