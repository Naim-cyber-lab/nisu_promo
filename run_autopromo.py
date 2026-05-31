"""
run_autopromo.py
================
Lance un run complet :
  1. Scrape le FYP TikTok
  2. Filtre les videos pertinentes pour Nisu
  3. Poste un commentaire : "Telecharge Nisu !"
  4. Sauvegarde les URLs commentees dans une base SQLite (nisu_db.sqlite)

Usage :
    python run_autopromo.py
    python run_autopromo.py --target 30 --delay 12 --dry-run
"""

import argparse
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from tiktok_client import TikTokClient

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

COOKIES_FILE  = "tt_8.json"          # fichier de cookies TikTok bruts
COMMENT_TEXT  = "Telecharge Nisu !"  # commentaire a poster
DB_PATH       = Path("nisu_db.sqlite")

# ──────────────────────────────────────────────────────────────────────────────
# Mots-cles de filtrage (memes que nisu_promo.py)
# ──────────────────────────────────────────────────────────────────────────────

NISU_KEYWORDS = [
    "sortie", "soiree", "entre amis", "entre potes", "avec mes amis",
    "plan entre amis", "plan du week", "week-end", "weekend",
    "qu'est-ce qu'on fait", "on sait pas quoi faire",
    "paris", "ile-de-france", "idf", "intramuros",
    "activite a paris", "activite paris", "que faire a paris",
    "que faire ce week", "bons plans paris", "sortir a paris",
    "paris by night",
    "activite originale", "activite insolite", "activite sympa",
    "activite fun", "activite cool", "truc a faire",
    "idee sortie", "idee activite", "quoi faire",
    "escape game", "karting", "laser game", "bowling",
    "paint ball", "accrobranche", "paintball",
    "cours de cuisine", "atelier", "rooftop", "bar insolite",
    "#paris", "#sortirparis", "#sortie", "#activiteparis",
    "#parislife", "#bonsplans", "#bonplan", "#quoifaire",
    "#activites", "#weekend", "#entrecopains", "#entreamis",
    "#loisirs", "#ideedesortie", "#soiree",
]

