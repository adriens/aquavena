import menusData from '../../data/menus.json';

function toAsciiSlug(slug) {
  return slug.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9-]/g, '-');
}

function icsDate(dateStr) {
  return dateStr.replace(/-/g, '');
}

function icsEscape(str) {
  return str.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/\n/g, '\\n');
}

function buildDesc(day) {
  const parts = [];
  const midi    = day.plats.filter(p => p.meal_time === 'midi').map(p => p.description);
  const soir    = day.plats.filter(p => p.meal_time === 'soir').map(p => p.description);
  const gourmet = day.plats.filter(p => p.meal_time.startsWith('gourmet')).map(p => p.description);
  if (midi.length)             parts.push('Midi :\n' + midi.join('\n'));
  if (soir.length)             parts.push('Soir :\n' + soir.join('\n'));
  if (gourmet.length)          parts.push('Gourmet :\n' + gourmet.join('\n'));
  if (day.supplements?.length) parts.push('Supplements :\n' + day.supplements.join('\n'));
  return parts.join('\n\n');
}

function makeEvent(day, regime, siteUrl) {
  const midi = day.plats.filter(p => p.meal_time === 'midi').map(p => p.description);
  const soir = day.plats.filter(p => p.meal_time === 'soir').map(p => p.description);
  const summaryParts = [
    midi.length && 'Midi : ' + midi.join(', '),
    soir.length && 'Soir : ' + soir.join(', '),
  ].filter(Boolean);

  return [
    'BEGIN:VEVENT',
    `DTSTART;VALUE=DATE:${icsDate(day.date)}`,
    'DURATION:P1D',
    `SUMMARY:Aquavena ${regime.name} - ${summaryParts.join(' | ')}`,
    `DESCRIPTION:${icsEscape(buildDesc(day))}`,
    `UID:${regime.slug}-${day.date}@aquavena.nc`,
    `URL:${siteUrl}aquavena/`,
    'END:VEVENT',
  ].join('\r\n');
}

export function getStaticPaths() {
  return menusData.regimes.map(r => ({
    params: { slug: toAsciiSlug(r.slug) },
    props: { regime: r },
  }));
}

export function GET(context) {
  const { regime } = context.props;
  const { today } = menusData;

  const days = (regime.menu?.days ?? []).filter(d => d.date >= today);
  const events = days.map(day => makeEvent(day, regime, context.site));

  const cal = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Aquavena//Menus//FR',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:Aquavena - ${regime.name}`,
    'X-WR-TIMEZONE:Pacific/Noumea',
    ...events,
    'END:VCALENDAR',
  ].join('\r\n');

  return new Response(cal, {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8' },
  });
}
