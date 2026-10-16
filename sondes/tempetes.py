"""Sonde : liste des tempêtes géomagnétiques depuis 2000 (Kp définitif du GFZ), pour choisir les tempêtes d'un
réajustement du modèle vent solaire -> dB/dt. Une tempête = jours consécutifs (UTC) avec un Kp maximal >= 7-.
Écrit sondes/tempetes.csv : début, fin, Kp maximal, jours."""
import json
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

URL = "https://kp.gfz.de/app/json/?start=2000-01-01T00:00:00Z&end=2026-10-16T00:00:00Z&index=Kp"
req = urllib.request.Request(URL, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
d = json.loads(urllib.request.urlopen(req, timeout=180).read())
kpmax = defaultdict(float)
for t, k in zip(d["datetime"], d["Kp"]):
    if k is not None:
        jour = date.fromisoformat(t[:10])
        kpmax[jour] = max(kpmax[jour], k)
jours = sorted(j for j, k in kpmax.items() if k >= 6.66)
tempetes, cour = [], []
for j in jours:
    if cour and j - cour[-1] > timedelta(days=1):
        tempetes.append(cour); cour = []
    cour.append(j)
if cour:
    tempetes.append(cour)
lignes = ["debut,fin,kp_max,jours"] + [f"{t[0]},{t[-1]},{max(kpmax[j] for j in t):.3f},{len(t)}" for t in tempetes]
open("sondes/tempetes.csv", "w").write("\n".join(lignes) + "\n")
print(len(tempetes), "tempêtes Kp >= 7- depuis 2000 ;", sum(1 for t in tempetes if max(kpmax[j] for j in t) >= 7.66), "avec Kp >= 8-")
