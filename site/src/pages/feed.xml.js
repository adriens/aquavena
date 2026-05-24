import rss from '@astrojs/rss';
import menusData from '../data/menus.json';

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const s = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function GET(context) {
  const { regimes, today } = menusData;

  const items = [];
  for (const r of regimes) {
    const days = (r.menu?.days ?? []).filter((d) => d.date >= today);
    for (const day of days) {
      const midi = day.plats
        .filter((p) => p.meal_time === 'midi')
        .map((p) => p.description)
        .join(', ');
      const soir = day.plats
        .filter((p) => p.meal_time === 'soir')
        .map((p) => p.description)
        .join(', ');
      const gourmet = day.plats
        .filter((p) => p.meal_time.startsWith('gourmet'))
        .map((p) => p.description)
        .join(', ');

      const parts = [
        midi && `☀ Midi : ${midi}`,
        soir && `🌙 Soir : ${soir}`,
        gourmet && `★ Gourmet : ${gourmet}`,
      ].filter(Boolean);

      items.push({
        title: `${formatDate(day.date)} — ${r.name}`,
        pubDate: new Date(day.date + 'T00:00:00'),
        description: parts.join(' | '),
        link: `${context.site}aquavena/`,
        customData: `<guid isPermaLink="false">${r.slug}-${day.date}</guid>`,
      });
    }
  }

  // Sort by date ascending
  items.sort((a, b) => a.pubDate - b.pubDate);

  return rss({
    title: 'Aquavena — Menus de la semaine',
    description: 'Menus diététiques Aquavena, Nouvelle-Calédonie',
    site: context.site,
    items,
    customData: '<language>fr-FR</language>',
  });
}
