"""Diagnostic ponctuel : où se trouve l'API SensorThings du BCMT (IPGP, nouvelle interface de septembre 2025), et
donne-t-elle Chambon-la-Forêt en temps réel ? Lit les pages publiques de l'application et leurs scripts pour trouver
l'adresse de l'API, vérifie robots.txt, puis interroge l'API (Things, Datastreams). Écrit diagnostic/bcmt_api.txt."""
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "veille-cig-france (projet etudiant IPSA)"
PAGES = []
BASE = "https://catalogue-terresolide.ipgp.fr/FROST-Server/v1.1"          # vue dans la console du navigateur
out = []


def autorise(url):
    u = urllib.parse.urlsplit(url)
    rp = urllib.robotparser.RobotFileParser(f"{u.scheme}://{u.netloc}/robots.txt")
    try:
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def lire(url):
    if not autorise(url):
        out.append(f"robots.txt interdit : {url}")
        return ""
    for k in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as e:
            err = str(e)
            time.sleep(3)
    out.append(f"échec {url} : {err}")
    return ""


candidats = set()
for p in PAGES:
    h = lire(p)
    out.append(f"== {p} : {len(h)} caractères")
    scripts = set(re.findall(r'<script[^>]+src="([^"]+)"', h)) | set(re.findall(r"<iframe[^>]+src=\"([^\"]+)\"", h))
    out.append("scripts / iframes : " + ", ".join(sorted(scripts))[:1500])
    textes = [h]
    for s in sorted(scripts)[:30]:
        textes.append(lire(urllib.parse.urljoin(p, s)))
    for t in textes:
        for m in re.findall(r"https?://[A-Za-z0-9._/\-:]+", t):
            if re.search(r"sensorthings|frost|v1\.[01]|sta|api|datastream", m, re.I):
                candidats.add(m.rstrip("/\"'),;"))
candidats.add(BASE)
out.append("== adresses candidates ==\n" + "\n".join(sorted(candidats)[:80]))
# interroge les candidats qui ressemblent à une racine SensorThings
for c in sorted(candidats):
    m = re.match(r"(https?://.+?/v1\.[01])", c)
    if not m:
        continue
    base = m.group(1)
    if base in [o.split(" ")[1] for o in out if o.startswith("API ")]:
        continue
    t = lire(base)
    out.append(f"API {base} : {t[:400]}")
    t = lire(base + "/Things?$top=100&$select=name,description,%40iot.id")
    out.append(f"Things : {t[:3000]}")
    t = lire(base + "/Datastreams?$filter=" + urllib.parse.quote("substringof('CLF',name)") + "&$top=40&$select=name,phenomenonTime,unitOfMeasurement,%40iot.id")
    out.append(f"Datastreams CLF : {t[:3000]}")
    t = lire(base + "/Datastreams?$top=20&$select=name,phenomenonTime,%40iot.id")
    out.append(f"Datastreams (20 premiers) : {t[:3000]}")
    ids = re.findall(r'"@iot.id"\s*:\s*"?([0-9A-Za-z_\-]+)', t)
    for i in ids[:2]:
        t2 = lire(base + f"/Datastreams({i})/Observations?$top=3&$orderby=phenomenonTime%20desc&$select=phenomenonTime,result")
        out.append(f"Observations récentes du datastream {i} : {t2[:800]}")
open("diagnostic/bcmt_api.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out)[:4000])
