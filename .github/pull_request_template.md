<!--
Tre lettori, tre livelli, in quest'ordine: (1) chi non fa software, (2) chi fa la review tecnica, (3) gli agenti AI.
Le intestazioni H2 sono fisse: il check `pr-issue` (scripts/pr_template.py) le cerca per nome e ordine, e rifiuta
sezioni vuote, con il solo commento-guida o con segnaposto (`...`, TODO, TBD). Non rinominarle, non riordinarle.
Fonti del modello: docs/decisions/pr-template.md.
-->

## Riassunto per tutti

<!--
Per chi non fa software: parole semplici, niente gergo, leggibile in 30 secondi, conclusione per prima (BLUF).
Mantieni queste otto voci in grassetto, una riga ciascuna:
Prima = come si comportava il sistema fin qui. Dopo = come si comporta con questa modifica.
Punti di forza / Debolezze = cosa guadagniamo e cosa resta fragile, dentro il progetto.
Opportunità / Rischi = cosa rende possibile dopo e cosa può andare storto, fuori dal progetto (mini SWOT).
Se va male = quale danno, per chi, quanto in fretta lo si nota. Come si annulla = i passi per tornare indietro.
-->

- **Prima:**
- **Dopo:**
- **Punti di forza:**
- **Debolezze:**
- **Opportunità:**
- **Rischi:**
- **Se va male:**
- **Come si annulla:**

## Sintesi

<!-- Livello tecnico. Una o due frasi, all'indicativo: cosa cambia, in modo che stia da solo nella cronologia di git. -->

## Issue collegata

<!-- Obbligatorio. `Closes #N` chiude la issue al merge; `Refs #N` solo se la issue deve restare aperta. -->

## Contesto e motivazione

<!-- Il perché: problema, decisione o vincolo che rende necessaria la modifica, con link a spec, decisioni, ricerche. Il codice dice cosa fa, non perché esiste. -->

## Modifiche

<!-- Il cosa: una riga per file o gruppo di file. -->

| File | Modifica |
|---|---|
| | |

### Documentazione

<!-- Elencare percorsi aggiornati e motivo nella stessa PR che cambia comportamento (regole, uso, decisioni, runbook, prove).
Se nessun documento è interessato, scrivere «Non applicabile:» con il motivo concreto; il reviewer verifica il nesso col diff. -->

### Riuso

<!-- Cosa è stato riusato / cercato e scartato / perché. -->

## Ambito e non-ambito

<!-- Cosa questa PR copre e cosa lascia fuori di proposito (rimandi a issue di seguito). -->

## Rischio

<!-- Prima parola: HIGH, MEDIUM o LOW (profondità della review), poi l'impatto: cosa si rompe, chi lo nota, quanto è esteso. -->

## Verifiche eseguite

<!-- Prove riproducibili: una riga per comando → esito (test, lint, typecheck, `git diff --check`), con l'output finale. Dichiara ciò che NON hai potuto eseguire. -->

## Prova e2e

<!-- Un blocco JSON: command, environment, utc (ISO8601 UTC), output, effect, counterproof, sha (head corrente).
Fonte CI (consigliata): "source": {"type": "ci", "workflow": ".github/workflows/<file>.yml", "job": "<job>", "step": "<step>"}; con source lo sha è facoltativo (transizione #801), se presente deve essere l'head.
Controprova: caso negativo che deve fallire e risultato osservato, oppure test che fallisce sulla base e passa sulla PR, con comando e risultato.
Solo per PR documentali: counterproof "non applicabile: <motivo>". Il gate verifica i path reali.
Prova differita o assente = DoD incompleta. -->

## Verifica dopo il merge

<!-- Esecuzione definita in post_merge nel blocco YAML; qui descrivi effetto atteso e vincoli.
Il supervisor pubblica un commento «Verifica post-merge: PASS» o «Verifica post-merge: FAIL» sulla prima riga. -->

## Dove guardare

<!-- Per chi fa la review: file e punti critici da leggere per primi, e cosa è solo meccanico (spostamenti, formattazione). -->

## Approvazione richiesta all'operatore

<!-- La decisione che serve all'operatore, in parole semplici; «Nessuna» se non serve. -->

## Rollback

<!-- Come annullare (di solito `git revert` della PR), cosa non si annulla da solo (dati, stato esterno), come accorgersi che serve. -->

## Contenuto generato da AI

<!-- Prima parola: Sì o No. Se Sì: quali parti (codice, test, descrizione), con quale strumento, e come le hai verificate di persona. -->

## Dati per agenti AI

<!--
Livello macchina: un solo blocco ```yaml con queste chiavi, validate dallo schema in scripts/pr_template.py.
issue: numero (lo stesso di «Issue collegata»). risk_class: routine | rilievo. files_critical, tests_run, sources (URL
http/https della documentazione tecnica usata): almeno una voce. assumptions, open_questions: liste, `[]` se nessuna. dod: riferimenti/prove per ogni voce del metodo; osservabilità a–e
con prove oppure non applicabilità motivata per ciascuna voce. Nessun campo vuoto o segnaposto.
post_merge obbligatorio: mode run con hosts non vuoti e unici dall'inventario (mac, dell, sg-ci, sg-voter-1,
tk-data-1, tk-hl-1, tk-hl-2, tk-mon, tk-nt-1, tk-voter-1), command non vuoto, prerequisites opzionale
come lista owner/repo#n positivi e unici. Oppure {mode: skip, reason: "motivo concreto"} per doc/refusi.
Solo il YAML decide il gate: nessun fallback alla prosa, nessun campo extra, chiavi duplicate o merge YAML.
-->

```yaml
issue: 0
risk_class: routine
files_critical: []
tests_run: []
sources: []
assumptions: []
open_questions: []
post_merge:
  mode: run
  hosts: []
  command: ""
  prerequisites: []
dod:
  requirements: ""
  design: ""
  tasks: ""
  lenses: ""
  checks: ""
  rollback: ""
  observability:
    metrics: ""
    alerts: ""
    logs: ""
    incidents: ""
    dead_man: ""
```
