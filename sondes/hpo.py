"""Indices Hp30 et ap30 du GFZ (Yamazaki et al., 2024 ; licence CC BY 4.0), de 2000 à aujourd'hui, pour relier
l'ap30 au dB/dt mesuré à Chambon (reajustement/donnees/hpo.csv.gz : time = début de la demi-heure, Hp30, ap30, statut).
Essaie l'API JSON du GFZ, puis les fichiers texte publiés."""
import csv
import gzip
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SORTIE = Path("reajustement/donnees/hpo.csv.gz")
API = "https://kp.gfz.de/app/json/?start={a}&end={b}&index={i}&status=all"
TEXTE = ["https://kp.gfz.de/app/files/Hp30_ap30_complete_series.txt", "https://kp.gfz.de/app/files/Hp30_ap30_nowcast.txt"]


def lire(url):
    for k in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            return urllib.request.urlopen(req, timeout=300).read().decode("utf-8", "replace")
        except Exception as e:
            print("échec", url, e, flush=True)
            time.sleep(10 * (k + 1))
    return ""


fin = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
lignes = {}
for i in ("Hp30", "ap30"):
    t = lire(API.format(a="2000-01-01T00:00:00Z", b=fin, i=i))
    try:
        d = json.loads(t)
        for k, (tt, v) in enumerate(zip(d["datetime"], d[i])):
            lignes.setdefault(tt, {})[i] = v
            if "status" in d:
                lignes[tt]["statut"] = d["status"][k]
        print(i, "API :", len(d["datetime"]), "valeurs", flush=True)
    except Exception as e:
        print(i, "API inutilisable :", e, t[:200], flush=True)
if not lignes:                                                    # repli : fichiers texte (colonnes du format Hpo)
    for url in TEXTE:
        for l in lire(url).splitlines():
            p = l.split()
            if l.startswith("#") or len(p) < 9 or int(p[0]) < 2000:
                continue
            h = float(p[3])
            tt = f"{p[0]}-{p[1]}-{p[2]}T{int(h):02d}:{round((h % 1) * 60):02d}:00Z"
            lignes[tt] = {"Hp30": float(p[7]), "ap30": float(p[8]), "statut": "nowcast" if "nowcast" in url else "def"}
    print("fichiers texte :", len(lignes), "valeurs", flush=True)
SORTIE.parent.mkdir(parents=True, exist_ok=True)
with gzip.open(SORTIE, "wt", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "Hp30", "ap30", "statut"])
    for tt in sorted(lignes):
        v = lignes[tt]
        w.writerow([tt, v.get("Hp30", ""), v.get("ap30", ""), v.get("statut", "")])
