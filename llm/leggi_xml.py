"""
Legge i risultati dei test esportati da IntelliJ (Export Test Results, formato XML)
e stampa per ogni test: esito, valore atteso e ottenuto, righe "DIFETTO n trovato!".

Uso:   python leggi_xml.py risultati_intellij.xml
"""
import sys, re, xml.etree.ElementTree as ET
t = ET.parse(sys.argv[1]).getroot()
def walk(n, d=0):
    for c in n:
        if c.tag in ("suite","test"):
            st = c.get("status")
            outs = [o.text or "" for o in c.findall("output")]
            txt = " ".join(outs)
            dif = sorted(set(re.findall(r"DIFETTO \d+ trovato!", txt, re.I)))
            msg = ""
            for o in c.findall("output"):
                if o.get("type") in ("stderr",) and o.text:
                    msg = o.text.strip().splitlines()[0][:220]; break
            df = c.find("diff")
            dd = (" exp=%s act=%s" % (df.get("expected"), df.get("actual"))) if df is not None else ""
            print("  "*d + "[%s] %s%s %s %s" % (st, c.get("name")[:150], dd, dif if dif else "", ("| "+msg) if (st not in ("passed",None) and c.tag=="test" and not dd) else ""))
            walk(c, d+1)
walk(t)
