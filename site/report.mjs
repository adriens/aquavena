#!/usr/bin/env node
// Génère un rapport d'accessibilité complet : pa11y-ci + Lighthouse
import { execSync, spawn } from 'child_process';
import { readFileSync, mkdirSync } from 'fs';
import { resolve } from 'path';

const PORT = 4321;
const BASE = `http://localhost:${PORT}`;
const HASH = `#aqua-m%C3%A9diterran%C3%A9en`;
const REPORTS = resolve('reports');

mkdirSync(REPORTS, { recursive: true });

// --- Démarrer le serveur ---
const server = spawn('npx', ['serve', 'dist', '-p', String(PORT)], { stdio: 'ignore' });
await new Promise(r => setTimeout(r, 3000));

let exitCode = 0;
try {
  // --- pa11y-ci ---
  console.log('\n📋 pa11y-ci — audit WCAG2AA\n');
  try {
    execSync(`npx pa11y-ci --config .pa11yci.json --json > reports/pa11y.json 2>/dev/null`, { stdio: 'inherit' });
  } catch {
    // pa11y-ci exits non-zero when issues found — check the JSON anyway
  }
  let pa11yResult = { results: {} };
  try { pa11yResult = JSON.parse(readFileSync('reports/pa11y.json', 'utf8')); } catch {}

  let totalErrors = 0, totalWarnings = 0;
  for (const [url, issues] of Object.entries(pa11yResult.results ?? {})) {
    const errors   = (issues ?? []).filter(i => i.type === 'error').length;
    const warnings = (issues ?? []).filter(i => i.type === 'warning').length;
    totalErrors   += errors;
    totalWarnings += warnings;
    const icon = errors === 0 ? '✅' : '❌';
    console.log(`  ${icon} ${url} — ${errors} erreur(s), ${warnings} avertissement(s)`);
  }
  console.log(`\n  Total : ${totalErrors} erreur(s), ${totalWarnings} avertissement(s)`);

  // --- Lighthouse ---
  console.log('\n🔦 Lighthouse — score accessibilité\n');
  execSync(
    `npx lighthouse "${BASE}/${HASH}" ` +
    `--only-categories=accessibility ` +
    `--output=json,html ` +
    `--output-path=reports/lighthouse ` +
    `--chrome-flags="--no-sandbox --headless" ` +
    `--quiet`,
    { stdio: 'inherit' }
  );

  const lh = JSON.parse(readFileSync('reports/lighthouse.report.json', 'utf8'));
  const score = Math.round(lh.categories.accessibility.score * 100);
  const audits = lh.categories.accessibility.auditRefs;
  const failed  = audits.filter(a => lh.audits[a.id]?.score === 0);
  const passed  = audits.filter(a => lh.audits[a.id]?.score === 1);
  const na      = audits.filter(a => lh.audits[a.id]?.scoreDisplayMode === 'notApplicable');

  const bar = '█'.repeat(Math.round(score / 5)) + '░'.repeat(20 - Math.round(score / 5));
  console.log(`\n  Score : ${score}/100  [${bar}]`);
  console.log(`  ✅ Réussis : ${passed.length}   ❌ Échoués : ${failed.length}   — N/A : ${na.length}`);

  if (failed.length > 0) {
    console.log('\n  Audits échoués :');
    for (const a of failed) {
      console.log(`    ✗ ${lh.audits[a.id].id} — ${lh.audits[a.id].title}`);
    }
    exitCode = 1;
  }

  console.log(`\n  📄 Rapport HTML → reports/lighthouse.report.html`);
  console.log(`  📄 Rapport JSON → reports/lighthouse.report.json`);
  console.log(`  📄 pa11y JSON   → reports/pa11y.json`);

  // --- Résumé final ---
  console.log('\n' + '─'.repeat(50));
  const ok = totalErrors === 0 && failed.length === 0;
  console.log(`\n  ${ok ? '🎉 TOUT EST OK' : '⚠️  DES PROBLÈMES ONT ÉTÉ DÉTECTÉS'}`);
  console.log(`  pa11y WCAG2AA : ${totalErrors === 0 ? '0 erreur ✅' : totalErrors + ' erreur(s) ❌'}`);
  console.log(`  Lighthouse    : ${score}/100 ${score === 100 ? '✅' : score >= 90 ? '🟡' : '❌'}\n`);

} finally {
  server.kill();
}

process.exit(exitCode);
