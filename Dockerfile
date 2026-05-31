# ── Base image ────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# ── Dépendances système nécessaires à Playwright/Chromium ─────────────────────
RUN apt-get update && apt-get install -y \
    # Chromium runtime deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libgtk-3-0 libx11-xcb1 libxcb-dri3-0 \
    # Utils
    wget ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── Workdir ────────────────────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright : install Chromium uniquement ───────────────────────────────────
RUN playwright install chromium

# ── Code source ───────────────────────────────────────────────────────────────
COPY tiktok_client.py .
COPY nisu_tiktok_autopromo.py .

# ── Cookies (montés via volume au runtime, pas copiés dans l'image) ────────────
# docker run -v $(pwd)/tt_8.json:/app/tt_8.json ...

# ── Entrypoint ────────────────────────────────────────────────────────────────
ENTRYPOINT ["python", "nisu_tiktok_autopromo.py"]
CMD ["--cookies", "tt_8.json", "--target", "50", "--delay", "15"]