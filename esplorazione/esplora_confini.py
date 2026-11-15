"""
Esplorazione black-box dei confini dei parametri interi, con contesti sistematici.

Uso:   python esplora_confini.py https://indirizzo-del-server

FIRMA di una risposta: lo status HTTP piu' i campi di classificazione dell'output
(fascia, esito, sconto...). Due valori con la stessa firma sono equivalenti.

CONTESTI (regola fissa, presa solo dalla specifica): per ogni parametro intero
esplorato, gli altri parametri assumono tutte le combinazioni valide di un
rappresentante per ciascuna classe documentata. I cambi di firma attesi in ogni
contesto sono calcolati dalle regole delle slide.

Per ogni parametro e contesto:
  1. SONDAGGIO: i due lati di ogni confine documentato, poi passi doppi
     (1, 2, 4, 8, ...). Nel primo contesto di ogni parametro si arriva ai limiti
     del tipo int a 32 bit; negli altri ci si ferma a 1024 oltre i confini noti.
  2. LOCALIZZAZIONE: dove la firma cambia tra due valori sondati, bisezione fino
     ai due valori adiacenti del cambio.
  3. CONFRONTO: cambi conformi, non documentati, documentati ma assenti;
     ogni risposta 5xx e' segnalata come errore del server.
Ipotesi: tra due valori sondati consecutivi c'e' al massimo un cambio di firma.

Origine dei limiti di validita': slide dove indicato; altrimenti messaggi di
errore del server (anni FC >= 1, nucleo >= 1, CFU previsti 1-180,
disabilita' 0-100, maturita' 60-100, giorni >= 0).
"""
import itertools
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INT_MIN, INT_MAX = -2**31, 2**31 - 1
MARGINE = 1024

# ---------------------------------------------------------------------------
# Specifica: per ogni parametro intero, i contesti (combinazioni dei
# rappresentanti delle classi degli altri parametri) e i cambi attesi.
# Ogni contesto: (valori di base, min, max, {(ultimo prima, primo dopo): descrizione})
# ---------------------------------------------------------------------------


def contesti_anni():
    out = []
    for corso, tip in itertools.product(["UMANISTICO", "SCIENTIFICO", "INGEGNERIA", "MEDICO"],
                                        ["IN_CORSO", "PART_TIME", "FUORI_CORSO"]):
        minimo = 1 if tip == "FUORI_CORSO" else None   # vincolo solo per i fuori corso
        out.append(({"corsoDiStudi": corso, "tipologiaIscrizione": tip}, minimo, None, {}))
    return out


def contesti_nucleo():
    out = []
    for isee in [10000, 20000, 30000, 42500, 60000]:   # un ISEE per ciascuna fascia
        attesi = {(3, 4): "bonus nucleo numeroso (>= 4)"} if isee <= 35000 else {}
        out.append(({"isee": "%.2f" % isee}, 1, None, attesi))
    return out


MERITO = [(20.0, "false"), (25.0, "false"), (28.0, "false"), (29.5, "false"), (29.5, "true")]


def contesti_cfu_acquisiti():
    out = []
    for media, lode in MERITO:   # una media per fascia di merito; lode solo con media >= 29
        attesi = {}
        if media >= 24:
            attesi[(79, 80)] = "soglia 80% CFU"
        if media >= 29:
            attesi[(89, 90)] = "soglia 90% CFU (oro)"
        out.append(({"cfuPrevisti": "100", "mediaVoti": str(media), "lode": lode}, 0, 100, attesi))
    return out


def contesti_cfu_previsti():
    # cfuAcquisiti = 0: unico valore valido per ogni cfuPrevisti; % CFU = 0 -> sconto costante
    return [({"cfuAcquisiti": "0", "mediaVoti": str(m), "lode": l}, 1, 180, {}) for m, l in MERITO]


def contesti_disabilita():
    out = []
    for borsa, primo, mat in itertools.product(["false", "true"], ["false", "true"], [80, 97, 100, None]):
        base = {"vincitoreBorsaStudio": borsa, "primoAnno": primo}
        if mat is not None:
            base["votoMaturita"] = str(mat)   # None = parametro omesso (default 60)
        if borsa == "true" or (primo == "true" and mat == 100):
            attesi = {}   # esenzione totale per qualunque disabilita'
        else:
            attesi = {(32, 33): "esenzione parziale 50% (>= 33)", (65, 66): "esenzione totale (>= 66)"}
        out.append((base, 0, 100, attesi))
    return out


