# Benchmark d'accessibilité — Aquavena vs aquavena.nc

Comparaison systématique de l'accessibilité entre ce site (adriens.github.io/aquavena) et le site source
(aquavena.nc), en utilisant des outils CLI standards et reproductibles.

---

## Structure du répertoire

```
benchmark/
├── ACCESSIBILITY_BENCHMARK.md  ← ce fichier
├── .gitignore                  ← exclut reports/ (généré)
├── data/                       ← exports CSV pour analyse data science
├── quarto/                     ← rapports Quarto R (à venir)
└── reports/                    ← rapports générés (gitignorés)
    ├── pa11y.json
    ├── lighthouse.report.json
    └── lighthouse.report.html
```

Pour générer les rapports :

```bash
cd aquavena-sdk/site
npm run report   # build + pa11y-ci + Lighthouse → benchmark/reports/
```

---

## Outils utilisés

| Outil | Version | Rôle |
|---|---|---|
| **pa11y-ci** | 4.1.1 | Audit WCAG 2.1 AA automatisé, multi-URL |
| **Lighthouse** | 13.3.0 | Score accessibilité 0–100, 24 audits |
| **axe-cli** | 4.11.3 | Audit axe-core en CLI, détail des violations |
| **W3C Validator** | API REST | Validation HTML sémantique |
| **webhint** | 7.1.13 | Compat navigateurs, sécurité, perf, headers HTTP |
| **pa11y** | 9.1.1 | Audit unitaire par URL (dev interactif) |

### Configuration pa11y-ci (`.pa11yci.json`)

```json
{
  "defaults": {
    "standard": "WCAG2AA",
    "runners": ["axe", "htmlcs"],
    "chromeLaunchConfig": { "args": ["--no-sandbox", "--disable-setuid-sandbox"] },
    "ignore": [
      "WCAG2AA.Principle1.Guideline1_4.1_4_3_F24.F24.FGColour",
      "WCAG2AA.Principle1.Guideline1_4.1_4_3_F24.F24.BGColour"
    ]
  },
  "urls": [
    "http://localhost:4321/#aqua-m%C3%A9diterran%C3%A9en",
    "http://localhost:4321/about/"
  ]
}
```

> Les deux règles ignorées sont des faux positifs htmlcs liés aux variables CSS (`var(--text-main)`).
> axe-core vérifie les contrastes effectifs au rendu — les ignorer est sans risque.

---

## Résultats — notre site

Date d'audit : 30 mai 2026

### pa11y-ci — WCAG 2.1 AA

| URL | Erreurs | Avertissements |
|---|---|---|
| `/#aqua-méditerranéen` | **0** | 0 |
| `/about/` | **0** | 0 |

### Lighthouse Accessibility

| Métrique | Valeur |
|---|---|
| Score | **100 / 100** |
| Audits réussis | 24 |
| Audits échoués | 0 |
| Non applicables | 42 |

### axe-cli

```
0 violations found
```

---

## Résultats — aquavena.nc (site source)

Date d'audit : 30 mai 2026 — URL : `https://www.aquavena.nc/formules/aqua-méditerranéen`

### pa11y-ci — WCAG 2.1 AA

| URL | Erreurs |
|---|---|
| aquavena.nc/formules/aqua-méditerranéen | **67** |

### Lighthouse Accessibility

| Métrique | Valeur |
|---|---|
| Score | **91 / 100** |
| Audits réussis | 22 |
| Audits échoués | 2 |

### webhint (aquavena.nc)

```
compat-api/css             1 error      1 warning
css-prefix-order           2 warnings
sri                        2 errors
x-content-type-options     2 errors
content-type               4 warnings
strict-transport-security  5 errors
http-compression           3 warnings   4 hints
no-disallowed-headers      10 warnings
http-cache                 12 warnings  4 hints
axe/color                  27 warnings
button-type                112 hints
Total : 10 errors, 63 warnings, 120 hints
```

---

## Tableau comparatif

