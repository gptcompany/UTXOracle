# Gemini Execution Prompts

Date: 2026-04-05

Purpose: copy-paste prompts for Gemini that stay aligned with the current UTXOracle architecture, the updated spec bookkeeping, and the actual local workspace baseline.

## How To Use

- Use one prompt at a time.
- Treat the local workspace as the source of truth. Do not treat an empty review or empty commit as proof of progress.
- Before coding, reread the spec artifacts named in the prompt.
- Follow the current architecture and registry docs when historical spec prose conflicts with them.
- Make one commit per prompt, then stop.
- If live infra, external docs, or tokens are missing, do not fake completion. Record the blocker clearly and stop.

---

## PROMPT_SPEC003_T092_T093_SYSTEMD_REBOOT [DONE]

```text
Continua dalla prossima fase realmente aperta e coerente con gli artefatti allineati.

Contesto importante:
- usa come baseline il workspace locale attuale, non eventuali review vuote o commit senza delta
- `spec-003` e' maintenance-only per il path legacy batch/comparison
- il confine canonico live/chart non e' qui:
  - `:8011` e' la boundary di produzione
  - `frontend/comparison.html` su `:8001` resta research-only
  - `/api/prices/*` e `/api/metrics/latest` sono serviti canonicamente da `api.routes.questdb`
- questa spec mantiene solo ownership su `scripts/daily_analysis.py`, validazione operativa e hardening del writer path

Artefatti da rileggere prima di toccare codice:
- `specs/003-mempool-integration-refactor/spec.md`
- `specs/003-mempool-integration-refactor/plan.md`
- `specs/003-mempool-integration-refactor/tasks.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`

Prossima fase:
- target tasks: `T092`, `T093`
- obiettivo:
  - verificare in modo onesto la resilienza systemd e la reboot readiness dell'esistente
  - produrre evidenza eseguibile o artefatti operativi utili
  - non introdurre feature nuove

Vincoli non negoziabili:
- non creare nuove route
- non cambiare il contratto canonico `:8011`
- non trattare `frontend/comparison.html` come superficie canonica
- non falsificare un reboot test se non e' stato davvero eseguito
- se il reboot reale non e' eseguibile nell'ambiente corrente:
  - prepara check script / runbook / artifact precisi
  - lascia aperta o parziale la task, con motivazione fattuale
- puoi chiudere `T110` solo se la stessa evidenza soddisfa davvero il criterio senza stretching

File target:
- `specs/003-mempool-integration-refactor/tasks.md`
- `OPERATIONAL_RUNBOOK.md`
- `scripts/health_check.sh`
- eventuali artifact sotto `specs/003-mempool-integration-refactor/`

Prima di toccare codice:
- conferma il perimetro di `T092` e `T093`
- implementa solo cio' che serve a verificare/strumentare questi task
- includi nel commit solo eventuali delta locali strettamente pertinenti a questa fase

Output richiesto a fine fase:
- Phase completed: spec-003 / systemd-reboot
- Commit: <sha>
- Files changed:
- Commands run:
- Tests or checks run:
- Result:
- Residual risks:
- Ready for review: yes/no

Fai un solo commit e fermati.
```

---

## PROMPT_SPEC003_T101_T106_VALIDATION_BACKLOG [DONE]

```text
Continua su `spec-003` senza scope drift.

Contesto importante:
- usa come baseline il workspace locale, non review/commit vuoti
- `spec-003` e' maintenance backlog per `daily_analysis.py` e path batch/comparison legacy
- la priorita' non e' feature nuova ma validazione operativa misurabile
- i task storici non devono trascinare lavoro fuori perimetro rispetto a `docs/ARCHITECTURE.md`

Artefatti da rileggere:
- `specs/003-mempool-integration-refactor/spec.md`
- `specs/003-mempool-integration-refactor/plan.md`
- `specs/003-mempool-integration-refactor/tasks.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`

Fase target:
- target tasks: `T101`-`T106`
- obiettivo:
  - trasformare il backlog di validation in checks, scripts, tests, runbooks o artifacts realmente eseguibili
  - chiudere solo cio' che puoi dimostrare
  - lasciare traccia chiara dei task che restano manuali o richiedono infra live/tempo reale

Vincoli non negoziabili:
- non rifattorizzare lateralmente `daily_analysis.py`
- non introdurre nuove feature UI
- non aprire nuove surface canoniche
- non simulare come "passato" un memory leak 24h, un bandwidth test o un disk audit se non hai raccolto davvero l'evidenza
- se un task richiede tempo reale o infrastruttura non disponibile:
  - crea al massimo harness/checklist/script
  - aggiorna gli artifact in modo veritiero
  - non marcarlo done senza evidenza

File target:
- `scripts/daily_analysis.py` solo se strettamente necessario
- `tests/test_daily_analysis.py`
- `scripts/health_check.sh`
- eventuali script di validazione dedicati
- `specs/003-mempool-integration-refactor/tasks.md`
- eventuali artifact sotto `specs/003-mempool-integration-refactor/`

Nota importante:
- `T108`-`T110` non sono il target di questa fase
- non inseguire il vecchio target di line-count o un refactor cosmetico

Output richiesto a fine fase:
- Phase completed: spec-003 / validation-backlog
- Commit: <sha>
- Files changed:
- Commands run:
- Tests or checks run:
- Result:
- Residual risks:
- Ready for review: yes/no

Un solo commit. Poi fermati.
```

---

## PROMPT_SPEC003_T138_TIER1_E2E

```text
Continua su `spec-003` dalla fase successiva coerente.

Contesto importante:
- baseline locale stabile:
  - `scripts/daily_analysis.py` usa il path Tier 1 aggiornato
  - questa spec resta maintenance-only
  - il live contract canonico non si tocca
- non usare review o commit vuoti come segnale di progresso

Artefatti da rileggere:
- `specs/003-mempool-integration-refactor/spec.md`
- `specs/003-mempool-integration-refactor/plan.md`
- `specs/003-mempool-integration-refactor/tasks.md`
- `docs/ARCHITECTURE.md`

Prossima fase:
- target task: `T138`
- obiettivo:
  - verificare davvero l'end-to-end Tier 1 sul path attuale
  - confermare che il `--dry-run --verbose` usa il Tier 1 previsto e produce evidenza leggibile
  - produrre artifact/check log utili senza aprire nuovo scope

Vincoli non negoziabili:
- non implementare ancora `T139` o `T140`
- non cambiare route contracts o frontend
- non rifattorizzare `daily_analysis.py` se non emerge un bug bloccante direttamente da `T138`
- se l'infra richiesta non e' disponibile o non e' sana:
  - documenta il blocker
  - non segnare la task come completata

File target:
- `scripts/daily_analysis.py` solo se trovi un bug bloccante di `T138`
- `tests/test_daily_analysis.py` solo se serve coprire il bug emerso
- `specs/003-mempool-integration-refactor/tasks.md`
- eventuali artifact di evidenza sotto `specs/003-mempool-integration-refactor/`

Output richiesto a fine fase:
- Phase completed: spec-003 / tier1-e2e
- Commit: <sha>
- Files changed:
- Commands run:
- Tests or checks run:
- Result:
- Residual risks:
- Ready for review: yes/no

Fai un solo commit e fermati.
```

---

## PROMPT_SPEC003_T139_T140_TIER_FALLBACK_OBSERVABILITY

```text
Continua su `spec-003` con disciplina rigida.

Contesto importante:
- usa come baseline il workspace locale attuale
- `spec-003` ha ownership solo sul path batch writer / resilience story
- il contratto canonico `:8011` non va ampliato per inerzia storica
- se un task storico parla di endpoint o frontend, implementa solo il minimo coerente con l'architettura attuale

Artefatti da rileggere:
- `specs/003-mempool-integration-refactor/spec.md`
- `specs/003-mempool-integration-refactor/tasks.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`
- `docs/contracts/feature_contract_registry.yaml`

Prossima fase:
- target tasks: `T139`, `T140`
- obiettivo:
  - completare il fallback Tier 2 come opzione operativa reale
  - aggiungere osservabilita' sul tier usato dal writer
  - evitare di introdurre nuove superfici prodotto non ammesse

Vincoli non negoziabili:
- non toccare superfici chart canoniche
- non promuovere nuovi endpoint consumer-facing senza allineare registry/architettura
- se per `T140` serve un endpoint:
  - tienilo esplicitamente operator/research-only
  - documentalo come tale
  - aggiorna `docs/FEATURE_CONTRACT_REGISTRY.md` e `docs/contracts/feature_contract_registry.yaml` solo se la nuova route esiste davvero
- non fare refactor laterali in `daily_analysis.py`
- non inseguire il vecchio frontend comparison come deliverable canonico

File target:
- `scripts/daily_analysis.py`
- `tests/test_daily_analysis.py`
- `api/routes/questdb.py` solo se strettamente necessario
- `docs/ARCHITECTURE.md` solo se la behavior surface cambia davvero
- `docs/FEATURE_CONTRACT_REGISTRY.md`
- `docs/contracts/feature_contract_registry.yaml`
- `specs/003-mempool-integration-refactor/tasks.md`

Prima di toccare codice:
- conferma se `T140` puo' essere soddisfatta senza introdurre una nuova public route
- se no, limita la route a superficie operator/research e allinea i documenti

Output richiesto a fine fase:
- Phase completed: spec-003 / tier2-observability
- Commit: <sha>
- Files changed:
- Commands run:
- Tests run:
- Result:
- Residual risks:
- Ready for review: yes/no

Un solo commit e stop.
```

---

## PROMPT_SPEC003_T108_T110_ACCEPTANCE_CLEANUP

```text
Chiudi il backlog amministrativo residuo di `spec-003` senza scope drift.

Contesto importante:
- questa fase non e' una scusa per rifare codice o inseguire obiettivi storici non piu' sensati
- `spec-003` e' maintenance-only
- il target storico "codebase <= 800 lines" non deve guidare refactor nuovi se non e' piu' architetturalmente rilevante

Artefatti da rileggere:
- `specs/003-mempool-integration-refactor/spec.md`
- `specs/003-mempool-integration-refactor/tasks.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`

Fase target:
- target tasks: `T108`, `T109`, `T110`
- obiettivo:
  - verificare se questi criteri sono ancora chiudibili con evidenza gia' raccolta
  - riallinearli in modo onesto all'architettura attuale
  - non fare lavoro tecnico nuovo solo per far quadrare vecchi acceptance criteria

Vincoli non negoziabili:
- non rifattorizzare per inseguire il line-count
- non cambiare il contratto runtime per compiacere il wording storico
- chiudi una task solo se hai evidenza reale
- se il criterio e' ormai archivistico o superseded:
  - annotalo chiaramente
  - non inventare completamenti

File target:
- `specs/003-mempool-integration-refactor/tasks.md`
- eventuali note/artifacts collegati alla spec

Output richiesto a fine fase:
- Phase completed: spec-003 / acceptance-cleanup
- Commit: <sha>
- Files changed:
- Checks reviewed:
- Result:
- Residual risks:
- Ready for review: yes/no

Un solo commit. Poi fermati.
```

---

## PROMPT_SPEC018_T045A_T045C_VALIDATION_BENCH

```text
Continua dalla fase successiva di `spec-018`.

Contesto importante:
- usa il workspace locale come baseline
- `spec-018` e' in maintenance mode, non greenfield
- stato tecnico stabile:
  - `scripts/metrics/cointime.py` esiste ed e' il source di calcolo
  - `/api/metrics/cointime*` esiste gia' su `:8001`
  - `cointime` e' gia' nel set `ENHANCED_WEIGHTS` a 11 componenti con peso `0.14`
- il lavoro residuo e' solo validazione fixture-based + benchmark

Artefatti da rileggere:
- `specs/018-cointime-economics/spec.md`
- `specs/018-cointime-economics/plan.md`
- `specs/018-cointime-economics/tasks.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`

Prossima fase:
- target tasks: `T045a`, `T045b`, `T045c`
- obiettivo:
  - creare la fixture di riferimento
  - aggiungere il test di confronto con reference data
  - aggiungere il performance benchmark richiesto da `SC-003`

Vincoli non negoziabili:
- non ridisegnare le API
- non cambiare il peso `0.14` o il set a 11 componenti salvo bug dimostrato
- non trasformare il benchmark in un test flaky o dipendente dal rumore macchina senza protezioni
- usa, se utile, marker tipo `slow` / `performance` gia' esistenti nel repo
- se la reference data non e' perfetta o e' solo campionata:
  - documenta chiaramente provenienza e limiti
  - non spacciare dati sintetici per golden data reali

File target:
- `tests/fixtures/glassnode_cointime_reference.csv`
- `tests/test_cointime.py`
- `scripts/metrics/cointime.py` solo se i test scoprono un bug reale
- documentazione/spec solo se serve annotare la provenienza della fixture

Prima di toccare codice:
- conferma il perimetro di `T045a`-`T045c`
- implementa solo questa fase
- includi nel commit solo delta strettamente pertinenti

Output richiesto a fine fase:
- Phase completed: spec-018 / validation-benchmark
- Commit: <sha>
- Files changed:
- Tests run:
- Result:
- Residual risks:
- Ready for review: yes/no

Fai un solo commit e fermati.
```

---

## PROMPT_SPEC035_T034_QUICKSTART_VERIFY

```text
Continua dalla fase successiva di `spec-035`.

Contesto importante:
- usa come baseline il workspace locale, non review/commit vuoti
- `spec-035` e' una surface `tier_3_research` gia' implementata
- il runtime reale e':
  - `/api/v1/validation/rbn/*` su `:8001`
  - fetcher/validator/modelli gia' esistono
- il quickstart storico puo' contenere esempi non piu' allineati, incluso il port binding

Artefatti da rileggere:
- `specs/035-rbn-api-integration/spec.md`
- `specs/035-rbn-api-integration/plan.md`
- `specs/035-rbn-api-integration/tasks.md`
- `specs/035-rbn-api-integration/quickstart.md`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_CONTRACT_REGISTRY.md`

Prossima fase:
- target task: `T034`
- obiettivo:
  - rendere `quickstart.md` realmente eseguibile rispetto al codice corrente
  - correggere esempi CLI/API/Python se non corrispondono piu' all'implementazione
  - allineare host/port e nomi metodo reali

Vincoli non negoziabili:
- non aprire nuove feature
- non fare refactor del fetcher/validator salvo bug bloccanti emersi direttamente dal quickstart
- non promuovere la route a `:8011`: resta surface research su `:8001`
- non lasciare esempi non testati spacciati come validati

File target:
- `specs/035-rbn-api-integration/quickstart.md`
- `scripts/integrations/rbn_validator.py` solo se scopri un bug reale negli esempi
- `api/main.py` solo se scopri un bug reale negli esempi
- `tests/test_rbn_integration.py` o test dedicati se serve coprire il bug emerso
- `specs/035-rbn-api-integration/tasks.md`

Output richiesto a fine fase:
- Phase completed: spec-035 / quickstart
- Commit: <sha>
- Files changed:
- Commands run:
- Tests run:
- Result:
- Residual risks:
- Ready for review: yes/no

Un solo commit e stop.
```

---

## PROMPT_SPEC035_T040_T041_MVRVZ_CODE_ALIGN

```text
Continua su `spec-035` con focus stretto sulla formula alignment.

Contesto importante:
- usa il workspace locale come baseline
- lo stato reale oggi:
  - `mvrv_z_rbn` esiste gia' come concetto in `scripts/metrics/mvrv_variants.py`
  - `scripts/integrations/metric_loader.py` lo conosce gia'
  - il path storico che parla di `daily_metrics table` non e' piu' allineato: l'architettura attuale usa tabelle giornaliere per metrica, in particolare `mvrv_daily`
- questa fase e' codice/schema alignment, non validazione finale

Artefatti da rileggere:
- `specs/035-rbn-api-integration/spec.md`
- `specs/035-rbn-api-integration/tasks.md`
- `docs/ARCHITECTURE.md`
- `scripts/migrations/consolidate_databases.py`
- `scripts/metrics/calculate_daily_metrics.py`
- `scripts/integrations/metric_loader.py`
- `scripts/integrations/validation_batch.py`

Prossima fase:
- target tasks: `T040`, `T041`
- obiettivo:
  - introdurre un path persistito per `mvrv_z_rbn` nella schema architecture attuale
  - far calcolare e persistire sia `mvrv_z` sia `mvrv_z_rbn`
  - mantenere allineato `metric_loader`

Vincoli non negoziabili:
- non reintrodurre una finta `daily_metrics` table se l'architettura attuale non la usa
- non toccare route/API se non necessario per bug bloccanti
- non cambiare la semantica del `mvrv_z` locale esistente
- aggiungi test mirati se tocchi calcolo o persistenza

File target:
- `scripts/migrations/consolidate_databases.py`
- `scripts/metrics/calculate_daily_metrics.py`
- `scripts/integrations/metric_loader.py`
- test pertinenti
- `specs/035-rbn-api-integration/tasks.md` solo per aggiornare stato reale a fine fase

Output richiesto a fine fase:
- Phase completed: spec-035 / mvrvz-code-align
- Commit: <sha>
- Files changed:
- Tests run:
- Result:
- Residual risks:
- Ready for review: yes/no

Fai un solo commit e fermati.
```

---

## PROMPT_SPEC035_T042_T043_MVRVZ_RECALC_VALIDATE

```text
Continua su `spec-035` dalla fase di validazione, senza scope drift.

Contesto importante:
- questa fase assume che il path persistito `mvrv_z_rbn` sia gia' implementato o comunque disponibile
- il target ora non e' piu' design, ma evidenza:
  - ricalcolo
  - validazione batch
  - verifica del target MAPE
- la baseline va presa dal workspace locale e dagli artifact gia' presenti

Artefatti da rileggere:
- `specs/035-rbn-api-integration/spec.md`
- `specs/035-rbn-api-integration/tasks.md`
- `scripts/metrics/calculate_daily_metrics.py`
- `scripts/integrations/validation_batch.py`
- eventuali artifact o note locali su backfill/validation

Prossima fase:
- target tasks: `T042`, `T043`
- obiettivo:
  - eseguire il recalculation path richiesto
  - rieseguire la validazione `mvrv_z`
  - raccogliere evidenza reale sul MAPE finale

Vincoli non negoziabili:
- non segnare come completati `T042` o `T043` se mancano dati, backfill o token
- se il recalculation completo non e' possibile:
  - documenta il blocker preciso
  - conserva eventuali output parziali utili
  - non falsificare il target `< 10%`
- non aprire nuovo scope API/UI

File target:
- artifact di validazione sotto la spec o cartelle gia' usate dal progetto
- `specs/035-rbn-api-integration/tasks.md`
- eventuali piccoli fix solo se emergono bug bloccanti direttamente da questa fase

Comandi attesi, se l'ambiente lo consente:
- `uv run python -m scripts.metrics.calculate_daily_metrics --recalculate`
- `uv run python -m scripts.integrations.validation_batch --metrics mvrv_z`

Output richiesto a fine fase:
- Phase completed: spec-035 / mvrvz-validate
- Commit: <sha>
- Files changed:
- Commands run:
- Tests or validations run:
- Result:
- Residual risks:
- Ready for review: yes/no

Un solo commit e poi fermati.
```

---

## PROMPT_SPEC035_T044_T050_UPSTREAM_VERSION_RECONCILIATION [DONE]

```text
Continua su `spec-035` con disciplina rigida e senza assumere che la vecchia narrativa "v2 imminente" sia ancora vera.

Contesto importante:
- usa il workspace locale come baseline tecnica
- la spec e' stata riallineata: le date storiche su v2 sono archivistiche, non fatti correnti
- questa fase richiede verificare l'upstream reale prima di cambiare codice
- la surface resta `tier_3_research` su `:8001`

Artefatti da rileggere:
- `specs/035-rbn-api-integration/spec.md`
- `specs/035-rbn-api-integration/tasks.md`
- `specs/035-rbn-api-integration/quickstart.md`
- `api/models/validation_models.py`
- `scripts/integrations/rbn_fetcher.py`
- `scripts/integrations/rbn_validator.py`

Prossima fase:
- target tasks: `T044`-`T050`
- obiettivo:
  - verificare quale versione upstream e' davvero attiva oggi
  - allineare base URL, naming, auth flow e quickstart alla realta'
  - consumare quota/API in modo parsimonioso

Vincoli non negoziabili:
- non assumere automaticamente che v2 abbia superseduto v1
- non cambiare `base_url` o naming solo per seguire la narrativa storica della spec
- se non hai accesso alla documentazione live o alla rete:
  - fermati dopo aver raccolto l'evidenza locale
  - non indovinare
- usa cache/golden data dove possibile per non sprecare quota
- se cambi il contratto runtime reale:
  - aggiorna quickstart e test pertinenti nello stesso commit

File target:
- `api/models/validation_models.py`
- `scripts/integrations/rbn_fetcher.py`
- `scripts/integrations/rbn_validator.py` solo se necessario
- `specs/035-rbn-api-integration/quickstart.md`
- test pertinenti
- `specs/035-rbn-api-integration/tasks.md`

Output richiesto a fine fase:
- Phase completed: spec-035 / upstream-version
- Commit: <sha>
- Files changed:
- Commands run:
- Tests run:
- Result:
- Residual risks:
- Ready for review: yes/no

Fai un solo commit e fermati.
```
