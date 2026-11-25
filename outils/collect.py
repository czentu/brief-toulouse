"""Récupère les données du brief (météo, air, actus, marchés, carburant)
et écrit la consigne du jour pour Claude : outils/consigne-du-jour.md.
Python 3, bibliothèque standard uniquement."""
import json, re, sys, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pas de base de fuseaux : heure d'hiver par défaut
    PARIS = timezone(timedelta(hours=1))

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
NOW = datetime.now(PARIS)
UA = {"User-Agent": "Mozilla/5.0 (brief)"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
journal = []


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fr(x, d=2):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def hfr(t):
    return f"{JOURS_COURTS[t.weekday()]} {t.day:02d} {t.hour:02d}h"


# --- Météo Open-Meteo -------------------------------------------------------
def meteo():
    u = ("https://api.open-meteo.com/v1/forecast?latitude=43.6047&longitude=1.4442"
         "&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,"
         "wind_speed_10m,wind_gusts_10m,wind_direction_10m"
         "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max,"
         "precipitation_sum,sunrise,sunset&timezone=Europe%2FParis&forecast_days=2&wind_speed_unit=kmh")
    try:
        r = json.loads(get(u)); d = r["daily"]; h = r["hourly"]
        lines = []
        for i in range(2):
            lines.append(f"Jour {d['time'][i]} : min {d['temperature_2m_min'][i]} C, max {d['temperature_2m_max'][i]} C, "
                         f"pluie max {d['precipitation_probability_max'][i]} %, cumul {d['precipitation_sum'][i]} mm, "
                         f"lever {d['sunrise'][i][11:]}, coucher {d['sunset'][i][11:]}")
        lines.append("Heure | temp C | proba pluie % | pluie mm | vent km/h | rafales km/h | direction vent deg | code WMO")
        start = NOW.replace(tzinfo=None) - timedelta(hours=1)
        end = NOW.replace(tzinfo=None, hour=0, minute=0, second=0) + timedelta(days=1, hours=21)
        for i, ts in enumerate(h["time"]):
            t = datetime.fromisoformat(ts)
            if t < start or t > end or t.hour < 6:
                continue
            lines.append(f"{hfr(t)} | {h['temperature_2m'][i]} | {h['precipitation_probability'][i]} | {h['precipitation'][i]} | "
                         f"{h['wind_speed_10m'][i]} | {h['wind_gusts_10m'][i]} | {h['wind_direction_10m'][i]} | {h['weather_code'][i]}")
        return "\n".join(lines)
    except Exception as e:
        journal.append(f"Open-Meteo indisponible : {e}")
        return "Indisponible : cherche la météo sur le web (Météo-France et une autre source reconnue)."


# --- Qualité de l'air --------------------------------------------------------
def air():
    u = ("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=43.6047&longitude=1.4442"
         "&hourly=european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide&timezone=Europe%2FParis&forecast_days=2")
    try:
        h = json.loads(get(u))["hourly"]
        lines = ["Indice europeen : 0-20 bon, 20-40 correct, 40-60 moyen, 60-80 mediocre, 80-100 tres mauvais, plus de 100 extremement mauvais",
                 "Heure | indice europeen | PM2.5 ug/m3 | PM10 ug/m3 | ozone ug/m3 | NO2 ug/m3"]
        now = NOW.replace(tzinfo=None)
        for i, ts in enumerate(h["time"]):
            t = datetime.fromisoformat(ts)
            if t < now - timedelta(hours=1) or t > now + timedelta(hours=18) or t.hour % 2:
                continue
            lines.append(f"{hfr(t)} | {h['european_aqi'][i]} | {h['pm2_5'][i]} | {h['pm10'][i]} | {h['ozone'][i]} | {h['nitrogen_dioxide'][i]}")
        return "\n".join(lines)
    except Exception as e:
        journal.append(f"Qualité de l'air indisponible : {e}")
        return "Indisponible : retire le bloc qualite de l'air."


# --- Flux RSS ----------------------------------------------------------------
GROUPES = {
    "GENERAL (France et monde)": [
        ("franceinfo", "https://www.francetvinfo.fr/titres.rss", 30, 20),
        ("Le Monde", "https://www.lemonde.fr/rss/une.xml", 30, 15),
        ("France 24", "https://www.france24.com/fr/rss", 30, 15),
        ("franceinfo monde", "https://www.francetvinfo.fr/monde.rss", 30, 10),
        ("RFI", "https://www.rfi.fr/fr/rss", 30, 10),
        ("Le Monde international", "https://www.lemonde.fr/international/rss_full.xml", 30, 10)],
    "SPORT": [
        ("L'Equipe", "https://dwh.lequipe.fr/api/edito/rss?path=/", 30, 25),
        ("franceinfo sports", "https://www.francetvinfo.fr/sports.rss", 30, 10)],
    "SCIENCES": [
        ("Sciences et Avenir", "https://www.sciencesetavenir.fr/rss.xml", 168, 15),
        ("Le Monde sciences", "https://www.lemonde.fr/sciences/rss_full.xml", 168, 10),
        ("franceinfo sciences", "https://www.francetvinfo.fr/sciences.rss", 168, 10),
        ("Le Figaro sciences", "https://www.lefigaro.fr/rss/figaro_sciences.xml", 168, 12),
        ("Le Journal du CNRS", "https://lejournal.cnrs.fr/rss", 168, 8),
        ("BBC science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", 168, 12),
        ("NASA", "https://www.nasa.gov/news-release/feed/", 168, 8)],
    "ECONOMIE": [
        ("Le Monde economie", "https://www.lemonde.fr/economie/rss_full.xml", 72, 12),
        ("franceinfo economie", "https://www.francetvinfo.fr/economie.rss", 72, 12)],
    "IA ET TECH": [
        ("01net", "https://www.01net.com/actualites/feed/", 168, 15),
        ("Le Monde Pixels", "https://www.lemonde.fr/pixels/rss_full.xml", 168, 10),
        ("MIT Technology Review", "https://www.technologyreview.com/feed/", 168, 12),
        ("Le Monde IA", "https://www.lemonde.fr/intelligence-artificielle/rss_full.xml", 168, 15),
        ("BBC tech", "https://feeds.bbci.co.uk/news/technology/rss.xml", 168, 12)],
    "ESPACE ET AERONAUTIQUE": [
        ("La Depeche aeronautique", "https://www.ladepeche.fr/economie/aeronautique/rss.xml", 120, 15),
        ("Sciences et Avenir espace", "https://www.sciencesetavenir.fr/espace/rss.xml", 168, 10),
        ("franceinfo espace", "https://www.francetvinfo.fr/sciences/espace.rss", 168, 10),
        ("Space.com", "https://www.space.com/feeds/all", 72, 15)],
    "SANTE": [
        ("franceinfo sante", "https://www.francetvinfo.fr/sante.rss", 120, 12),
        ("Le Monde sante", "https://www.lemonde.fr/sante/rss_full.xml", 120, 10),
        ("Le Figaro sante", "https://www.lefigaro.fr/rss/figaro_sante.xml", 120, 10)],
    "CULTURE (cinema, musique, livres)": [
        ("Le Monde cinema", "https://www.lemonde.fr/cinema/rss_full.xml", 72, 10),
        ("Le Monde musiques", "https://www.lemonde.fr/musiques/rss_full.xml", 72, 10),
        ("Le Monde livres", "https://www.lemonde.fr/livres/rss_full.xml", 120, 10),
        ("franceinfo culture", "https://www.francetvinfo.fr/culture.rss", 48, 15)],
    "TOULOUSE (pour les expositions)": [
        ("La Depeche Toulouse", "https://www.ladepeche.fr/communes/toulouse,31555.rss", 72, 25),
        ("France 3 Toulouse", "https://france3-regions.francetvinfo.fr/occitanie/haute-garonne/toulouse/rss", 72, 25)],
}


def texte(el, tag):
    x = el.find(tag)
    return "".join(x.itertext()).strip() if x is not None else ""


def flux(nom, url, age_max, n_max):
    out = []
    try:
        root = ET.fromstring(get(url))
        for it in root.iter("item"):
            titre, lien = texte(it, "title"), texte(it, "link")
            desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texte(it, "description"))).strip()
            if len(desc) > 220:
                desc = desc[:220] + "..."
            quand = "?"
            pd = texte(it, "pubDate")
            if pd:
                try:
                    dt = parsedate_to_datetime(pd).astimezone(PARIS)
                    if dt < NOW - timedelta(hours=age_max):
                        continue
                    quand = dt.strftime("%d/%m %H:%M")
                except Exception:
                    pass
            out.append(f"- [{nom}] {quand} | {titre} | {lien} | {desc}")
            if len(out) >= n_max:
                break
    except Exception as e:
        journal.append(f"Flux indisponible ({nom}) : {e}")
    return out


