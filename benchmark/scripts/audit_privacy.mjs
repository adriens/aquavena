#!/usr/bin/env node
/**
 * Privacy / tracking audit.
 * For each URL: open it in headless Chrome, capture all cookies, all network
 * requests, classify first-party vs third-party, flag known tracker domains.
 *
 * Usage:  node audit_privacy.mjs <url> [<url> ...]
 * Output: JSON to stdout
 *   { "<url>": { first_party_hosts, third_party_hosts, known_trackers,
 *                cookies, third_party_requests, total_requests } }
 */

import puppeteer from "puppeteer";

// Well-known tracker / analytics host patterns
const TRACKER_PATTERNS = [
  /google-analytics\.com/i,
  /googletagmanager\.com/i,
  /googlesyndication\.com/i,
  /doubleclick\.net/i,
  /facebook\.com\/tr/i,
  /facebook\.net/i,
  /connect\.facebook\.net/i,
  /hotjar\.com/i,
  /mixpanel\.com/i,
  /segment\.(com|io)/i,
  /amplitude\.com/i,
  /intercom\.io/i,
  /clarity\.ms/i,
  /yandex\.(ru|com)/i,
  /addthis\.com/i,
  /scorecardresearch\.com/i,
  /quantserve\.com/i,
  /matomo\.cloud/i,
  /piwik\.pro/i,
  /chartbeat\.com/i,
  /newrelic\.com/i,
  /\bsentry\.io/i,
  /optimizely\.com/i,
  /fullstory\.com/i,
  /heapanalytics\.com/i,
  /linkedin\.com\/.*insight/i,
  /twitter\.com\/i\/adsct/i,
  /tiktok\.com\/business/i,
  /bing\.com\/bat/i,
  /branch\.io/i,
];

function isSameRegistrableDomain(hostA, hostB) {
  // Very small heuristic: same hostname OR same suffix on last two labels.
  if (hostA === hostB) return true;
  const a = hostA.split(".").slice(-2).join(".");
  const b = hostB.split(".").slice(-2).join(".");
  return a === b;
}

async function audit(targetUrl) {
  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage();
    const targetHost = new URL(targetUrl).hostname;

    const reqs = [];
    page.on("request", (req) => reqs.push(req.url()));

    await page.goto(targetUrl, {
      waitUntil: "networkidle2",
      timeout: 30000,
    });

    const cookies = await page.cookies();

    const allHosts = new Set();
    const thirdPartyHosts = new Set();
    const thirdPartyReqs = [];
    for (const u of reqs) {
      let h;
      try {
        h = new URL(u).hostname;
      } catch {
        continue;
      }
      allHosts.add(h);
      if (!isSameRegistrableDomain(h, targetHost)) {
        thirdPartyHosts.add(h);
        thirdPartyReqs.push(u);
      }
    }

    const knownTrackers = [...thirdPartyHosts].filter((h) =>
      TRACKER_PATTERNS.some((p) => p.test(h)),
    );

    return {
      url: targetUrl,
      target_host: targetHost,
      total_requests: reqs.length,
      third_party_requests: thirdPartyReqs.length,
      first_party_hosts: [...allHosts].filter((h) =>
        isSameRegistrableDomain(h, targetHost),
      ),
      third_party_hosts: [...thirdPartyHosts],
      known_trackers: knownTrackers,
      cookies_count: cookies.length,
      cookies: cookies.map((c) => ({
        name: c.name,
        domain: c.domain,
        secure: c.secure,
        httpOnly: c.httpOnly,
        sameSite: c.sameSite,
      })),
    };
  } finally {
    await browser.close();
  }
}

(async () => {
  const urls = process.argv.slice(2);
  if (urls.length === 0) {
    console.error("Usage: node audit_privacy.mjs <url> [<url> ...]");
    process.exit(2);
  }
  const out = {};
  for (const u of urls) {
    try {
      out[u] = await audit(u);
    } catch (e) {
      out[u] = { error: String(e) };
    }
  }
  console.log(JSON.stringify(out, null, 2));
})();
