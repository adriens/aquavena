import rss from '@astrojs/rss';
import menusData from '../../data/menus.json';

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const s = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function descriptionHtml(day) {
  const sections = [];
  const midi = day.plats.filter(p => p.meal_time === 'midi');
  const soir = day.plats.filter(p => p.meal_time === 'soir');
  const gourmet = day.plats.filter(p => p.meal_time.startsWith('gourmet'));
  if (midi.length)    sections.push(`<p><strong>☀ Midi</strong><br>${midi.map(d => d.description).join('<br>')}</p>`);
  if (soir.length)    sections.push(`<p><strong>🌙 Soir</strong><br>${soir.map(d => d.description).join('<br>')}</p>`);
  if (gourmet.length) sections.push(`<p><strong>★ Gourmet</strong><br>${gourmet.map(d => d.description).join('<br>')}</p>`);
  if (day.supplements?.length) sections.push(`<p><strong>Suppléments</strong><br>${day.supplements.join('<br>')}</p>`);
  return sections.join('') || '<p>Aucun plat renseigné.</p>';
}

export function getStaticPaths() {
  return menusData.regimes.map(r => ({
    params: { slug: r.slug },
    props: { regime: r },
  }));
}

export function GET(context) {
  const { regime } = context.props;
  const { today } = menusData;

  const days = (regime.menu?.days ?? []).filter(d => d.date >= today);

  const items = days.map(day => ({
    title: `${formatDate(day.date)} — ${regime.name}`,
    pubDate: new Date(day.date + 'T00:00:00'),
    description: descriptionHtml(day),
    link: `${context.site}aquavena/`,
    customData: `<guid isPermaLink="false">${regime.slug}-${day.date}</guid>`,
  }));

  return rss({
    title: `Aquavena — ${regime.name}`,
    description: regime.menu?.description || `Menus ${regime.name} — Aquavena Nouvelle-Calédonie`,
    site: context.site,
    items,
    customData: `<language>fr-FR</language>`,
  });
}