def contesti_maturita():
    out = []
    for dis, borsa, primo in itertools.product([10, 50, 80], ["false", "true"], ["false", "true"]):
        base = {"percentualeDisabilita": str(dis), "vincitoreBorsaStudio": borsa, "primoAnno": primo}
        if borsa == "true" or dis >= 66 or primo == "false":
            attesi = {}
        elif dis >= 33:
            attesi = {(99, 100): "esenzione totale (primo anno e voto 100)"}
        else:
            attesi = {(94, 95): "esenzione parziale 30% (>= 95)",
                      (99, 100): "esenzione totale (primo anno e voto 100)"}
        out.append((base, 60, 100, attesi))
    return out


def contesti_rate():
    out = []
    for isee in [20000, 30000]:   # ISEE <= 25000 e > 25000
        attesi = ({(1, 2): "spese 2 rate", (2, 3): "spese 3 rate", (3, 4): "spese 4 rate"}
                  if isee > 25000 else {})
        out.append(({"importoTotale": "1000.00", "isee": "%.2f" % isee}, 1, 4, attesi))
    return out


def contesti_giorni():
    attesi = {(14, 15): "fine periodo di grazia", (30, 31): "fine ritardo lieve",
              (90, 91): "fine ritardo medio"}
    return [({"importoRata": "500.00", "sollecitoInviato": s}, 0, None, dict(attesi))
            for s in ["false", "true"]]


PARAMETRI = [
    (1, "/api/v1/tasse/calcola-contributo-base", "anniFuoriCorso", [], contesti_anni),
    (2, "/api/v1/tasse/fascia-isee", "componentiNucleo", ["fasciaIsee", "percentualeSconto"], contesti_nucleo),
    (3, "/api/v1/tasse/sconto-merito", "cfuPrevisti", ["percentualeScontoMerito"], contesti_cfu_previsti),
    (3, "/api/v1/tasse/sconto-merito", "cfuAcquisiti", ["percentualeScontoMerito"], contesti_cfu_acquisiti),
    (4, "/api/v1/tasse/esenzione-speciale", "percentualeDisabilita", ["esitoEsenzione"], contesti_disabilita),
    (4, "/api/v1/tasse/esenzione-speciale", "votoMaturita", ["esitoEsenzione"], contesti_maturita),
    (5, "/api/v1/tasse/piano-rate", "numeroRate", ["speseGestioneEuro"], contesti_rate),
    (6, "/api/v1/tasse/mora-ritardo", "giorniRitardo", ["fasciaRitardo"], contesti_giorni),
]

# ---------------------------------------------------------------------------
# Esplorazione
# ---------------------------------------------------------------------------

base_url = ""
richieste = 0
difetti_visti = set()


def firma(p, valore):
    """Invia la richiesta e restituisce la firma: (status, campi di output)."""
    global richieste
    query = dict(p["base"])
    query[p["nome"]] = str(valore)
    url = base_url + p["path"] + "?" + urllib.parse.urlencode(query)
    for tentativo in range(3):
        try:
            richieste += 1
            with urllib.request.urlopen(url, timeout=20) as risposta:
                codice, corpo = risposta.status, risposta.read()
            break
        except urllib.error.HTTPError as errore:
            codice, corpo = errore.code, errore.read()
            break
        except (urllib.error.URLError, TimeoutError):
            if tentativo == 2:
                sys.exit("Server non raggiungibile: " + url)
            time.sleep(2)
    try:
        dati = json.loads(corpo)
    except ValueError:
        dati = {}
    if isinstance(dati, dict) and dati.get("difetto"):
        difetti_visti.add(dati["difetto"])
    if codice != 200 or not isinstance(dati, dict):
        return (codice,)
    return (codice,) + tuple(dati.get(campo) for campo in p["firma"])


def mostra(f):
    return "/".join(str(x) for x in f)


def punti_di_sondaggio(p, completo):
    noti = [v for v in (p["min"], p["max"]) if v is not None] or [0]
    for a, b in p["confini"]:
        noti += [a, b]
    basso, alto = min(noti), max(noti)
    limite_basso = INT_MIN if completo else basso - MARGINE
    limite_alto = INT_MAX if completo else alto + MARGINE
    punti = {INT_MIN - 1, INT_MIN, INT_MAX, INT_MAX + 1} if completo else set()
    for v in noti:
        punti.update({v - 1, v, v + 1})
    passo = 1
    while basso - passo > limite_basso or alto + passo < limite_alto:
        if basso - passo > limite_basso:
            punti.add(basso - passo)
        if alto + passo < limite_alto:
            punti.add(alto + passo)
        passo *= 2
    return sorted(punti)


