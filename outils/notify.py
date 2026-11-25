"""Après le push : attend que GitHub Pages serve le nouveau brief (3 min max),
puis envoie la notification ntfy qui ouvre l'app au toucher."""
import json, time, urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
cfg = json.loads((ICI / "config.json").read_text(encoding="utf-8"))
n = json.loads((ICI / "notif.json").read_text(encoding="utf-8"))

url = cfg["site_url"].rstrip("/") + "/archives.html"
for _ in range(18):
    try:
        req = urllib.request.Request(f"{url}?t={time.time()}", headers={"Cache-Control": "no-cache"})
        if n["fichier"] in urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace"):
            print("Site à jour."); break
    except Exception as e:
        print(f"Site pas encore joignable : {e}")
    time.sleep(10)

data = json.dumps({"topic": cfg["ntfy_topic"], "title": n["titre"], "message": n["message"],
                   "click": cfg["site_url"], "tags": ["sunrise"]}).encode()
try:
    urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/", data=data,
                           headers={"Content-Type": "application/json"}), timeout=20).read()
    print("Notification envoyée.")
except Exception as e:
    print(f"Notification impossible : {e}")
