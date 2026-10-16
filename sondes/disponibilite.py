"""Sonde : pour chaque tempête de Kp >= 8- depuis 2000 (sondes/tempetes.csv), part des minutes disponibles
- dans OMNI à la minute (vitesse, densité et Bz valides en même temps : les entrées du modèle) ;
- au magnétomètre de Chambon-la-Forêt (définitif, sinon meilleure donnée disponible).
Fenêtre : de 3 h avant le premier jour à la fin du dernier jour (UTC). Écrit sondes/disponibilite.csv."""
import csv
import io
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

OMNI = ("https://cdaweb.gsfc.nasa.gov/hapi/data?id=OMNI_HRO_1MIN&parameters=BZ_GSM,flow_speed,proton_density"
        "&time.min={a}&time.max={b}&format=csv")
CLF_DEF = ("https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?dataset=clf/definitive/PT1M/xyzf"
           "&parameters=Field_Vector&start={a}&stop={b}&format=csv")
CLF_BEST = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002&observatoryIagaCode=CLF"
            "&samplesPerDay=minute&dataStartDate={a}&dataDuration={j}&publicationState=best-avail&orientation=native")


def lire(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            return urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "replace")
        except Exception as e:
            err = e
            time.sleep(5 * (i + 1))
    return ""


def valeurs(texte):
    """Lignes CSV HAPI -> liste de listes de flottants (None si vide ou valeur de remplissage)."""
    out = []
    for r in csv.reader(io.StringIO(texte)):
        if not r or not r[0][:2].isdigit():
            continue
        v = []
        for x in r[1:]:
            try:
                f = float(x)
                v.append(None if abs(f) >= 9000 or (f >= 990 and f < 1000) else f)
            except ValueError:
                v.append(None)
        out.append(v)
    return out


lignes = [l for l in csv.DictReader(open("sondes/tempetes.csv")) if float(l["kp_max"]) >= 7.66]
res = [["debut", "fin", "kp_max", "minutes", "omni_pct", "clf_pct", "clf_source"]]
for l in lignes:
    a = datetime.fromisoformat(l["debut"]).replace(tzinfo=timezone.utc) - timedelta(hours=3)
    b = datetime.fromisoformat(l["fin"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    n = int((b - a).total_seconds() // 60)
    fa, fb = a.strftime("%Y-%m-%dT%H:%M:%SZ"), b.strftime("%Y-%m-%dT%H:%M:%SZ")
    om = valeurs(lire(OMNI.format(a=fa, b=fb)))
    omni_ok = sum(1 for v in om if len(v) >= 3 and None not in v[:3])
    cl = valeurs(lire(CLF_DEF.format(a=fa, b=fb)))
    clf_ok, source = sum(1 for v in cl if len(v) >= 2 and v[0] is not None and v[1] is not None), "définitif"
    if clf_ok < 0.5 * n:                                       # pas encore de définitif : données provisoires
        t = lire(CLF_BEST.format(a=fa, j=(b - a).days + 1))
        ok = 0
        for r in t.splitlines():
            p = r.split()
            if len(p) >= 6 and p[0][:2] == "20" and len(p[0]) == 10:
                tt = datetime.fromisoformat(p[0] + "T" + p[1][:5]).replace(tzinfo=timezone.utc)
                if a <= tt < b and abs(float(p[3])) < 88888 and abs(float(p[4])) < 88888:
                    ok += 1
        if ok > clf_ok:
            clf_ok, source = ok, "provisoire"
    res.append([l["debut"], l["fin"], l["kp_max"], n, round(100 * omni_ok / n, 1), round(100 * clf_ok / n, 1), source])
    print(res[-1], flush=True)
with open("sondes/disponibilite.csv", "w", newline="") as f:
    csv.writer(f).writerows(res)
