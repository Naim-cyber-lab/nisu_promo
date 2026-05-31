"""
nisu_tiktok_autopromo.py
========================
Scrolle le FYP TikTok, filtre les vidéos pertinentes pour Nisu
(sorties entre amis, activités Paris, activités originales, etc.)
et poste automatiquement un commentaire de promotion.

Usage :
    python nisu_tiktok_autopromo.py --cookies tt_8.json --target 50
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Import du client existant ──────────────────────────────────────────────────
from tiktok_client import TikTokClient


# ──────────────────────────────────────────────────────────────────────────────
# Historique des commentaires
# ──────────────────────────────────────────────────────────────────────────────

HISTORY_FILE = Path("nisu_comment_history.json")


def _load_history() -> dict:
    """Charge l'historique depuis le fichier JSON. Retourne un dict vide si absent."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_history(history: dict) -> None:
    """Sauvegarde l'historique dans le fichier JSON (indenté pour lisibilité)."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def already_commented(video_id: str, history: dict) -> bool:
    """Retourne True si on a déjà commenté cette vidéo."""
    return video_id in history


def record_comment(video_id: str, row: pd.Series, comment_text: str,
                   success: bool, history: dict) -> None:
    """Enregistre un commentaire (réussi ou non) dans l'historique en mémoire."""
    history[video_id] = {
        "video_id":        video_id,
        "url":             row.get("url", ""),
        "title":           row.get("title", ""),
        "hashtags":        row.get("hashtags", ""),
        "author_username": row.get("author_username", ""),
        "author_display":  row.get("author_display", ""),
        "comment":         comment_text,
        "success":         success,
        "commented_at":    datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Mots-clés de filtrage
# ──────────────────────────────────────────────────────────────────────────────

NISU_KEYWORDS = [
    # Sorties / amis
    "sortie", "soirée", "entre amis", "entre potes", "avec mes amis",
    "plan entre amis", "plan du week", "week-end", "weekend",
    "qu'est-ce qu'on fait", "on sait pas quoi faire",

    # Activités Paris
    "paris", "île-de-france", "idf", "intramuros",
    "activité à paris", "activité paris", "que faire à paris",
    "que faire ce week", "bons plans paris", "sortir à paris",
    "paris by night",

    # Activités originales / insolites
    "activité originale", "activité insolite", "activité sympa",
    "activité fun", "activité cool", "truc à faire",
    "idée sortie", "idée activité", "quoi faire",
    "escape game", "karting", "laser game", "bowling",
    "paint ball", "accrobranche", "paintball",
    "cours de cuisine", "atelier", "rooftop", "bar insolite",

    # Hashtags courants
    "#paris", "#sortirparis", "#sortie", "#activitéparis",
    "#parislife", "#bonsplans", "#bonplan", "#quoifaire",
    "#activités", "#weekend", "#entrecopains", "#entreamis",
    "#loisirs", "#idéesortie", "#soirée",
]

# Mis en minuscules pour la comparaison
NISU_KEYWORDS_LOWER = [k.lower() for k in NISU_KEYWORDS]


# ──────────────────────────────────────────────────────────────────────────────
# Filtrage
# ──────────────────────────────────────────────────────────────────────────────

def is_nisu_relevant(row: pd.Series) -> bool:
    """
    Retourne True si la vidéo est pertinente pour Nisu.
    Cherche les mots-clés dans le titre, les hashtags et la bio de l'auteur.
    """
    text = " ".join([
        str(row.get("title", "")),
        str(row.get("hashtags", "")),
        str(row.get("bio", "")),
    ]).lower()

    # Supprime les accents pour une meilleure correspondance
    text_normalized = _normalize(text)

    for kw in NISU_KEYWORDS_LOWER:
        kw_normalized = _normalize(kw)
        if kw_normalized in text_normalized:
            return True
    return False


def _normalize(s: str) -> str:
    """Normalise les accents et la ponctuation pour la comparaison."""
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
    }
    for accented, plain in replacements.items():
        s = s.replace(accented, plain)
    return s


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────────────────────

COMMENT_TEXT = "L'application Nisu pourrait t'intéresser ! 📍"