def bisezione(p, a, firma_a, b, firma_b):
    while b - a > 1:
        m = (a + b) // 2
        f = firma(p, m)
        if f == firma_a:
            a = m
        else:
            b, firma_b = m, f
    return a, b, firma_b


def esplora(p, completo):
    """Esplora un parametro in un contesto; restituisce l'elenco delle anomalie."""
    punti = punti_di_sondaggio(p, completo)
    firme = [firma(p, v) for v in punti]
    cambi = []
    for i in range(len(punti) - 1):
        if firme[i] != firme[i + 1]:
            a, b, fb = bisezione(p, punti[i], firme[i], punti[i + 1], firme[i + 1])
            cambi.append((a, b, firme[i], fb))

    attesi = {}
    if p["min"] is not None:
        attesi[(p["min"] - 1, p["min"])] = "limite inferiore documentato"
    if p["max"] is not None:
        attesi[(p["max"], p["max"] + 1)] = "limite superiore documentato"
    attesi.update(p["confini"])
    di_tipo = {(INT_MAX, INT_MAX + 1), (INT_MIN - 1, INT_MIN)}

    anomalie, conformi = [], 0
    for a, b, fa, fb in cambi:
        errore_server = fa[0] >= 500 or fb[0] >= 500
        if (a, b) in di_tipo and not errore_server:
            continue
        if (a, b) in attesi and not errore_server:
            conformi += 1
            continue
        motivo = "ERRORE SERVER" if errore_server else "NON DOCUMENTATO"
        anomalie.append("cambio tra %d e %d (%s -> %s) %s" % (a, b, mostra(fa), mostra(fb), motivo))
    osservati = {(a, b) for a, b, _, _ in cambi}
    for coppia, descrizione in attesi.items():
        if coppia not in osservati:
            anomalie.append("ASSENTE: %s (nessun cambio tra %d e %d)" % (descrizione, coppia[0], coppia[1]))
    tutte_5xx = [v for v, f in zip(punti, firme) if f[0] >= 500]
    if tutte_5xx and not any("ERRORE SERVER" in x for x in anomalie):
        anomalie.append("ERRORE SERVER (5xx) per %d valori sondati" % len(tutte_5xx))
    if p["max"] is not None and (p["max"], p["max"] + 1) not in osservati:
        sopra = [a for a, b, fa, fb in cambi if a > p["max"] and fa[0] == 200 and fb[0] != 200]
        if sopra and (sopra[0], sopra[0] + 1) not in di_tipo:
            anomalie.append("-> limite superiore osservato: %d (divergenza = %d)" % (sopra[0], sopra[0] - p["max"]))
        elif completo:
            anomalie.append("-> nessun limite superiore fino al limite del tipo")
    return anomalie, conformi


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python esplora_confini.py https://indirizzo-del-server")
    base_url = sys.argv[1].rstrip("/")
    totale = 0
    riepilogo = []
    for servizio, path, nome, campi, genera in PARAMETRI:
        contesti = genera()
        print("\n=== Servizio %d - %s (%d contesti)" % (servizio, nome, len(contesti)))
        con_anomalie = 0
        for i, (base, minimo, massimo, confini) in enumerate(contesti):
            p = dict(path=path, nome=nome, firma=campi, base=base, min=minimo, max=massimo, confini=confini)
            richieste = 0
            anomalie, conformi = esplora(p, completo=(i == 0))
            totale += richieste
            contesto = ", ".join("%s=%s" % kv for kv in base.items())
            if anomalie:
                con_anomalie += 1
                print("  [%s]  (%d richieste)" % (contesto, richieste))
                for a in anomalie:
                    print("     " + a)
            else:
                print("  [%s]  OK: %d cambi conformi  (%d richieste)" % (contesto, conformi, richieste))
        riepilogo.append((servizio, nome, con_anomalie, len(contesti)))

    print("\n=== Riepilogo")
    for servizio, nome, k, n in riepilogo:
        print("  Servizio %d - %-22s contesti con anomalie: %d su %d" % (servizio, nome, k, n))
    print("Richieste totali: %d" % totale)
    if difetti_visti:
        print("Difetti segnalati dal server durante l'esplorazione:")
        for d in sorted(difetti_visti):
            print("  " + d)
