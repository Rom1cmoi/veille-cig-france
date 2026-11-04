"""Diagnostic ponctuel de l'accès aux données INTERMAGNET (service GIN du BGS) : retard annoncé par le serveur
(GetDataLagTime), embargo par observatoire (GetCapabilities), et données récentes par type de publication
(best-avail, adjusted, reported) ; écriture de samplesPerDay (minute / Minute). Écrit diagnostic/acces.txt."""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

B = "https://imag-data.bgs.ac.uk/GIN_V1/GINServices?"
OBS = ["CLF", "HAD", "DOU", "FUR", "EBR", "SPT", "WNG", "SFS"]


def lire(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
        except Exception as e:
            err = str(e)
            time.sleep(5)
    return "ERREUR " + err


def minutes(texte):
    n, der = 0, None
    for l in texte.splitlines():
        x = l.split()
        if len(x) >= 6 and len(x[0]) == 10 and x[0][4] == "-":
            try:
                a, b = float(x[3]), float(x[4])
            except ValueError:
                continue
            if abs(a) < 88888 and abs(b) < 88888:
                n += 1
                der = x[0] + " " + x[1][:5]
    typ = [l.split("Data Type")[1].strip(" |") for l in texte.splitlines()[:25] if "Data Type" in l]
    return n, der, typ


now = datetime.now(timezone.utc)
out = [f"Diagnostic d'accès du {now:%Y-%m-%d %H:%M} UTC"]
# 1. retard annoncé par le serveur
t = lire(B + "Request=GetDataLagTime&Format=plain&observatoryIagaCodeList=" + ",".join(OBS) +
         f"&dataStartDate={(now - timedelta(days=20)):%Y-%m-%d}&dataDuration=21&showDetails=false")
out += ["== GetDataLagTime (21 jours, plain) ==", t[:3000]]
# 2. capacités : embargo et types disponibles pour nos observatoires
t = lire(B + "Request=GetCapabilities&format=json")
try:
    d = json.loads(t)
    txt = json.dumps(d, ensure_ascii=False)
    out.append("== GetCapabilities : clés de premier niveau == " + str(list(d)[:10] if isinstance(d, dict) else type(d)))
    for o in OBS:
        i = txt.find(f'"{o}"')
        out.append(f"{o} : {txt[max(0, i - 200):i + 600] if i >= 0 else 'absent'}")
except Exception as e:
    out.append(f"GetCapabilities illisible ({e}) : {t[:1500]}")
# 3. données des 2 derniers jours selon le type de publication et l'écriture de samplesPerDay
d0 = (now - timedelta(days=1)).strftime("%Y-%m-%d")
out.append(f"== GetData depuis le {d0}, 2 jours ==")
for o in OBS:
    for etat in ("best-avail", "adjusted", "reported"):
        for spd in ("minute", "Minute"):
            if spd == "Minute" and etat != "best-avail":
                continue
            u = (B + f"Request=GetData&format=iaga2002&observatoryIagaCode={o}&samplesPerDay={spd}"
                 f"&dataStartDate={d0}&dataDuration=2&publicationState={etat}&orientation=native")
            t = lire(u)
            n, der, typ = minutes(t) if not t.startswith("ERREUR") else (0, None, [t[:120]])
            out.append(f"{o} {etat:10s} {spd:6s} : {n:5d} minutes valides, dernière {der}, type {typ}")
            print(out[-1], flush=True)
open("diagnostic/acces.txt", "w").write("\n".join(out) + "\n")
