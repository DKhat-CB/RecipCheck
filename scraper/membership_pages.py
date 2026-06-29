"""Tier 2 fetch + membership-section isolation + hashing.

Fetch ladder:
  1. httpx with realistic browser headers.
  2. On 403 / 429 / empty-or-tiny body, fall back to Playwright/Chromium (renders JS and
     defeats most WAF bot blocks). Chromium is expected at PLAYWRIGHT_BROWSERS_PATH.

Failure is a first-class state: a page that yields no usable membership text returns
status="blocked" or "js_only" so the orchestrator can flag it rather than emit junk.

Section isolation: extract visible text, then keep the region around membership/price/tier
keywords and normalize whitespace. The hash is computed over that normalized region only,
so event banners and nav changes do not force a re-extraction.
"""
from __future__ import annotations

import glob
import hashlib
import os
import re
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


def _chromium_executable() -> str | None:
    """Locate a usable Chromium binary.

    The managed environment ships a pre-installed browser whose build number may not match
    the pip `playwright` package's expectation, so we point `executable_path` at it directly
    (per the environment's guidance) rather than downloading. Prefer full chromium over the
    headless shell. Returns None to let Playwright use its own default.
    """
    override = os.environ.get("CHROMIUM_EXECUTABLE")
    if override and os.path.exists(override):
        return override
    roots = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    for pat in (
        os.path.join(roots, "chromium-*/chrome-linux/chrome"),
        os.path.join(roots, "chromium_headless_shell-*/chrome-linux/headless_shell"),
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

MEMBERSHIP_KEYWORDS = re.compile(
    r"member|membership|join|annual|reciprocal|narm|roam|astc|admission|tier|"
    r"\$\d|household|family|patron|benefit",
    re.I,
)

# How much surrounding context to keep around the membership region.
_SECTION_MAX_CHARS = 24000


@dataclass
class FetchResult:
    url: str
    html: str
    status: str  # "ok" | "blocked" | "js_only" | "error"
    method: str  # "httpx" | "playwright"
    http_status: int | None
    note: str = ""


def robots_allows(url: str, user_agent: str) -> bool:
    """Best-effort robots.txt check. On any error, default to allow (we are low-volume)."""
    try:
        parts = urlparse(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        resp = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=15, follow_redirects=True)
        if resp.status_code >= 400:
            return True
        rp.parse(resp.text.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def robots_crawl_delay(url: str, user_agent: str) -> float | None:
    try:
        parts = urlparse(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.crawl_delay(user_agent)
    except Exception:
        return None


def _looks_empty(html: str) -> bool:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) < 600 or not MEMBERSHIP_KEYWORDS.search(text)


def _fetch_httpx(url: str, timeout: int) -> FetchResult:
    try:
        resp = httpx.get(url, headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        return FetchResult(url, "", "error", "httpx", None, note=str(e))
    if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
        return FetchResult(url, resp.text, "blocked", "httpx", resp.status_code,
                           note=f"http {resp.status_code}")
    if resp.status_code >= 400:
        return FetchResult(url, resp.text, "error", "httpx", resp.status_code,
                           note=f"http {resp.status_code}")
    if _looks_empty(resp.text):
        return FetchResult(url, resp.text, "js_only", "httpx", resp.status_code,
                           note="empty/short body")
    return FetchResult(url, resp.text, "ok", "httpx", resp.status_code)


# Some egress proxies do not support browser HTTPS CONNECT tunneling. Probe once and, if the
# browser cannot reach the network, skip the Playwright tier for the rest of the run so each
# blocked page fails fast instead of paying a browser launch + timeout.
_PLAYWRIGHT_USABLE: bool | None = None


def _playwright_usable() -> bool:
    global _PLAYWRIGHT_USABLE
    if _PLAYWRIGHT_USABLE is not None:
        return _PLAYWRIGHT_USABLE
    probe = _fetch_playwright("https://example.com", 15, _probe=True)
    _PLAYWRIGHT_USABLE = probe.status in ("ok", "js_only") and bool(probe.html)
    return _PLAYWRIGHT_USABLE


def _fetch_playwright(url: str, timeout: int, _probe: bool = False) -> FetchResult:
    if not _probe and not _playwright_usable():
        return FetchResult(url, "", "error", "playwright", None,
                           note="browser cannot reach network through proxy")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        return FetchResult(url, "", "error", "playwright", None, note=f"playwright unavailable: {e}")
    exe = _chromium_executable()
    launch_kwargs = {"headless": True}
    if exe:
        launch_kwargs["executable_path"] = exe
    # Outbound HTTPS in this environment must traverse the egress proxy; Chromium does not
    # read HTTPS_PROXY on its own, so pass it explicitly. The proxy's CA is trusted via the
    # system/NSS store, so TLS still verifies.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}
    ctx_kwargs = {"user_agent": BROWSER_HEADERS["User-Agent"], "locale": "en-US"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(**ctx_kwargs)
            page = ctx.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            html = page.content()
            code = resp.status if resp else None
            browser.close()
    except Exception as e:  # noqa: BLE001
        return FetchResult(url, "", "error", "playwright", None, note=str(e))
    if _looks_empty(html):
        status = "blocked" if (code and code in (401, 403, 429)) else "js_only"
        return FetchResult(url, html, status, "playwright", code, note="empty/short after render")
    return FetchResult(url, html, "ok", "playwright", code)


def fetch(url: str, timeout: int = 30) -> FetchResult:
    """Run the fetch ladder. httpx first; Playwright on block/empty/error."""
    first = _fetch_httpx(url, timeout)
    if first.status == "ok":
        return first
    second = _fetch_playwright(url, timeout)
    if second.status == "ok":
        return second
    # neither worked — return the more informative failure
    return second if second.html or second.note else first


def isolate_membership_text(html: str) -> str:
    """Strip tags, keep the membership-relevant region, normalize whitespace."""
    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        for tag in tree.css("script, style, noscript, svg, header, footer, nav"):
            tag.decompose()
        text = tree.body.text(separator="\n") if tree.body else tree.text(separator="\n")
    except Exception:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", text)

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    hit_idx = [i for i, ln in enumerate(lines) if MEMBERSHIP_KEYWORDS.search(ln)]
    if hit_idx:
        lo = max(0, hit_idx[0] - 5)
        hi = min(len(lines), hit_idx[-1] + 6)
        lines = lines[lo:hi]

    out = "\n".join(lines)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out[:_SECTION_MAX_CHARS].strip()


def section_hash(membership_text: str) -> str:
    norm = re.sub(r"\s+", " ", membership_text).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
