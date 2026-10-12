"""Télécharge une fois les magnétomètres à la minute des 10 et 11 octobre 2026 (tempête rejouée sur la page).
Mêmes observatoires que les rejeux (HAD, DOU, CLF, FUR, EBR, SPT), plus Wingst (WNG) et San Fernando (SFS)
au cas où certains n'auraient pas publié. Sortie : rejeu_oct2026/donnees/<code>.csv (t, X, Y en nT)."""
import sys
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from sol import URL, lire_xy  # noqa: E402

(ICI / "donnees").mkdir(exist_ok=True)
for o in ("HAD", "DOU", "CLF", "FUR", "EBR", "SPT", "WNG", "SFS"):
    url = URL.format(o=o, debut="2026-10-10T00:00:00Z").replace("dataDuration=1", "dataDuration=2")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "veille-cig-france (projet etudiant IPSA)"})
        m = lire_xy(urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace"))
    except Exception as e:
        print(o, "erreur", e)
        continue
    lignes = ["t,X,Y"] + [f"{t:%Y-%m-%dT%H:%MZ},{x:.2f},{y:.2f}" for t, (x, y) in sorted(m.items())]
    (ICI / "donnees" / f"{o}.csv").write_text("\n".join(lignes) + "\n")
    print(o, len(m), "minutes valides")
