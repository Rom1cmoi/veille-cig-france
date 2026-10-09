"""Sonde ponctuelle : retard de publication des 6 observatoires des rejeux sur le service GIN du BGS (INTERMAGNET).
Écrit sondes/observatoires.txt : pour chaque observatoire, dernière minute valide et retard par rapport à maintenant."""
import urllib.request
from datetime import datetime, timedelta, timezone

URL = ("https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&format=iaga2002&observatoryIagaCode={o}"
       "&samplesPerDay=minute&dataStartDate={d}&dataDuration=6&publicationState=best-avail&orientation=native")
maintenant = datetime.now(timezone.utc)
debut = (maintenant - timedelta(days=5)).strftime("%Y-%m-%dT00:00:00Z")
lignes = [f"Sonde du {maintenant:%Y-%m-%d %H:%M} UTC"]
for o in ("CLF", "HAD", "DOU", "FUR", "EBR", "SPT", "VAL", "ESK", "BFO", "WNG", "MAB", "AQU", "SFS", "COI"):
    try:
        texte = urllib.request.urlopen(URL.format(o=o, d=debut), timeout=60).read().decode("utf-8", "replace")
        derniere, entete = None, [l for l in texte.splitlines() if "Data Type" in l or "Reported" in l]
        for l in texte.splitlines():
            p = l.split()
            if len(p) >= 6 and p[0][:2] == "20" and len(p[0]) == 10:
                try:
                    X, Y = float(p[3]), float(p[4])
                except ValueError:
                    continue
                if abs(X) < 88888 and abs(Y) < 88888:
                    derniere = p[0] + " " + p[1][:5]
        retard = (maintenant - datetime.strptime(derniere, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)) if derniere else None
        n = sum(1 for l in texte.splitlines() if l[:2] == "20")
        lignes.append(f"{o} : {n} lignes, dernière minute valide {derniere} UTC, retard {retard}")
    except Exception as e:
        lignes.append(f"{o} : erreur {e}")
open("sondes/observatoires.txt", "w").write("\n".join(lignes) + "\n")
print("\n".join(lignes))
