#!/bin/sh
# yt-dlp breaks whenever YouTube changes, so refresh it on every start.
# A failed update keeps the version from the image.
pip install --quiet --no-cache-dir --upgrade yt-dlp || echo "yt-dlp-Update fehlgeschlagen"
exec python3 /app/main.py