| Critère | Notre site | aquavena.nc |
|---|---|---|
| **pa11y WCAG 2.1 AA — erreurs** | ✅ **0** | ❌ 67 |
| **Lighthouse Accessibility** | ✅ **100/100** | 🟡 91/100 |
| **axe-core violations** | ✅ **0** | ❌ détectées |
| **HTML valide (W3C)** | ✅ | non audité |
| **PWA (manifest + SW)** | ✅ | ❌ non |
| **Mode nuit** | ✅ | ❌ non |
| **Taille texte réglable** | ✅ | ❌ non |
| **Lecture vocale intégrée** | ✅ | ❌ non |
| **Police Atkinson Hyperlegible** | ✅ | ❌ non |
| **Flux RSS** | ✅ | ❌ non |
| **Calendriers iCal** | ✅ | ❌ non |

---

## Violations corrigées (notre site)

Toutes les violations identifiées lors de l'audit initial ont été corrigées :

### Contraste WCAG 2.1 AA (1.4.3)

| Élément | Avant | Après |
|---|---|---|
| Tous les boutons `speak-btn` (about + index) | `bg-teal-600` (#0d9488) | `bg-teal-700` (#0f766e) |
| Bouton "Lire toute la semaine" | `bg-teal-600` | `bg-teal-700` |
| Bouton RSS | `bg-orange-500` | `bg-orange-700` |
| Bouton iCal | `bg-sky-500` | `bg-sky-700` |
| Bouton Instagram | `bg-pink-500` | `bg-pink-700` |
| Lien aquavena.nc | `bg-teal-600` | `bg-teal-700` |
| Badge Score AIM | `bg-teal-600 text-teal-100` | `bg-teal-700 text-white` |
| Textes orange | `text-orange-500` | `text-orange-700` |
| Textes sky | `text-sky-500` | `text-sky-700` |
| Textes trophée | `text-amber-500` | `text-amber-700` |
| Bouton WhatsApp | `bg-green-600` | `bg-green-700` |

### Landmark / Région (4.1.3)

| Élément | Correction |
|---|---|
| Barre de recherche | Ajout de `role="search"` sur le `<div>` englobant |

### Tabs (mode nuit)

Remplacé les classes Tailwind fixes par des variables CSS + sélecteur `[data-dark]` pour une lisibilité garantie
en mode clair et sombre.

---

## Méthodologie de test

### Test local complet

```bash
# 1. Mettre à jour les données
cd aquavena-sdk && python scripts/fetch_data.py

# 2. Build + rapport complet (pa11y-ci + Lighthouse)
cd site && npm run report
# → benchmark/reports/pa11y.json
# → benchmark/reports/lighthouse.report.json
# → benchmark/reports/lighthouse.report.html

# 3. Audit pa11y interactif uniquement
npm run a11y
```

### Test avec axe-cli (live ou local)

```bash
# Sur le site déployé
npx axe https://adriens.github.io/aquavena/ --chromedriver-path ~/.browser-driver-manager/chromedriver/linux-149.0.7827.54/chromedriver-linux64/chromedriver

# Sur le site local (après npm run build + npx serve dist -p 4321)
npx axe http://localhost:4321/ --chromedriver-path ~/.browser-driver-manager/chromedriver/linux-149.0.7827.54/chromedriver-linux64/chromedriver
```

### Validation HTML W3C

```bash
curl -s -H "Content-Type: text/html; charset=utf-8" \
  --data-binary @dist/index.html \
  "https://validator.w3.org/nu/?out=json" | jq '.messages | length'
```

### Audit webhint (site distant)

```bash
npx hint https://adriens.github.io/aquavena/
```

---

## Vision data science (à venir)

L'objectif final est de produire un article PDF comparatif généré avec **Quarto** et **R** :

```
benchmark/
  data/
    aquavena_a11y.csv      ← exports pa11y + Lighthouse (colonnes: url, date, tool, score, violations)
    aquavena_nc_a11y.csv   ← mêmes métriques sur aquavena.nc
  duckdb/
    benchmark.duckdb       ← base de données analytique
  quarto/
    report.qmd             ← article Quarto
    report.pdf             ← rendu final
```

Pipeline envisagé :

```
npm run report  →  pa11y.json + lighthouse.json
      ↓
CSV export (script Node.js ou Python)
      ↓
DuckDB (chargement + requêtes SQL)
      ↓
Quarto R (ggplot2, knitr)  →  PDF
```
