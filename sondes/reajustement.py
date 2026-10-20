"""Données pour réajuster le modèle « vent solaire -> dB/dt à Chambon » sur les tempêtes de Kp >= 8- depuis 2000.

Pour chaque tempête de sondes/tempetes.csv (Kp max >= 8-), de 6 h avant le premier jour à la fin du dernier jour (UTC) :
  - OMNI à la minute (CDAWeb, HAPI) : By, Bz GSM, vitesse, densité, pression dynamique ;
  - Chambon-la-Forêt à la minute : X, Y, Z (définitif BGS, sinon meilleure donnée disponible) ;
et une fois pour toutes l'indice Kp (GFZ) de 2000 à aujourd'hui.
Écrit reajustement/donnees/<début>_omni.csv.gz, <début>_clf.csv.gz et kp.csv.gz (valeurs manquantes : vide).
"""
import csv
import gzip
import io
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SORTIE = Path("reajustement/donnees")
OMNI = ("https://cdaweb.gsfc.nasa.gov/hapi/data?id=OMNI_HRO_1MIN&parameters=BY_GSM,BZ_GSM,flow_speed,proton_density,Pressure"
        "&time.min={a}&time.max={b}&format=csv")
CLF_DEF = ("https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?dataset=clf/definitive/PT1M/xyzf"
           "&parameters=Field_Vector&start={a}&stop={b}&format=csv")
CLF_BEST = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002&observatoryIagaCode=CLF"
            "&samplesPerDay=minute&dataStartDate={a}&dataDuration={j}&publicationState=best-avail&orientation=native")
KP = "https://kp.gfz.de/app/json/?start=2000-01-01T00:00:00Z&end={fin}&index=Kp"


def lire(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            return urllib.request.urlopen(req, timeout=240).read().decode("utf-8", "replace")
        except Exception:
            time.sleep(10 * (i + 1))
    return ""


def nombre(x, lim=9000):
    try:
        f = float(x)
    except ValueError:
        return ""
    return "" if abs(f) >= lim or 990 <= f < 1000 else repr(f)


def ecrire(nom, entete, lignes):
    with gzip.open(SORTIE / nom, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(entete)
        w.writerows(lignes)


SORTIE.mkdir(parents=True, exist_ok=True)
maintenant = datetime.now(timezone.utc)
k = json.loads(lire(KP.format(fin=maintenant.strftime("%Y-%m-%dT00:00:00Z"))) or "{}")
ecrire("kp.csv.gz", ["time", "Kp"], zip(k.get("datetime", []), k.get("Kp", [])))
print("Kp :", len(k.get("Kp", [])), "valeurs", flush=True)

for l in csv.DictReader(open("sondes/tempetes.csv")):
    if float(l["kp_max"]) < 7.66:
        continue
    a = datetime.fromisoformat(l["debut"]).replace(tzinfo=timezone.utc) - timedelta(hours=6)
    b = datetime.fromisoformat(l["fin"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    fa, fb = a.strftime("%Y-%m-%dT%H:%M:%SZ"), b.strftime("%Y-%m-%dT%H:%M:%SZ")
    # OMNI : time, By, Bz, V, n, P
    om = []
    for r in csv.reader(io.StringIO(lire(OMNI.format(a=fa, b=fb)))):
        if len(r) >= 6 and r[0][:2] == "20":
            om.append([r[0][:16] + "Z", nombre(r[1]), nombre(r[2]), nombre(r[3], 9990), nombre(r[4], 900), nombre(r[5], 90)])
    ecrire(f"{l['debut']}_omni.csv.gz", ["time", "By", "Bz", "V", "n", "P"], om)
    # Chambon : time, X, Y, Z
    cl, source = [], "définitif"
    for r in csv.reader(io.StringIO(lire(CLF_DEF.format(a=fa, b=fb)))):
        if len(r) >= 4 and r[0][:2] == "20":
            cl.append([r[0][:16] + "Z", nombre(r[1], 88888), nombre(r[2], 88888), nombre(r[3], 88888)])
    if sum(1 for r in cl if r[1] and r[2]) < 0.5 * (b - a).total_seconds() / 60:
        best = []
        for r in lire(CLF_BEST.format(a=a.strftime("%Y-%m-%d"), j=(b - a).days + 2)).splitlines():
            p = r.split()
            if len(p) >= 6 and p[0][:2] == "20" and len(p[0]) == 10:
                t = datetime.fromisoformat(p[0] + "T" + p[1][:5]).replace(tzinfo=timezone.utc)
                if a <= t < b:
                    best.append([t.strftime("%Y-%m-%dT%H:%MZ"), nombre(p[3], 88888), nombre(p[4], 88888), nombre(p[5], 88888)])
        if len(best) > len(cl):
            cl, source = best, "meilleure disponible"
    ecrire(f"{l['debut']}_clf.csv.gz", ["time", "X", "Y", "Z"], cl)
    print(l["debut"], l["fin"], "OMNI", len(om), "min ; Chambon", len(cl), "min,", source, flush=True)
