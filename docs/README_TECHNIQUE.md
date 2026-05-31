# Nisu Comm - Documentation technique

Ce document detaille l'implementation du projet et complete le README principal.

## 1) Vue d'ensemble

Le projet automatise un pipeline TikTok :
1. conversion des cookies au format Playwright,
2. verification de session,
3. scraping de videos sur le FYP,
4. filtrage des videos pertinentes pour Nisu,
5. publication de commentaires (ou simulation),
6. sauvegarde d'un historique JSON.

Composants principaux :
- `tiktok_client.py` : couche d'acces TikTok (Playwright)
- `nisu_promo.py` : orchestration metier Nisu
- `requirements.txt` : dependances Python

## 2) Fichiers et roles

- `tiktok_client.py`
  - `CookieConverter` : convertit des cookies bruts en `storage_state` Playwright
  - `TikTokClient` : scraping FYP + publication de commentaires
- `nisu_promo.py`
  - charge l'historique (`nisu_comment_history.json`)
  - filtre via `NISU_KEYWORDS`
  - evite les doublons de commentaire
  - pilote les runs CLI (`--dry-run`, `--target`, `--delay`)
- `tt_8.json`
  - cookies bruts TikTok (sensible, ne pas versionner)
- `tt_8_pw.json`
  - cookies convertis, generes localement

## 3) Classe `TikTokClient`

### Construction

```python
from tiktok_client import TikTokClient

# 1) Etat Playwright deja pret
client = TikTokClient("tt_8_pw.json")

# 2) Conversion automatique depuis cookies bruts
client = TikTokClient.from_cookies("tt_8.json")
```

### API publique

#### `check_login() -> bool`
- ouvre `https://www.tiktok.com/foryou`
- detecte les marqueurs de session connectee
- verifie la presence du cookie `sessionid`

#### `scrape_fyp(target=30, pause=2.0) -> pandas.DataFrame`
- scrolle le FYP avec `ArrowDown`
- intercepte les reponses API feed
- dedoublonne les videos par `video_id`
- retourne un DataFrame structure

Colonnes standard :
- `video_id`, `url`, `title`, `hashtags`
- `author_username`, `author_display`, `profile_url`, `bio`
- `likes`, `comments`, `shares`, `saves`
- `music`, `duration`, `thumbnail`

#### `post_comment(video_url, comment_text) -> bool`
- ouvre la video
- ferme popups / overlays
- cible la zone de commentaire
- soumet via bouton `Publier` (fallback `Enter`)

#### `post_comments_bulk(urls, comment_text, delay=10.0) -> pandas.DataFrame`
- enchaine `post_comment` sur une liste d'URL
- applique un delai entre chaque tentative
- retourne un DataFrame (`url`, `success`, `error`)

### Methodes internes utiles

- `_new_context(...)` : creation browser/contexte avec `storage_state`
- `_close_popups(page)` : gestion de modales TikTok
- `_scrape_fyp_async(...)` : logique de collecte feed
- `_post_comment_async(...)` : logique de publication
- `_run_async(coro)` : execution async dans thread dedie (Windows)

## 4) Pipeline `nisu_promo.py`

Etapes du run :
1. charger l'historique JSON,
2. creer `TikTokClient` via cookies,
3. verifier la connexion,
4. scraper `target` videos,
5. filtrer par pertinence (`is_nisu_relevant`),
6. retirer celles deja commentees,
7. commenter (ou simuler),
8. enregistrer chaque tentative dans l'historique.

Constante metier :

```python
COMMENT_TEXT = "L'application Nisu pourrait t'interesser !"
```

## 5) Commandes de base (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Dry run :

```powershell
python .\nisu_promo.py --cookies tt_8.json --target 50 --dry-run
```

Run reel :

```powershell
python .\nisu_promo.py --cookies tt_8.json --target 50 --delay 15
```

## 6) Fichiers generes en execution

- `nisu_comment_history.json` : historique des tentatives
- `comment_debug.png` : debug publication commentaire
- `comment_result.png` : capture apres soumission
- `tiktok_stuck.png` : capture en cas de blocage scraping

## 7) Limites connues

- Le DOM TikTok change souvent : certains selecteurs peuvent casser.
- Les cookies expirent : necessite un nouvel export regulier.
- Le client est en `headless=False` dans `tiktok_client.py`.
- L'automatisation de commentaires est soumise aux politiques TikTok.

## 8) Note Docker

Le `Dockerfile` existe, mais verifier les noms de scripts copies/executes avant build, car le code actif est dans `nisu_promo.py`.


