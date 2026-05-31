# Nisu Comm

Automatisation TikTok orientee prospection locale : le projet scrolle le FYP, detecte les videos pertinentes pour Nisu, puis commente automatiquement (ou en simulation).

## Pourquoi ce projet

- Gagner du temps sur la prospection organique TikTok.
- Cibler des contenus lies aux sorties, activites et plans a Paris.
- Eviter les doublons grace a un historique local des commentaires deja tentes.

## Fonctionnalites

- Conversion de cookies TikTok vers le format Playwright.
- Verification de session avant execution.
- Scraping FYP avec extraction de metadonnees (titre, hashtags, stats, auteur, URL).
- Filtrage par mots-cles metier Nisu.
- Publication de commentaires unitaire ou en lot.
- Mode `--dry-run` pour tester sans poster.

## Demarrage rapide (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Run de test (aucun commentaire envoye) :

```powershell
python .\nisu_promo.py --cookies tt_8.json --target 50 --dry-run
```

Run reel :

```powershell
python .\nisu_promo.py --cookies tt_8.json --target 50 --delay 15
```

## Classe `TikTokClient` en bref

La classe `TikTokClient` dans `tiktok_client.py` encapsule toute la couche Playwright.

Constructeurs :

```python
from tiktok_client import TikTokClient

client = TikTokClient("tt_8_pw.json")
# ou
client = TikTokClient.from_cookies("tt_8.json")
```

Methodes principales :
- `check_login()` : valide la session TikTok active.
- `scrape_fyp(target, pause)` : recupere un DataFrame de videos du FYP.
- `post_comment(video_url, comment_text)` : poste un commentaire sur une video.
- `post_comments_bulk(urls, comment_text, delay)` : publication en serie avec delai.

## Structure du projet

```text
nisu_comm/
|- Dockerfile
|- main.py
|- nisu_ai.ipynb
|- nisu_promo.py
|- tiktok_client.py
|- requirements.txt
|- tt_8.json
|- tt_8_pw.json
|- README.md
`- docs/
   `- README_TECHNIQUE.md
```

## Documentation complete

Pour la doc technique detaillee (pipeline complet, methodes internes, fichiers generes, limites), consulte :
- `docs/README_TECHNIQUE.md`

## Points d'attention

- Les cookies TikTok expirent : regenerer `tt_8.json` si `check_login()` echoue.
- Les selecteurs TikTok peuvent casser avec les evolutions du site.
- Ne pas versionner les fichiers de cookies en public.
- Verifier le `Dockerfile` avant execution si vous utilisez Docker.

## Licence et usage

Projet interne/experimental. Adapter les usages aux conditions TikTok et a votre cadre legal.
