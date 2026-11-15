# Esplorazione sistematica dei confini in un servizio REST

Approfondimento svolto nell'ambito del corso di Software Testing (Università degli Studi di Napoli Federico II), a partire dall'esercitazione "Testing Black Box di Servizi REST" sul servizio Tasse.

Autore: Fabio Greco

## In breve

Durante l'esercitazione avevo trovato a mano un limite nascosto: il server dichiarava "CFU previsti tra 1 e 180", ma accettava valori fino a 300. Qui quel procedimento, sviluppato a mano tramite euristiche ragionevoli, diventa una procedura automatica: per ogni parametro intero si cercano i punti in cui la risposta del servizio cambia (i confini) e li si confronta con quelli attesi dai requisiti. La procedura permette, in determinati casi, di inferire il limite numerico effettivamente applicato dal servizio e di individuare discrepanze rispetto ai vincoli di riferimento, senza disporre del codice sorgente.

L'idea nasce dalla curiosità e da una tecnica che avevo già usato in un mio progetto di web scraping su Vinted: il metodo del "voltmetro digitale", che restringe un intervallo numerico suddividendolo in sottointervalli finché trova il punto in cui la risposta cambia. Qui l'ho ripresa in parte in modo intuitivo, e solo in un secondo momento ho scoperto che idee simili sono già state studiate: nell'estrazione di database nascosti dietro interfacce web (Sheng et al., 2012) e nella boundary value exploration (Dobslaw et al., 2020).

La procedura è stata eseguita sulla versione del servizio con 10 difetti iniettati dal docente e confrontata con la mia suite manuale, con Schemathesis e con casi di test generati da un LLM (Gemini).

| Approccio | Dimensione | Difetti riconosciuti |
| --- | --- | --- |
| Suite manuale (fase 1) | 249 test | 1, 3, 4, 5, 6, 7, 9, 10 + D7 |
| Esplorazione dei confini | 1889 richieste | 2, 3, 4, 5, 6, 7, 8, 10 + D7 |
| Gemini | 67 test | 1, 3, 5, 6, 7, 8, 9, 10 + D7 |
| Schemathesis con vincoli aggiunti | 2150 casi | 1, 4, 7, 8 |

D7 è una discrepanza non etichettata dal docente (esenzione totale da 65% invece che da 66%). Metodo, formalizzazione, risultati e limiti sono descritti nel report in `report/`.

## Struttura

```
report/        il report completo in PDF
esplorazione/  lo script della procedura e la sua simulazione offline
schemathesis/  le specifiche OpenAPI usate e il lettore dei report di Schemathesis
llm/           i casi di test di Gemini, il testo dato a Gemini e i risultati dell'esecuzione
```

## Requisiti

- Python 3.9 o successivo. Gli script usano solo la libreria standard.
- Per il confronto: Schemathesis (`pip install schemathesis`; è stata usata la versione 4.33.4).

## Come si usa

**Esplorazione dei confini**

```
cd esplorazione
python esplora_confini.py https://indirizzo-del-server
```

Lo script esplora gli 8 parametri interi del servizio nei 59 contesti ricavati dai requisiti e stampa, per ogni contesto, i confini conformi e le anomalie (confini non documentati, confini attesi ma assenti, risposte 5xx). Alla fine stampa il numero di richieste e le segnalazioni `DIFETTO n trovato!` del server strumentato, se presenti.

Lo script invia circa 1900 richieste senza pause: va usato solo su sistemi propri o per i quali si ha l'autorizzazione, preferibilmente in un ambiente di test.

**Prova senza server**

```
cd esplorazione
python simula2.py . originale
python simula2.py . difettoso
```

Sostituisce le richieste HTTP con una riscrittura in Python delle regole del servizio. Sulla versione originale lo script non segnala anomalie; su quella difettosa trova i difetti attesi. È una verifica di coerenza, non una prova: la simulazione parte dalla stessa lettura dei requisiti.

**Schemathesis**

```
cd schemathesis
st run openapi_vincoli.json --url https://indirizzo-del-server --checks all --continue-on-failure --max-examples 300 --report har --report-dir report_st3
python leggi_report.py report_st3
```

`openapi.json` è la specifica pubblicata dal server, senza vincoli sui parametri; `openapi_vincoli.json` aggiunge 12 vincoli presi dai requisiti. `leggi_report.py` riassume il report HAR: status per endpoint e difetti raggiunti. Nelle due specifiche l'indirizzo temporaneo del server originale è stato sostituito con `http://localhost:8080`: l'indirizzo effettivo si passa con `--url`. Conviene usare una cartella di report nuova per ogni esecuzione, perché `leggi_report.py` legge tutti i report presenti nella cartella indicata.

**LLM**

I CSV in `llm/gemini_csv/` vanno copiati al posto di quelli del progetto JUnit dell'esercitazione. In `llm/prompt_gemini.txt` ci sono il testo inviato a Gemini (modalità Auto, ragionamento avanzato) e l'elenco degli allegati; la consegna e i requisiti, allegati come immagine e PDF, non sono inclusi perché materiale del corso. I risultati dell'esecuzione, esportati da IntelliJ, sono in `llm/risultati_intellij.xml` e si leggono con:

```
cd llm
python leggi_xml.py risultati_intellij.xml
```

L'XML contiene 100 test: i 67 casi di Gemini (53 superati, 14 falliti) e 33 errori di inizializzazione dei test della mia suite, i cui CSV erano stati svuotati per eseguire solo i casi di Gemini. I risultati riportati riguardano solo i 67 casi. Dal file sono stati rimossi il comando di avvio e i percorsi locali.

## Note

- Il server strumentato del docente era raggiungibile a un indirizzo temporaneo, che potrebbe non essere più attivo.
- Il codice del servizio, le slide e il progetto JUnit del corso non sono inclusi: sono materiale del docente.