def run(cookies_file: str, target: int, delay: float, dry_run: bool):
    print("=" * 60)
    print("🚀 Nisu TikTok AutoPromo")
    print("=" * 60)

    # 1. Charger l'historique
    history = _load_history()
    print(f"📖 Historique chargé : {len(history)} vidéos déjà commentées")

    # 2. Créer le client
    client = TikTokClient.from_cookies(cookies_file)

    # 3. Vérifier la connexion
    if not client.check_login():
        print("❌ Connexion échouée. Vérifie tes cookies.")
        return

    # 4. Scraper le FYP
    print(f"\n📥 Scraping {target} vidéos du FYP…")
    df = client.scrape_fyp(target=target)
    print(f"✅ {len(df)} vidéos collectées")

    if df.empty:
        print("⚠️  Aucune vidéo collectée, arrêt.")
        return

    # 5. Filtrer les vidéos pertinentes
    print("\n🔍 Filtrage des vidéos pertinentes pour Nisu…")
    df["nisu_relevant"] = df.apply(is_nisu_relevant, axis=1)
    df_filtered = df[df["nisu_relevant"]].copy()
    print(f"✅ {len(df_filtered)}/{len(df)} vidéos retenues par les mots-clés")

    if df_filtered.empty:
        print("⚠️  Aucune vidéo pertinente trouvée.")
        return

    # 6. Exclure les vidéos déjà commentées
    df_filtered["already_done"] = df_filtered["video_id"].apply(
        lambda vid: already_commented(str(vid), history)
    )
    df_new = df_filtered[~df_filtered["already_done"]].copy()
    skipped = len(df_filtered) - len(df_new)
    if skipped:
        print(f"⏭️  {skipped} vidéo(s) ignorée(s) (déjà commentées)")
    print(f"🆕 {len(df_new)} nouvelle(s) vidéo(s) à commenter")

    if df_new.empty:
        print("✅ Rien de nouveau à commenter.")
        return

    # Aperçu
    print("\n📋 Vidéos à commenter :")
    for _, row in df_new.iterrows():
        print(f"  • @{row['author_username']} — {str(row['title'])[:70]}")
        if row.get("hashtags"):
            print(f"    Tags : {str(row['hashtags'])[:80]}")

    # 7. Poster les commentaires
    if dry_run:
        print(f"\n🧪 DRY RUN — commentaire qui aurait été posté : '{COMMENT_TEXT}'")
        print(f"   Sur {len(df_new)} vidéos (aucun commentaire réellement posté)")
        return

    print(f"\n💬 Envoi du commentaire sur {len(df_new)} vidéos…")
    nb_success = nb_fail = 0

    for i, (_, row) in enumerate(df_new.iterrows(), 1):
        video_id = str(row["video_id"])
        url = row["url"]
        print(f"\n[{i}/{len(df_new)}] {url}")
        try:
            ok = client.post_comment(url, COMMENT_TEXT)
            record_comment(video_id, row, COMMENT_TEXT, ok, history)
            _save_history(history)   # sauvegarde après chaque commentaire
            if ok:
                nb_success += 1
                print(f"  ✅ Commentaire enregistré dans l'historique")
            else:
                nb_fail += 1
                print(f"  ⚠️  Commentaire échoué (enregistré quand même)")
        except Exception as e:
            record_comment(video_id, row, COMMENT_TEXT, False, history)
            _save_history(history)
            nb_fail += 1
            print(f"  ❌ Erreur : {e}")

        if i < len(df_new):
            print(f"⏳ Attente {delay}s…")
            time.sleep(delay)

    print(f"\n📊 Résultat : {nb_success} ✅  {nb_fail} ❌  sur {len(df_new)} vidéos")
    print(f"📁 Historique mis à jour → {HISTORY_FILE}")


# ──────────────────────────────────────────────────────────────────────────────
# Point d'entrée CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nisu TikTok AutoPromo")
    parser.add_argument("--cookies", default="tt_8.json", help="Fichier de cookies TikTok")
    parser.add_argument("--target", type=int, default=50, help="Nombre de vidéos à scraper")
    parser.add_argument("--delay", type=float, default=15.0, help="Délai entre chaque commentaire (secondes)")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans poster de commentaires")
    args = parser.parse_args()

    run(
        cookies_file=args.cookies,
        target=args.target,
        delay=args.delay,
        dry_run=args.dry_run,
    )