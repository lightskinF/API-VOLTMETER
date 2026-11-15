"""
Legge i file HAR salvati da Schemathesis e riassume, per ogni endpoint:
  - quante richieste sono state fatte e con quali status HTTP;
  - quali difetti ha segnalato il server strumentato (campo "difetto").

Uso:   python leggi_report.py cartella_report
"""
import base64
import collections
import glob
import json
import os
import sys
import urllib.parse

if len(sys.argv) != 2:
    sys.exit("Uso: python leggi_report.py cartella_report")

# Schemathesis salva il report HAR con estensione .json (es. har-20261113T232652Z.json)
file_har = [p for estensione in ("*.har", "*.json")
            for p in glob.glob(os.path.join(sys.argv[1], "**", estensione), recursive=True)]
if not file_har:
    sys.exit("Nessun report HAR trovato in " + sys.argv[1])

status = collections.defaultdict(collections.Counter)
difetti = collections.defaultdict(collections.Counter)
esempi = {}
totale = 0

for percorso in file_har:
    with open(percorso, encoding="utf-8") as f:
        har = json.load(f)
    for voce in har.get("log", {}).get("entries", []):
        url = voce["request"]["url"]
        endpoint = urllib.parse.urlparse(url).path.replace("/api/v1/tasse/", "")
        codice = voce["response"]["status"]
        totale += 1
        status[endpoint][codice] += 1
        contenuto = voce["response"].get("content", {})
        testo = contenuto.get("text") or ""
        if contenuto.get("encoding") == "base64":
            testo = base64.b64decode(testo).decode("utf-8", "replace")
        try:
            dati = json.loads(testo)
        except ValueError:
            continue
        if isinstance(dati, dict) and dati.get("difetto"):
            for pezzo in dati["difetto"].replace("!", "!|").split("|"):
                pezzo = pezzo.strip()
                if pezzo:
                    difetti[endpoint][pezzo] += 1
                    esempi.setdefault(pezzo, urllib.parse.urlparse(url).query)

print("Richieste totali nei report: %d\n" % totale)
for endpoint in sorted(status):
    print("%s" % endpoint)
    print("  status: " + ", ".join("%d x%d" % (c, n) for c, n in sorted(status[endpoint].items())))
    for d, n in sorted(difetti[endpoint].items()):
        print("  %s  (%d richieste)" % (d, n))
print("\nPrima richiesta che ha raggiunto ciascun difetto:")
for d in sorted(esempi, key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or 0)):
    print("  %s  <- %s" % (d, esempi[d]))
