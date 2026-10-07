"""Figures du rejeu 2024 (après rejeu.py et bilan.py). Écrit dans rejeu_2024/resultats/ et, s'il existe, dans le
dossier figures du rapport."""
import csv
import gzip
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from collecteur import date  # noqa: E402

R = ICI / "resultats"
RAPPORT = Path("/home/claude/rapport/figures")
INK, INK2, GRID, BLUE = "#1f1f1e", "#5f5e5a", "#d3d1c7", "#2a6f97"
ORANGE, JAUNE, ROUGE, VERT = "#ec835a", "#fab219", "#d03b3b", "#0ca30c"
plt.rcParams.update({"font.size": 8.5, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})

bilan = json.loads((R / "bilan_2024.json").read_text())
horaire = json.loads((R / "horaire_2024.json").read_text())
h = {}
with gzip.open(R / "dbdt_chambon_2024.csv.gz", "rt") as f:
    for l in f.read().splitlines()[1:]:
        t, v = l.split(",")
        h[date(t)] = float(v)
with gzip.open(R / "collectes_2024.csv.gz", "rt") as f:
    col = list(csv.DictReader(io.StringIO(f.read())))


def sauver(fig, nom):
    fig.savefig(R / f"{nom}.png", dpi=160, bbox_inches="tight")
    if RAPPORT.exists():
        fig.savefig(RAPPORT / f"{nom}.pdf", bbox_inches="tight")


# ---------------------------------------------------------------- figure 15 : l'année et le 10 mai
fig, (a, b) = plt.subplots(2, 1, figsize=(7.2, 5.6), gridspec_kw={"height_ratios": [1, 1.05], "hspace": 0.42})
jours = {}
for t, v in h.items():
    j = t.replace(hour=0, minute=0)
    jours[j] = max(jours.get(j, 0), v)
J = sorted(jours)
a.bar(J, [jours[j] for j in J], width=1, color=BLUE, alpha=0.75, lw=0)
a.set_yscale("log"); a.set_ylim(1, 1000)
a.axhline(68, color=ORANGE, lw=1); a.axhline(30, color=INK2, lw=0.7, ls="--")
a.text(J[2], 76, "orange (68 nT/min)", color=ORANGE, fontsize=7.5)
a.text(J[2], 33, "30 nT/min", color=INK2, fontsize=7.5)
for e in bilan["episodes"]["liste"]:
    d0, d1 = date(e["debut"]), date(e["fin"])
    if e["ouvert_par"] == ["cme"]:
        a.axvspan(d0, d1, ymin=0.92, ymax=0.99, color=BLUE, alpha=0.9, lw=0)
    else:
        a.plot(d0, 330, marker="v", color=INK, ms=3.5, lw=0)
a.text(1.0, 1.03, "▬ veille CME orange   ▼ choc détecté à L1", transform=a.transAxes, ha="right", fontsize=7.5, color=INK2)
a.set_ylabel("dB/dt max. du jour\nà Chambon (nT/min)")
a.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
a.set_title("(a) 2024 : 47 épisodes d'alerte rejoués", loc="left", fontsize=9, color=INK)

t0, t1 = datetime(2024, 5, 10, 12, tzinfo=timezone.utc), datetime(2024, 5, 11, 12, tzinfo=timezone.utc)
T = [t for t in sorted(h) if t0 <= t <= t1]
b.plot(T, [h[t] for t in T], color=BLUE, lw=0.7, label="dB/dt mesuré à Chambon (1 min)")
C = [(date(c["t"]), float(c["dbdt_p90"])) for c in col if c["dbdt_p90"] and t0 <= date(c["t"]) <= t1]
b.step([c[0] for c in C], [c[1] for c in C], where="post", color=ORANGE, lw=1.1, label="P90 prévu à L1 (heure qui commence)")
b.axhline(68, color=ORANGE, lw=0.6, ls=":")
b.set_yscale("log"); b.set_ylim(0.5, 4000)
choc = datetime(2024, 5, 10, 16, 30, tzinfo=timezone.utc)
pic = datetime(2024, 5, 10, 17, 7, tzinfo=timezone.utc)
for x, txt, ha in ((choc, "16 h 30 : choc détecté,\npré-alerte orange ", "right"), (pic, " 17 h 07 : pic\n 107 nT/min", "left")):
    b.axvline(x, color=INK2, lw=0.6, ls=":")
    b.text(x, 1500, txt, ha=ha, va="center", fontsize=7.2, color=INK)
b.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
b.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m\n%H h"))
b.set_ylabel("nT/min")
b.legend(loc="upper right", fontsize=7.2, frameon=False, ncol=1)
b.set_title("(b) 10-11 mai 2024, tel que le service l'aurait vécu", loc="left", fontsize=9, color=INK)
sauver(fig, "fig15_rejeu_2024")

# ---------------------------------------------------------------- figure 16 : calibrage et CME
fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 3.1), gridspec_kw={"wspace": 0.32})
P = np.array([r["prevu_med"] for r in horaire if r.get("observe")])
O = np.array([max(r["observe"], 0.3) for r in horaire if r.get("observe")])
a.hexbin(np.log10(P), np.log10(O), gridsize=40, bins="log", cmap="Blues", mincnt=1, linewidths=0)
x = np.linspace(-0.2, 2.5, 10)
a.plot(x, x, color=INK, lw=0.8)
a.fill_between(x, x - 0.301, x + 0.301, color=GRID, alpha=0.5, lw=0)
ticks = [1, 3, 10, 30, 100]
a.set_xticks(np.log10(ticks)); a.set_xticklabels(ticks); a.set_yticks(np.log10(ticks)); a.set_yticklabels(ticks)
a.set_xlim(-0.1, 2.4); a.set_ylim(-0.4, 2.4)
a.set_xlabel("dB/dt prévu (médiane, nT/min)"); a.set_ylabel("dB/dt mesuré, max. horaire (nT/min)")
a.set_title(f"(a) {len(P)} heures de 2024", loc="left", fontsize=9, color=INK)
err = [c["erreur_h"] for c in bilan["cme"]["cas"] if c.get("statut") == "annoncée"]
b.axvspan(-10, 10, color=GRID, alpha=0.5, lw=0)
b.hist(err, bins=np.arange(-60, 31, 6), color=BLUE, alpha=0.85)
b.axvline(0, color=INK, lw=0.8)
b.set_xlabel("arrivée prévue − arrivée réelle (h)")
b.set_ylabel("chocs reliés à une CME")
b.set_title(f"(b) {len(err)} CME annoncées", loc="left", fontsize=9, color=INK)
sauver(fig, "fig16_scores_2024")
print("figures écrites")
