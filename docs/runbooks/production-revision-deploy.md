# Live: release attestata e deploy per digest

Solo operatore dopo review, nessun deploy automatico. Canonico `main` rilevato
14/11/2026: df2c1a7c11a7754bc731baf9b3d2a4ef696e77fe. Riuso Dockerfile.live,
docker-compose.live.yml, health esistenti; la CI self-hosted proviene dalla PR90.
Questa PR dipende dalla sua review/merge; recovery dati separata nella PR91 (#89).
Accettazione operativa differita: #93, prima di qualsiasi aggiornamento live.

## Piano da → a

| Servizio Dell | Da, osservato 14 novembre | A, dopo review | Rischi e verifica |
|---|---|---|---|
| checkout /media/sam/1TB/UTXOracle | 7cc48dd53661f5ba9e0d6285bd5babdf49e4363c; 53 commit mancanti e 36 locali rispetto al main rilevato | checkout Git pulito del main risultante dalle PR90/91 e questa PR | conservare divergenze, niente reset del checkout operativo; verificare HEAD e diff pulito |
| live API | ea4560831e503c6ce34d18739476a71ac6e9a9de non risolvibile, distanza ignota | digest CI di quello stesso main revisionato | health commit_sha e label devono coincidere; HTTP 200 non basta |
| live worker | stessa label ea456083, distanza ignota | stesso digest API | verificare avanzamento live_snapshots e watermark, senza modificare dati per simulare successo |
| data-updater | stessa label ea456083 non risolvibile, distanza ignota | stesso digest API/worker | compatibilità sorgenti e volumi; verificare stato e acquisizione reale |

Il vecchio checkout non è antenato lineare di main: preservare le differenze per
review prima di scegliere la release. La label attuale non è una release Git
risolvibile; nessun conteggio inventato. Il target esatto è lo SHA di main dopo
review, registrato insieme al digest e al run CI: il main fotografato sopra è
un riferimento di confronto, non autorizza un deploy senza le correzioni.

## Build e rilascio

`.github/workflows/live-image.yml` verifica il contratto su PR e costruisce solo
main su `[self-hosted, sg-priv]`, riusando Docker Buildx, metadata e build-push.
Non avvia servizi. Il sommario CI registra `ghcr.io/gptcompany/utxoracle-live`
con digest e SHA completo; la label OCI e COMMIT_SHA ricevono lo SHA della build.
Il login riusa il riferimento GH_PROJECT_PAT già adottato dalla CI di organizzazione.
Il runner e il permesso registry vanno verificati in #93: errore push resta FAIL,
mai spostare la build su GitHub-hosted. Nessuna build su Dell o Mac fuori CI.

## Deploy e verifica operatore

1. Identificare checkout, image ID, digest precedenti di API/worker/updater e
   versione compose. Conservare l'immagine attuale anche se la revisione è ignota;
   se non si può ripristinare e verificare, bloccare il rollout. Conservare i dati
   con la procedura backup esistente e verificare compatibilità schema.
2. Preparare un checkout Git pulito dello SHA approvato; niente copie di codice
   senza .git. Compose resta quella del repository a quello SHA. Le configurazioni
   provengono dall'inventario e i segreti dal deposito esterno già adottato, senza
   stampare environment o `compose config`, senza generare .env nel repository.
3. Impostare `UTXORACLE_LIVE_IMAGE` a `ghcr.io/gptcompany/utxoracle-live@sha256:...`
   nella configurazione esterna approvata, riusata anche ai successivi avvii.
   Pull di quel riferimento esatto, verifica label e digest; aggiornare soltanto
   API/worker/updater con compose `up -d --no-build --wait`. Niente mount di codice
   sotto /app; i soli dati persistenti conservano i bind già versionati.
4. Confrontare i tre image ID/digest e label con lo SHA approvato; controllo
   provenienza monitoring-stack e console servizi devono mostrare zero distanza.
   Verificare `/health`, metadati della build e stato delle sorgenti senza leggere
   credenziali o topic; poi osservare nuovi snapshot e freshness nei gate esistenti.
   La fotografia iniziale mostrava MAX(ts) 16/09 e risposta live indisponibile:
   finché non avanzano i dati il ripristino operativo non è completato (#89/91).
5. Registrare SHA, digest, run CI, esiti e precedente riferimento per rollback.
   Non riavviare Nautilus e non modificare STOPPED/kill_switch=1.

## Rollback

Ripristinare checkout/compose precedenti e immagine conservata per digest, con
`UTXORACLE_LIVE_IMAGE` mantenuto anche agli avvii futuri; ricreare solo i servizi
approvati senza build e ripetere health/freshness. Non cancellare volumi e non
eseguire downgrade di schema senza compatibilità provata. Una label irrisolvibile
non diventa attestata con il rollback: documentarla come finding ancora aperto.
