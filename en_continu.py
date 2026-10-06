"""
Fait tourner Veille CIG France en direct sur ton propre ordinateur, sans GitHub.

  python en_continu.py

- lance le collecteur tout de suite, puis toutes les 5 minutes ;
- sert la page sur http://localhost:8000 (ouvre ce lien dans ton navigateur, puis clique « Direct »).
Ctrl+C pour arrêter.
"""
import functools
import http.server
import subprocess
import sys
import threading
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent


def collecte_en_boucle():
    while True:
        subprocess.run([sys.executable, str(ICI / "collecteur.py")])
        time.sleep(300)


threading.Thread(target=collecte_en_boucle, daemon=True).start()
gestion = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ICI / "docs"))
print("Page : http://localhost:8000  (Ctrl+C pour arrêter)")
http.server.ThreadingHTTPServer(("localhost", 8000), gestion).serve_forever()
