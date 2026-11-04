"""Diagnostic ponctuel : pour chaque observatoire utilisé, dernière minute valide publiée par le serveur BGS (GIN,
meilleure donnée disponible) et nombre de minutes valides par jour sur les 15 derniers jours.
Écrit diagnostic/observatoires.txt."""
import time
import urllib.request
from datetime import datetime, timedelta, timezone

URL = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002&observatoryIagaCode={o}"
       "&samplesPerDay=minute&dataStartDate={d}&dataDuration={n}&publicationState={p}&orientation=native")


def lire(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
            return urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
        except Exception as e:
            err = str(e)
            time.sleep(5)
    return "ERREUR " + err


maintenant = datetime.now(timezone.utc)
debut = (maintenant - timedelta(days=17)).strftime("%Y-%m-%d")
out = [f"Diagnostic du {maintenant:%Y-%m-%d %H:%M} UTC, depuis le {debut}"]
for o in ("CLF", "HAD", "DOU", "FUR", "EBR", "SPT", "WNG", "SFS"):
    for p in ("best-avail", "adj-or-rep"):
        t = lire(URL.format(o=o, d=debut, n=18, p=p))
        if t.startswith("ERREUR"):
            out.append(f"{o} {p} : {t[:200]}")
            continue
        par_jour, der, reprise = {}, None, None
        for l in t.splitlines():
            x = l.split()
            if len(x) >= 6 and len(x[0]) == 10 and x[0][4] == "-":
                try:
                    a, b = float(x[3]), float(x[4])
                except ValueError:
                    continue
                if abs(a) < 88888 and abs(b) < 88888:
                    par_jour[x[0]] = par_jour.get(x[0], 0) + 1
                    t = x[0] + " " + x[1][:5]
                    if der and t > "2026-10-25" and der < "2026-10-25" and not reprise:
                        reprise = t                                  # première minute après le trou
                    der = t
        entete = [l.strip() for l in t.splitlines()[:20] if "Data Type" in l or "Publication" in l]
        out.append(f"{o} {p} : reprise après le trou {reprise} | dernière minute valide {der} | {entete} | " +
                   ", ".join(f"{j[5:]}:{n}" for j, n in sorted(par_jour.items())))
        print(out[-1], flush=True)
open("diagnostic/observatoires.txt", "w").write("\n".join(out) + "\n")
