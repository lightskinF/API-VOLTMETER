# Controllo interno: sostituisce le richieste HTTP con una simulazione in Python delle regole
# del TasseService (originale o difettoso), per provare esplora_confini.py senza server.
# Uso (dalla cartella esplorazione):  python simula2.py . originale   oppure   python simula2.py . difettoso
import sys
sys.path.insert(0, sys.argv[1])
import esplora_confini as e

DIF = sys.argv[2] == "difettoso"


def neg32(v):  # negazione Java su int a 32 bit
    return v if v == e.INT_MIN else -v


def servizio(p, q):
    n, b = p["nome"], dict(p["base"])
    b[n] = q
    try:
        vals = {k: (int(v) if k in ("componentiNucleo", "cfuAcquisiti", "cfuPrevisti", "anniFuoriCorso",
                                       "percentualeDisabilita", "votoMaturita", "numeroRate", "giorniRitardo")
                    else v) for k, v in b.items()}
    except ValueError:
        return 400, {}
    for k in ("componentiNucleo", "cfuAcquisiti", "cfuPrevisti", "anniFuoriCorso",
              "percentualeDisabilita", "votoMaturita", "numeroRate", "giorniRitardo"):
        if k in vals and not (e.INT_MIN <= vals[k] <= e.INT_MAX):
            return 400, {}
    path = p["path"]
    if path.endswith("contributo-base"):
        return (400, {}) if (vals["tipologiaIscrizione"] == "FUORI_CORSO" and vals["anniFuoriCorso"] < 1) else (200, {})
    if path.endswith("fascia-isee"):
        isee, c = float(vals["isee"]), vals["componentiNucleo"]
        if (isee <= 0) if DIF else (isee < 0):
            return 400, {}
        if DIF and c < 0:
            c = neg32(c)
        if c < 1:
            return 400, {}
        for lim, f, s in ((15000, "FASCIA_1", 80), (25000, "FASCIA_2", 50), (35000, "FASCIA_3", 30),
                          (50000, "FASCIA_4", 10), (float("inf"), "FASCIA_5", 0)):
            if isee <= lim:
                break
        if c >= 4 and isee <= (50000 if DIF else 35000):
            s = min(85, s + 5)
        return 200, {"fasciaIsee": f, "percentualeSconto": float(s)}
    if path.endswith("sconto-merito"):
        acq, prev, media = vals["cfuAcquisiti"], vals["cfuPrevisti"], float(vals["mediaVoti"])
        if prev <= 0 or prev > (300 if DIF else 180):
            return 400, {}
        if acq < 0 or acq > prev:
            return 400, {}
        perc = (acq // prev) * 100.0 if DIF else round(acq / prev * 100, 2)
        lode = vals["lode"] == "true"
        if lode and media < 29:
            return 400, {}
        sb = 0.0
        if (media >= 24) if DIF else (perc >= 80 and media >= 24):
            sb = 15.0 if media < 27 else 30.0 if media < 29 else (40.0 if perc >= 90 else 30.0)
        sf = min(50.0, sb + 10) if (lode and sb > 0) else sb
        return 200, {"percentualeScontoMerito": sf}
    if path.endswith("esenzione-speciale"):
        dis, mat, primo = vals["percentualeDisabilita"], vals.get("votoMaturita"), vals["primoAnno"] == "true"
        borsa = vals["vincitoreBorsaStudio"] == "true"
        if dis < 0 or (not DIF and dis > 100):
            return 400, {}
        if mat is not None and (mat < 60 or mat > 100):
            return 400, {}
        if dis >= (65 if DIF else 66) or borsa or (primo and mat == 100):
            es = "ESENZIONE_TOTALE"
        elif dis >= 33:
            es = "ESENZIONE_PARZIALE_50"
        elif primo and mat is not None and mat >= 95:
            es = "ESENZIONE_PARZIALE_30"
        elif DIF and mat is None:
            return 500, {}
        elif DIF and mat == 60:
            es = "ESENZIONE_PARZIALE_30"
        else:
            es = "NESSUNA_ESENZIONE"
        return 200, {"esitoEsenzione": es}
    if path.endswith("piano-rate"):
        n_r, isee = vals["numeroRate"], float(vals["isee"])
        if n_r < 1 or n_r > 4:
            return 400, {}
        spese = {2: 15.0, 3: 25.0, 4: 35.0}.get(n_r, 0.0) if (n_r > 1 and isee > 25000) else 0.0
        return 200, {"speseGestioneEuro": spese}
    if path.endswith("mora-ritardo"):
        g = vals["giorniRitardo"]
        if g < 0:
            return 400, {}
        f = ("GRAZIA" if g <= 14 else "RITARDO_LIEVE" if g <= (31 if DIF else 30)
             else "RITARDO_MEDIO" if g <= 90 else "RITARDO_GRAVE")
        return 200, {"fasciaRitardo": f}


def finta_firma(p, valore):
    e.richieste += 1
    codice, dati = servizio(p, str(valore))
    if codice != 200:
        return (codice,)
    return (codice,) + tuple(dati.get(c) for c in p["firma"])


e.firma = finta_firma
tot = 0
for serv, path, nome, campi, genera in e.PARAMETRI:
    print("=== Servizio %d - %s" % (serv, nome))
    for i, (base, mn, mx, conf) in enumerate(genera()):
        p = dict(path=path, nome=nome, firma=campi, base=base, min=mn, max=mx, confini=conf)
        e.richieste = 0
        an, ok = e.esplora(p, completo=(i == 0))
        tot += e.richieste
        if an:
            print("  [%s]" % ", ".join("%s=%s" % kv for kv in base.items()))
            for a in an: print("     " + a)
print("Richieste totali:", tot)