def actus():
    lines, n = [], 0
    for g, feeds in GROUPES.items():
        lines.append(f"### {g}")
        for f in feeds:
            items = flux(*f); n += len(items); lines += items
        lines.append("")
    journal.append(f"Flux RSS : {n} articles")
    return "\n".join(lines)


# --- Marchés (Yahoo Finance) ---------------------------------------------------
def marches():
    lines = ["Valeur | dernier cours | variation vs cloture precedente | heure du cours | source"]
    for nom, sym, src in [
        ("CAC 40", "^FCHI", "https://www.boursorama.com/bourse/indices/cours/1rPCAC/"),
        ("S&P 500", "^GSPC", "https://www.boursorama.com/bourse/indices/cours/%24INX/"),
        ("Nasdaq", "^IXIC", "https://www.boursorama.com/bourse/indices/cours/%24COMPX/"),
        ("Euro / dollar", "EURUSD=X", "https://www.boursorama.com/bourse/devises/taux-de-change-euro-dollar-EUR-USD/"),
        ("Brent", "BZ=F", "https://www.boursorama.com/bourse/matieres-premieres/cours/8xBRN/"),
        ("Bitcoin", "BTC-USD", "https://www.coindesk.com/price/bitcoin")]:
        try:
            r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=10d&interval=1d"))
            res = r["chart"]["result"][0]; m = res["meta"]
            last = float(m["regularMarketPrice"])
            lt = datetime.fromtimestamp(int(m["regularMarketTime"]), PARIS)
            prev = None
            closes = res["indicators"]["quote"][0]["close"]
            for ts, c in reversed(list(zip(res["timestamp"], closes))):
                if datetime.fromtimestamp(int(ts), PARIS).date() < lt.date() and c:
                    prev = float(c); break
            chg = (f"{(last - prev) / prev * 100:+.2f} %".replace(".", ",")) if prev else "?"
            lines.append(f"{nom} | {fr(last)} | {chg} | {lt.strftime('%d/%m %H:%M')} | {src}")
        except Exception as e:
            lines.append(f"{nom} | indisponible | | | {src}")
            journal.append(f"Cours indisponible ({nom}) : {e}")
    return "\n".join(lines)


