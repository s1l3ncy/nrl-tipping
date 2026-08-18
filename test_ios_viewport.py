#!/usr/bin/env python3
"""iOS no-cover layout backstops (WebKit 301994; viewport-fit=cover removed 2026-08-18).

Adapted from the Fit booking tool project's tests/test_layout_backstops.py.
Drives the real page with navigator.standalone and screen.height shimmed to
reproduce the two standalone geometries measured on-device (iPhone 17 Pro Max,
iOS 26.6, 18 Aug 2026):

  LETTERBOXED  missing=62 : view seated below the status bar, flush at the bottom.
               --sat must stay 0 (the island is above the view).
               --sab must be restored to 34px (the indicator overlaps the view).
  FULL-BLEED   missing=0  : view underlaps island and indicator.
               --sat must be 62px, --sab 34px.

Also: env()-reporting wins over both, transitions re-decide on resize, pinch zoom
holds state, Android/browser-tab get nothing, no JS errors, no horizontal overflow,
and both prefers-color-scheme values behave identically (the app is dark-only).

Run: python3 test_ios_viewport.py [path-to-nrl-tipping-guide.html]
Data files (nrl_data.js etc.) are picked up from the HTML file's own directory.
Exit non-zero on any failure (mutation testing requires that).
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent
HTML = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "nrl-tipping-guide.html"

FAILS = []
def ok(name, cond, extra=""):
    print(("ok  " if cond else "FAIL") + " " + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)

# The page polls ESPN + the footytips comp API while open; stub fetch so the test
# is hermetic and never depends on network.
FETCH_STUB = r"""
(() => {
  const jsonRes = (obj) => new Response(JSON.stringify(obj),
    {status: 200, headers: {'Content-Type': 'application/json'}});
  window.fetch = async () => jsonRes({});
})();
"""

SHIM = r"""
(() => {
  const MISSING = __MISSING__;
  try { Object.defineProperty(window.navigator, 'standalone',
        {get: () => true, configurable: true}); } catch(e) {}
  try {
    const realScreen = window.screen;
    Object.defineProperty(window, 'screen', {configurable: true, get: () => new Proxy(realScreen, {
      get(t, p){ return p === 'height' ? (window.innerHeight + window.__missing__) : t[p]; }
    })});
    window.__missing__ = MISSING;
  } catch(e) {}
})();
"""

ENV_STYLE = r"""
(() => {
  const el = document.createElement('style');
  el.textContent = ':root{--sat:59px !important;--sab:34px !important;}';
  const add = () => (document.head || document.documentElement).appendChild(el);
  if (document.head) add(); else document.addEventListener('DOMContentLoaded', add);
})();
"""

IOS_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 Mobile/15E148 Safari/604.1")
ANDROID_UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")

async def launch_page(browser, scheme, ua, missing, extra_init=None):
    ctx = await browser.new_context(
        viewport={"width": 440, "height": 894}, device_scale_factor=3,
        is_mobile=True, has_touch=True, color_scheme=scheme, user_agent=ua)
    await ctx.add_init_script(FETCH_STUB)
    if missing is not None:
        await ctx.add_init_script(SHIM.replace("__MISSING__", str(missing)))
    if extra_init:
        await ctx.add_init_script(extra_init)
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(f"file://{HTML}", wait_until="load", timeout=30000)
    await page.wait_for_timeout(1200)
    return ctx, page, errors

async def snapshot(page):
    return await page.evaluate("""() => {
      const root = document.documentElement;
      const bar = document.querySelector('.tabbar');
      const nav = document.querySelector('.topnav');
      const meas = (name) => {
        const d = document.createElement('div');
        d.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:var(' + name + ');visibility:hidden';
        document.body.appendChild(d);
        const h = d.getBoundingClientRect().height; d.remove(); return h;
      };
      return {
        satInline: root.style.getPropertyValue('--sat').trim(),
        sabInline: root.style.getPropertyValue('--sab').trim(),
        satPx: meas('--sat'), sabPx: meas('--sab'),
        barPadBottom: bar ? parseFloat(getComputedStyle(bar).paddingBottom) : null,
        navPadTop: nav ? parseFloat(getComputedStyle(nav).paddingTop) : null,
        bodyPadBottom: parseFloat(getComputedStyle(document.body).paddingBottom),
        hOverflow: (document.scrollingElement || document.documentElement).scrollWidth
                   - window.innerWidth,
      };
    }""")

async def main():
    # ── 0. static guard: the viewport meta must never regain viewport-fit=cover ──
    import re
    head = HTML.read_text(encoding="utf-8")
    metas = re.findall(r'<meta[^>]*name="viewport"[^>]*>', head)
    ok("static: exactly one viewport meta, without viewport-fit=cover (WebKit 301994)",
       len(metas) == 1 and "viewport-fit" not in metas[0]
       and "width=device-width" in metas[0], str(metas))

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # ── 1. LETTERBOXED (the current on-device iOS 26.6 state) ─────────────
        ctx, page, errors = await launch_page(browser, "dark", IOS_UA, 62)
        s = await snapshot(page)
        ok("letterboxed: boots clean (no JS errors)", not errors, "; ".join(errors[:3]))
        ok("letterboxed: --sat stays 0 (a naive backstop would set 62)", s["satPx"] == 0, json.dumps(s))
        ok("letterboxed: --sab restored to 34px", s["sabInline"] == "34px" and s["sabPx"] == 34, json.dumps(s))
        ok("letterboxed: tab bar pads 8+34=42px", s["barPadBottom"] == 42, str(s["barPadBottom"]))
        ok("letterboxed: header pads 0+12=12px (clock is above the view)", s["navPadTop"] == 12, str(s["navPadTop"]))
        ok("letterboxed: body clears bar by 96+34=130px", s["bodyPadBottom"] == 130, str(s["bodyPadBottom"]))
        ok("letterboxed: no horizontal overflow", s["hOverflow"] <= 0, str(s["hOverflow"]))

        # ── 2. transition to FULL-BLEED and back, mid-session ────────────────
        await page.evaluate("window.__missing__ = 0; window.dispatchEvent(new Event('resize'))")
        await page.wait_for_timeout(150)
        s = await snapshot(page)
        ok("full-bleed after resize: --sat 62px", s["satInline"] == "62px" and s["satPx"] == 62, json.dumps(s))
        ok("full-bleed after resize: --sab 34px", s["sabPx"] == 34, json.dumps(s))
        ok("full-bleed: header clears the island (62+12=74px)", s["navPadTop"] == 74, str(s["navPadTop"]))
        await page.evaluate("window.__missing__ = 62; window.dispatchEvent(new Event('resize'))")
        await page.wait_for_timeout(150)
        s = await snapshot(page)
        ok("back to letterboxed: --sat dropped to 0", s["satPx"] == 0, json.dumps(s))

        # ── 2b. outside both signatures (landscape-like): overrides DROP ──────
        await page.evaluate("window.__missing__ = 520; window.dispatchEvent(new Event('resize'))")
        await page.wait_for_timeout(150)
        s = await snapshot(page)
        ok("520px shortfall: both overrides dropped (re-run wired)",
           s["sabPx"] == 0 and s["satPx"] == 0, json.dumps(s))
        await page.evaluate("window.__missing__ = 62; window.dispatchEvent(new Event('resize'))")
        await page.wait_for_timeout(150)
        s = await snapshot(page)
        ok("back to letterboxed: --sab restored again", s["sabPx"] == 34, json.dumps(s))

        # ── 3. pinch zoom holds the last decision ────────────────────────────
        await page.evaluate("""() => {
          Object.defineProperty(window, 'visualViewport',
            {configurable: true, get: () => ({scale: 2})});
          window.__missing__ = 500;
          window.dispatchEvent(new Event('resize'));
        }""")
        await page.wait_for_timeout(150)
        s = await snapshot(page)
        ok("zoomed resize: --sab held at 34px (no flash to 0)", s["sabPx"] == 34, json.dumps(s))
        await ctx.close()

        # ── 4. env() reporting wins: no inline overrides at all ───────────────
        ctx, page, errors = await launch_page(browser, "dark", IOS_UA, 62, ENV_STYLE)
        s = await snapshot(page)
        ok("env present: no inline --sat/--sab overrides",
           s["satInline"] == "" and s["sabInline"] == "", json.dumps(s))
        ok("env present: stylesheet values rule (59/34)", s["satPx"] == 59 and s["sabPx"] == 34, json.dumps(s))
        await ctx.close()

        # ── 5. light colour scheme: identical (the app is dark-only) ─────────
        ctx, page, errors = await launch_page(browser, "light", IOS_UA, 62)
        s = await snapshot(page)
        ok("light scheme letterboxed: boots clean, --sab 34, --sat 0, no overflow",
           not errors and s["sabPx"] == 34 and s["satPx"] == 0 and s["hOverflow"] <= 0, json.dumps(s))
        await ctx.close()

        # ── 6. Android standalone: untouched ─────────────────────────────────
        ctx, page, errors = await launch_page(browser, "dark", ANDROID_UA, 62)
        s = await snapshot(page)
        ok("android: no overrides (sat 0, sab 0, bar pad 8)",
           s["satPx"] == 0 and s["sabPx"] == 0 and s["barPadBottom"] == 8, json.dumps(s))
        await ctx.close()

        # ── 7. plain browser tab: untouched ──────────────────────────────────
        ctx, page, errors = await launch_page(browser, "dark", IOS_UA, None)
        s = await snapshot(page)
        ok("browser tab: no overrides", s["satPx"] == 0 and s["sabPx"] == 0, json.dumps(s))
        await ctx.close()

        await browser.close()

    print("\n" + ("ALL GREEN" if not FAILS else f"FAILURES: {len(FAILS)}"))
    sys.exit(1 if FAILS else 0)

asyncio.run(main())