KEYWORDS_LOWER = [k.lower() for k in NISU_KEYWORDS]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Supprime les accents pour une comparaison plus souple."""
    for src, dst in [
        ("é","e"),("è","e"),("ê","e"),("ë","e"),
        ("à","a"),("â","a"),("ä","a"),
        ("î","i"),("ï","i"),
        ("ô","o"),("ö","o"),
        ("ù","u"),("û","u"),("ü","u"),
        ("ç","c"),
    ]:
        s = s.replace(src, dst)
    return s


def is_relevant(row) -> bool:
    """Retourne True si la video correspond a un critere Nisu."""
    text = _normalize(" ".join([
        str(row.get("title", "")),
        str(row.get("hashtags", "")),
        str(row.get("bio", "")),
    ]).lower())
    return any(kw in text for kw in KEYWORDS_LOWER)


# ──────────────────────────────────────────────────────────────────────────────
# Base de donnees SQLite
# ──────────────────────────────────────────────────────────────────────────────

def init_db(db_path: Path) -> sqlite3.Connection:
    """Cree la base et la table si elle n'existent pas encore."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commented_videos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id      TEXT    UNIQUE NOT NULL,
            url           TEXT    NOT NULL,
            title         TEXT,
            hashtags      TEXT,
            author        TEXT,
            comment_text  TEXT,
            success       INTEGER,
            commented_at  TEXT
        )
    """)
    conn.commit()
    return conn


def already_in_db(conn: sqlite3.Connection, video_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM commented_videos WHERE video_id = ?", (video_id,)
    ).fetchone()
    return row is not None


def save_to_db(conn: sqlite3.Connection, row, comment: str, success: bool) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO commented_videos
            (video_id, url, title, hashtags, author, comment_text, success, commented_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(row.get("video_id", "")),
        str(row.get("url", "")),
        str(row.get("title", "")),
        str(row.get("hashtags", "")),
        str(row.get("author_username", "")),
        comment,
        int(success),
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────────────────────

def run(cookies_file: str, target: int, delay: float, dry_run: bool) -> None:
    sep = "=" * 60
    print(sep)
    print("  Nisu AutoPromo — run_autopromo.py")
    print(sep)

    # 1. Base de donnees
    conn = init_db(DB_PATH)
    already_done_total = conn.execute("SELECT COUNT(*) FROM commented_videos").fetchone()[0]
    print(f"📦 Base de donnees : {DB_PATH}  ({already_done_total} entrees existantes)")

    # 2. Client TikTok
    print(f"\n🔑 Chargement des cookies : {cookies_file}")
    client = TikTokClient.from_cookies(cookies_file)

    # 3. Verification de la session
    print("🔍 Verification de la connexion…")
    if not client.check_login():
        print("❌ Session invalide. Exporte de nouveaux cookies depuis Cookie-Editor.")
        conn.close()
        return

    # 4. Scraping FYP
    print(f"\n📥 Scraping du FYP ({target} videos)…")
    df = client.scrape_fyp(target=target)
    print(f"✅ {len(df)} videos collectees")

    if df.empty:
        print("⚠️  Aucune video collectee, arret.")
        conn.close()
        return

    # 5. Filtrage
    print("\n🔍 Filtrage des videos pertinentes pour Nisu…")
    df["relevant"] = df.apply(is_relevant, axis=1)
    df_ok = df[df["relevant"]].copy()
    print(f"✅ {len(df_ok)}/{len(df)} videos retenues")

    if df_ok.empty:
        print("⚠️  Aucune video pertinente, arret.")
        conn.close()
        return

    # 6. Exclusion des videos deja traitees
    df_ok["done"] = df_ok["video_id"].apply(lambda vid: already_in_db(conn, str(vid)))
    df_new = df_ok[~df_ok["done"]].copy()
    skipped = len(df_ok) - len(df_new)
    if skipped:
        print(f"⏭️  {skipped} video(s) ignoree(s) (deja dans la base)")
    print(f"🆕 {len(df_new)} nouvelle(s) video(s) a commenter")

    if df_new.empty:
        print("✅ Rien de nouveau a commenter.")
        conn.close()
        return

    # Apercu
    print("\n📋 Videos ciblees :")
    for _, row in df_new.iterrows():
        print(f"   • @{row['author_username']}  {str(row['title'])[:70]}")
        print(f"     {row['url']}")

    # 7. Commentaires
    if dry_run:
        print(f"\n🧪 DRY RUN — commentaire : '{COMMENT_TEXT}'")
        print(f"   {len(df_new)} videos auraient ete commentees (rien n'est poste).")
        conn.close()
        return

    print(f"\n💬 Envoi du commentaire sur {len(df_new)} video(s)…")
    nb_ok = nb_fail = 0

    for i, (_, row) in enumerate(df_new.iterrows(), 1):
        video_id = str(row["video_id"])
        url      = str(row["url"])
        print(f"\n[{i}/{len(df_new)}] {url}")

        try:
            success = client.post_comment(url, COMMENT_TEXT)
        except Exception as exc:
            print(f"  ❌ Erreur : {exc}")
            success = False

        save_to_db(conn, row, COMMENT_TEXT, success)

        if success:
            nb_ok += 1
            print(f"  ✅ Commentaire poste + URL enregistree dans {DB_PATH}")
        else:
            nb_fail += 1
            print(f"  ⚠️  Echec du commentaire (URL enregistree quand meme)")

        if i < len(df_new):
            print(f"  ⏳ Attente {delay}s…")
            time.sleep(delay)

    print(f"\n{sep}")
    print(f"  Resultat : {nb_ok} ✅   {nb_fail} ❌   sur {len(df_new)} videos")
    print(f"  Base de donnees mise a jour : {DB_PATH}")
    print(sep)
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Entree CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nisu AutoPromo TikTok")
    parser.add_argument("--cookies", default=COOKIES_FILE,
                        help=f"Fichier cookies TikTok (defaut : {COOKIES_FILE})")
    parser.add_argument("--target",  type=int,   default=50,
                        help="Nombre de videos a scraper (defaut : 50)")
    parser.add_argument("--delay",   type=float, default=15.0,
                        help="Delai entre commentaires en secondes (defaut : 15)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule sans poster ni enregistrer de commentaires")
    args = parser.parse_args()

    run(
        cookies_file=args.cookies,
        target=args.target,
        delay=args.delay,
        dry_run=args.dry_run,
    )