# --- Carburant (SP95-E10, Toulouse) -------------------------------------------
def carburant():
    u = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records?where="
         + urllib.parse.quote('ville="Toulouse"') + "&limit=100")
    try:
        st = json.loads(get(u, 40))["results"]
        rows = []
        for s in st:
            v = s.get("e10_prix")
            if v in (None, ""):
                continue
            rows.append((float(str(v).replace(",", ".")), s.get("adresse", ""), str(s.get("e10_maj", ""))))
        if not rows:
            raise ValueError("aucun prix E10")
        rows.sort()
        avg = sum(r[0] for r in rows) / len(rows)
        maj = max(r[2] for r in rows)
        out = [f"{len(st)} stations a Toulouse. Carburant | prix moyen | moins cher | adresse la moins chere | nombre de stations | mise a jour la plus recente",
               f"SP95-E10 | {fr(avg, 3)} EUR/L | {fr(rows[0][0], 3)} EUR/L | {rows[0][1]} | {len(rows)} | {maj}",
               "Les 3 stations les moins cheres : " + " ; ".join(f"{fr(p, 3)} EUR/L, {a}" for p, a, _ in rows[:3]),
               f"La plus chere : {fr(rows[-1][0], 3)} EUR/L, {rows[-1][1]}"]
        return "\n".join(out)
    except Exception as e:
        journal.append(f"Prix des carburants indisponibles : {e}")
        return "Indisponible : retire la section carburant."


def main():
    matin = NOW.hour < 16
    moment = "Brief du matin" if matin else "Brief de l’après-midi"
    slug = "matin" if matin else "apres-midi"
    date_txt = f"{JOURS[NOW.weekday()]} {NOW.day} {MOIS[NOW.month - 1]} {NOW.year}"
    fichier = RACINE / "docs" / "brief-en-cours.html"
    resume = RACINE / "docs" / "brief-en-cours.resume.txt"
    tpl = (ICI / "consigne-modele.md").read_text(encoding="utf-8")
    c = (tpl.replace("{{MOMENT}}", moment).replace("{{DATE}}", date_txt)
         .replace("{{HEURE}}", NOW.strftime("%H:%M")).replace("{{FICHIER}}", str(fichier))
         .replace("{{RESUME}}", str(resume)).replace("{{METEO}}", meteo()).replace("{{AIR}}", air())
         .replace("{{ACTUS}}", actus()).replace("{{MARCHES}}", marches()).replace("{{CARBURANT}}", carburant())
         .replace("{{MODELE}}", str(ICI / "modele.html")))
    (ICI / "consigne-du-jour.md").write_text(c, encoding="utf-8")
    (ICI / "moment.json").write_text(json.dumps({"moment": moment, "slug": slug, "date": NOW.strftime("%Y-%m-%d"), "heure": NOW.strftime("%H:%M")}, ensure_ascii=False), encoding="utf-8")
    print("\n".join(journal))
    print(f"Consigne écrite : {ICI / 'consigne-du-jour.md'} ({moment}, {date_txt} {NOW.strftime('%H:%M')})")


if __name__ == "__main__":
    main()
