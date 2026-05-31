"""
tiktok_client.py
================
Client TikTok orienté objet — scraping FYP + posting de commentaires.

Usage rapide :
    client = TikTokClient.from_cookies("tt_8.json")
    df = client.scrape_fyp(target=30)
    client.post_comment(df["url"].iloc[0], "Super vidéo ! 🔥")
"""

import asyncio
import json
import threading
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────────────────────────

SAMESITE_MAP = {
    "strict":         "Strict",
    "lax":            "Lax",
    "none":           "None",
    "no_restriction": "None",
    "unspecified":    "Lax",
    "":               "Lax",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

POPUP_SELECTORS = [
    'button:has-text("J\'ai compris")',
    'button:has-text("Pas maintenant")',
    'button:has-text("Terminé")',
    'button:has-text("Retourner sur TikTok")',
    '[data-e2e="modal-close-inner-button"]',
    '[data-e2e="cookie-banner-accept"]',
    'button:has-text("Accept")',
]

JS_REMOVE_OVERLAYS = """
() => {
    let n = 0;
    ['[class*="DivFixedBottomContainer"]','[class*="KeyboardShortcut"]',
     '[class*="shortcut"]','[class*="e1sleddd0"]'].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => { el.remove(); n++; });
    });
    return n;
}
"""


def _parse_count(val) -> int | None:
    if not val:
        return None
    try:
        val = str(val).strip().upper().replace(",", ".")
        if "M" in val:
            return int(float(val.replace("M", "")) * 1_000_000)
        if "K" in val:
            return int(float(val.replace("K", "")) * 1_000)
        return int(float(val))
    except ValueError:
        return None


def _run_async(coro):
    """Lance une coroutine dans un thread dédié avec ProactorEventLoop (Windows)."""
    result = {}

    def _worker():
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            result["data"] = loop.run_until_complete(coro)
        except Exception as exc:
            result["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    if "error" in result:
        raise result["error"]
    return result["data"]


# ──────────────────────────────────────────────────────────────────────────────
# CookieConverter
# ──────────────────────────────────────────────────────────────────────────────

class CookieConverter:
    """
    Convertit un fichier de cookies (J2TEAM, Cookie-Editor, etc.)
    au format attendu par Playwright (storage_state).
    """

    @staticmethod
    def convert(input_path: str, output_path: str | None = None) -> str:
        """
        Convertit `input_path` → `output_path` (format Playwright).
        Retourne le chemin du fichier converti.
        """
        input_path = Path(input_path)
        output_path = Path(output_path) if output_path else input_path.with_suffix("_pw.json")

        with open(input_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        cookies_raw = raw if isinstance(raw, list) else raw.get("cookies", [])
        pw_cookies = []

        for c in cookies_raw:
            raw_ss = str(c.get("sameSite") or c.get("same_site") or "").lower()
            pw_c = {
                "name":     c.get("name", c.get("key", "")),
                "value":    c.get("value", ""),
                "domain":   c.get("domain", ".tiktok.com"),
                "path":     c.get("path", "/"),
                "secure":   bool(c.get("secure", True)),
                "httpOnly": bool(c.get("httpOnly", c.get("http_only", False))),
                "sameSite": SAMESITE_MAP.get(raw_ss, "Lax"),
            }
            exp = c.get("expirationDate") or c.get("expires") or c.get("expiry")
            if exp and float(exp) > 0:
                pw_c["expires"] = float(exp)
            pw_cookies.append(pw_c)

        state = {"cookies": pw_cookies, "origins": []}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(state, f)

        has_session = any(c["name"] == "sessionid" for c in pw_cookies)
        print(f"✅ {len(pw_cookies)} cookies convertis → {output_path}")
        print(f"🔑 sessionid : {'présent' if has_session else '❌ ABSENT'}")
        return str(output_path)


# ──────────────────────────────────────────────────────────────────────────────
# TikTokClient
# ──────────────────────────────────────────────────────────────────────────────

class TikTokClient:
    """
    Client Playwright pour TikTok.

    Instanciation :
        # Depuis un fichier déjà au format Playwright :
        client = TikTokClient("tt_8_pw.json")

        # Depuis un fichier brut (J2TEAM / Cookie-Editor) :
        client = TikTokClient.from_cookies("tt_8.json")
    """

    def __init__(self, state_file: str):
        self.state_file = str(state_file)

    # ── Constructeur alternatif ───────────────────────────────────────────────

    @classmethod
    def from_cookies(cls, raw_cookie_file: str, output_file: str | None = None) -> "TikTokClient":
        """Convertit les cookies puis crée le client."""
        pw_file = CookieConverter.convert(raw_cookie_file, output_file)
        return cls(pw_file)

    # ── Contexte Playwright partagé ───────────────────────────────────────────

    async def _new_context(self, pw):
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            storage_state=self.state_file,
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
        )
        return browser, context

    # ── Fermeture des popups ──────────────────────────────────────────────────

    @staticmethod
    async def _close_popups(page) -> None:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        await page.evaluate(JS_REMOVE_OVERLAYS)
        for sel in POPUP_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.8)
            except Exception:
                pass

    # ── Vérification de connexion ─────────────────────────────────────────────

    def check_login(self) -> bool:
        """Retourne True si les cookies permettent une connexion."""
        async def _check():
            async with async_playwright() as pw:
                browser, context = await self._new_context(pw)
                page = await context.new_page()
                await page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
                await asyncio.sleep(4)
                logged_in = await page.evaluate(
                    "() => !document.querySelector('[data-e2e=\"top-login-button\"]') "
                    "|| !!document.querySelector('[data-e2e=\"nav-profile\"] img')"
                )
                cookies = await context.cookies()
                has_session = any(c["name"] == "sessionid" for c in cookies)
                await browser.close()
                return logged_in and has_session

        ok = _run_async(_check())
        print("✅ Connecté :" if ok else "❌ Non connecté :", ok)
        return ok

    # ── Scraping FYP ─────────────────────────────────────────────────────────

    def scrape_fyp(self, target: int = 30, pause: float = 2.0) -> pd.DataFrame:
        """
        Scrolle le For You Page et retourne un DataFrame.

        Paramètres
        ----------
        target : nombre de vidéos à collecter
        pause  : délai (secondes) entre chaque vidéo
        """
        data = _run_async(self._scrape_fyp_async(target, pause))
        return self._build_dataframe(data)

    async def _scrape_fyp_async(self, target: int, pause: float) -> list[dict]:
        collected: dict[str, dict] = {}

        async with async_playwright() as pw:
            browser, context = await self._new_context(pw)
            page = await context.new_page()

            # Intercepter les réponses API
            async def _on_response(response):
                try:
                    url = response.url
                    if any(k in url for k in ["recommend/item_list", "aweme/v1/feed", "/feed"]):
                        data = await response.json()
                        items = (
                            data.get("itemList")
                            or data.get("aweme_list")
                            or data.get("items")
                            or []
                        )
                        for it in items:
                            vid_id   = str(it.get("id") or it.get("aweme_id") or "")
                            author   = it.get("author") or {}
                            stats    = it.get("stats") or it.get("statistics") or {}
                            music    = it.get("music") or {}
                            video    = it.get("video") or {}
                            username = author.get("uniqueId") or author.get("unique_id") or ""
                            if vid_id and username and vid_id not in collected:
                                collected[vid_id] = {
                                    "video_id":        vid_id,
                                    "url":             f"https://www.tiktok.com/@{username}/video/{vid_id}",
                                    "title":           it.get("desc", ""),
                                    "author_username": username,
                                    "author_display":  author.get("nickname", ""),
                                    "profile_url":     f"https://www.tiktok.com/@{username}",
                                    "bio":             author.get("signature", ""),
                                    "likes":           stats.get("diggCount") or stats.get("digg_count") or 0,
                                    "comments":        stats.get("commentCount") or stats.get("comment_count") or 0,
                                    "shares":          stats.get("shareCount") or stats.get("share_count") or 0,
                                    "saves":           stats.get("collectCount") or stats.get("collect_count") or 0,
                                    "music":           music.get("title", ""),
                                    "hashtags":        " ".join(
                                        "#" + c.get("hashtagName", c.get("cha_name", ""))
                                        for c in it.get("challenges", it.get("cha_list", []))
                                    ),
                                    "duration":        video.get("duration", ""),
                                    "thumbnail":       video.get("cover", ""),
                                }
                                print(f"  ✚ [{len(collected):>3}/{target}] @{username} — {it.get('desc','')[:60]}")
                except Exception:
                    pass

            page.on("response", _on_response)

            print("🚀 Ouverture TikTok FYP…")
            await page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
            await asyncio.sleep(5)

            await self._close_popups(page)
            await page.mouse.click(640, 450)
            await asyncio.sleep(1)
            await self._close_popups(page)
            await page.mouse.click(640, 450)
            await asyncio.sleep(0.5)

            print(f"\n⬇️  Navigation ArrowDown…\n")
            step = stale = last_count = 0

            while len(collected) < target and step < target * 5:
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(pause)
                step += 1

                if len(collected) == last_count:
                    stale += 1
                    if stale % 5 == 0:
                        await self._close_popups(page)
                        await page.mouse.click(640, 450)
                    if stale == 20:
                        await page.screenshot(path="tiktok_stuck.png")
                        print("⚠️  Bloqué — screenshot : tiktok_stuck.png")
                else:
                    stale = 0
                    last_count = len(collected)

            print(f"\n✅ {len(collected)} vidéos collectées en {step} steps")
            await browser.close()

        return list(collected.values())

    @staticmethod
    def _build_dataframe(data: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(data)
        if df.empty:
            print("⚠️ Aucune vidéo collectée.")
            return df
        for col in ["likes", "comments", "shares", "saves"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        cols = [
            "video_id", "url", "title", "hashtags",
            "author_username", "author_display", "profile_url", "bio",
            "likes", "comments", "shares", "saves",
            "music", "duration", "thumbnail",
        ]
        return df[[c for c in cols if c in df.columns]]

    # ── Post commentaire ──────────────────────────────────────────────────────

    def post_comment(self, video_url: str, comment_text: str) -> bool:
        """
        Poste un commentaire sur une vidéo TikTok.

        Paramètres
        ----------
        video_url    : URL de la vidéo
        comment_text : Texte à poster

        Retourne True si succès.
        """
        return _run_async(self._post_comment_async(video_url, comment_text))

    async def _post_comment_async(self, video_url: str, comment_text: str) -> bool:
        async with async_playwright() as pw:
            browser, context = await self._new_context(pw)
            page = await context.new_page()

            print(f"🚀 Ouverture : {video_url}")
            await page.goto(video_url, wait_until="networkidle")
            await asyncio.sleep(4)

            await self._close_popups(page)

            # Ouvrir le panel commentaires
            print("💬 Ouverture des commentaires…")
            for sel in ['[data-e2e="comment-icon"]', '[data-e2e="comment-count"]']:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.click()
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass

            await page.evaluate(JS_REMOVE_OVERLAYS)

            # Trouver la zone de saisie
            print("🔍 Recherche zone de commentaire…")
            comment_box = None
            for sel in [
                '[data-e2e="comment-input"]',
                'div[contenteditable="true"]',
                'div[placeholder*="Ajoute"]',
                'div[placeholder*="comment"]',
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        comment_box = el
                        print(f"  ✅ Zone : {sel}")
                        break
                except Exception:
                    pass

            if not comment_box:
                await page.screenshot(path="comment_debug.png")
                print("❌ Zone introuvable — voir comment_debug.png")
                await browser.close()
                return False

            # Écrire via JS click + keyboard.type
            print(f"✍️  Écriture : '{comment_text}'")
            await page.evaluate("el => el.click()", comment_box)
            await asyncio.sleep(0.5)
            await page.keyboard.type(comment_text, delay=50)
            await asyncio.sleep(1)

            # Soumettre
            submitted = False
            for sel in [
                '[data-e2e="comment-post"]',
                'button:has-text("Publier")',
                'span:has-text("Publier")',
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await page.evaluate("el => el.click()", btn)
                        submitted = True
                        print(f"  ✅ Soumis via : {sel}")
                        break
                except Exception:
                    pass

            if not submitted:
                print("  ↩️  Fallback : Enter")
                await page.keyboard.press("Enter")

            await asyncio.sleep(3)
            await page.screenshot(path="comment_result.png")
            print("✅ Commentaire posté ! → comment_result.png")
            await browser.close()
            return True

    # ── Poster sur plusieurs vidéos ───────────────────────────────────────────

    def post_comments_bulk(
        self,
        urls: list[str],
        comment_text: str,
        delay: float = 10.0,
    ) -> pd.DataFrame:
        """
        Poste le même commentaire sur une liste de vidéos.

        Paramètres
        ----------
        urls         : liste d'URLs TikTok
        comment_text : texte à poster
        delay        : délai (secondes) entre chaque post

        Retourne un DataFrame avec les résultats (url, success).
        """
        import time
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] {url}")
            try:
                ok = self.post_comment(url, comment_text)
                results.append({"url": url, "success": ok, "error": None})
            except Exception as e:
                results.append({"url": url, "success": False, "error": str(e)})
            if i < len(urls):
                print(f"⏳ Attente {delay}s avant la prochaine…")
                time.sleep(delay)
        df = pd.DataFrame(results)
        print(f"\n📊 {df['success'].sum()}/{len(df)} commentaires postés avec succès")
        return df