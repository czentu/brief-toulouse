"""Termine le brief écrit par Claude : police intégrée, balises d'app iPhone,
publication dans docs/ (index + archives), puis notification ntfy."""
import base64, json, re, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

ICI = Path(__file__).resolve().parent
DOCS = ICI.parent / "docs"
ARCH = DOCS / "archives"
cfg = json.loads((ICI / "config.json").read_text(encoding="utf-8"))
m = json.loads((ICI / "moment.json").read_text(encoding="utf-8"))

src = DOCS / "brief-en-cours.html"
if not src.exists():
    sys.exit("ERREUR : docs/brief-en-cours.html n'existe pas, le brief n'a pas été écrit.")
html = src.read_text(encoding="utf-8")

police = base64.b64encode((ICI / "fraunces-latin-600-normal.woff2").read_bytes()).decode()
html = html.replace("__FRAUNCES__", police)

if not re.search(r"<base\s+target=", html):
    html = html.replace("</title>", '</title>\n<base target="_blank">', 1)

APP = """
<link rel="manifest" href="/{repo}/manifest.webmanifest">
<link rel="apple-touch-icon" href="/{repo}/icon-180.png">
<link rel="icon" type="image/png" href="/{repo}/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Brief">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="#F9F9F7">""".format(repo=cfg["repo"])
if 'rel="manifest"' not in html:
    html = html.replace('<base target="_blank">', '<base target="_blank">' + APP, 1)

PIED = ('\n<p style="text-align:center;font:13px -apple-system,Segoe UI,sans-serif;margin:0;padding:8px 0 40px">'
        f'<a target="_self" href="/{cfg["repo"]}/archives.html" style="color:#6B6A63">Briefs précédents</a></p>\n')
if "Briefs précédents" not in html:
    html = html.replace("</body>", PIED + "</body>", 1) if "</body>" in html else html + PIED

ARCH.mkdir(parents=True, exist_ok=True)
nom = f"brief-{m['date']}-{m['slug']}.html"
(ARCH / nom).write_text(html, encoding="utf-8")
(DOCS / "index.html").write_text(html, encoding="utf-8")

# archives : 30 jours, liste du plus récent au plus ancien
limite = date.today() - timedelta(days=30)
for f in ARCH.glob("brief-*.html"):
    try:
        if date.fromisoformat(f.name[6:16]) < limite:
            f.unlink()
    except ValueError:
        pass
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
lignes = []
for f in sorted(ARCH.glob("brief-*.html"), reverse=True):
    d = date.fromisoformat(f.name[6:16]); quand = "matin" if f.name.endswith("-matin.html") else "après-midi"
    lignes.append(f'<li><a href="archives/{f.name}">{d.day} {MOIS[d.month-1]} {d.year} · {quand}</a></li>')
(DOCS / "archives.html").write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Briefs précédents</title>
<link rel="apple-touch-icon" href="/{cfg['repo']}/icon-180.png"><meta name="apple-mobile-web-app-capable" content="yes">
<style>body{{margin:0;background:#F9F9F7;color:#2E2C27;font:16px -apple-system,Segoe UI,sans-serif}}
main{{max-width:600px;margin:0 auto;padding:48px 20px}}h1{{font-family:Georgia,serif;font-size:28px}}
ul{{list-style:none;padding:0}}li{{border-top:1px solid #E4E3DC}}a{{display:block;padding:14px 0;color:inherit;text-decoration:none}}
@media (prefers-color-scheme:dark){{body{{background:#1C1B19;color:#ECEAE3}}li{{border-color:#36352F}}}}</style></head>
<body><main><p><a href="./" style="display:inline;padding:0;color:#C6613F">← Dernier brief</a></p><h1>Briefs précédents</h1><ul>
{chr(10).join(lignes)}
</ul></main></body></html>""", encoding="utf-8")

resume_f = DOCS / "brief-en-cours.resume.txt"
resume = resume_f.read_text(encoding="utf-8").strip() if resume_f.exists() else "Ton brief est prêt."
src.unlink()
if resume_f.exists():
    resume_f.unlink()

(ICI / "notif.json").write_text(json.dumps({"titre": f"{m['moment']} prêt", "message": resume[:250], "fichier": nom},
                                           ensure_ascii=False), encoding="utf-8")
print(f"Publié : docs/index.html et docs/archives/{nom}")
