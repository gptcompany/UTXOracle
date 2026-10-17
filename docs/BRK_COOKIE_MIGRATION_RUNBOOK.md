# Runbook: Migrazione BRK ad Autenticazione Cookie Bitcoin Core

Questo runbook definisce la procedura operativa ordinata per la rimozione delle credenziali RPC bitcoind passate come argomenti da riga di comando (`argv`) in BRK e l'adozione dell'autenticazione nativa tramite file cookie (`.cookie`).

---

## 1. Riferimento Tecnico e Meccanismo Cookie (Bitcoin Core v28.0)

Nel sorgente ufficiale di Bitcoin Core v28.0 ([`src/httprpc.cpp`, funzione `InitRPCAuthentication`](https://github.com/bitcoin/bitcoin/blob/v28.0/src/httprpc.cpp#L293-L316)):

```cpp
static bool InitRPCAuthentication()
{
    if (gArgs.GetArg("-rpcpassword", "") == "")
    {
        LogInfo("Using random cookie authentication.\n");
        // ...
        if (!GenerateAuthCookie(&strRPCUserColonPass, cookie_perms)) {
            return false;
        }
    } else {
        LogPrintf("Config options rpcuser and rpcpassword will soon be deprecated...\n");
        strRPCUserColonPass = gArgs.GetArg("-rpcuser", "") + ":" + gArgs.GetArg("-rpcpassword", "");
    }
```

- **Requisito fondamentale:** Bitcoin Core genera il file `.cookie` casuale (`GenerateAuthCookie`) **solo quando `rpcpassword` è vuota o assente**. Se `rpcpassword` rimane valorizzata in `bitcoin.conf`, bitcoind **non** genera il cookie.
- Di conseguenza, l'operatore **deve rimuovere** (o commentare) sia `rpcpassword` che `rpcuser` dal file `bitcoin.conf`.
- **Permessi del cookie e accesso BRK:**
  - `InitRPCAuthentication` supporta il parametro `-rpccookieperms` con valori consentiti `'owner'`, `'group'`, `'all'`.
  - Non configurare **mai** permessi world-readable (`all` o `chmod 0666/0644`).
  - Sul Dell, bitcoind e il container BRK eseguono con UID 1000, e il mount `/data/cold/12TB/Bitcoin` -> `/bitcoin:ro` garantisce la lettura diretta con i permessi proprietario predefiniti (`owner`, 0600).
  - Se necessario per utenti dello stesso gruppo di sistema, usare `-rpccookieperms=group` (0640).

---

## 2. Finestra di Interruzione (Downtime Window)

La procedura comporta le seguenti finestre di indisponibilità controllate:
1. **BRK (`:7070`):** arrestato al Passo 1 e riavviato al Passo 4. Finestra di interruzione stimata: **~2-5 minuti**. Durante questo intervallo, i consumatori di BRK (`utxoracle-live-worker`, `utxoracle-live-api`) riceveranno errori temporanei di connessione verso la porta :7070.
2. **Bitcoin Core RPC (`:8332`):** indisponibile durante il riavvio del demone al Passo 2. Finestra di interruzione stimata: **~15-30 secondi**. Tutte le chiamate RPC verso bitcoind saranno temporaneamente rifiutate.
3. **Consumatori RPC (`mempool-electrs`, `mempool-api`, UTXOracle):** riavviati al Passo 2 dopo bitcoind, per caricare la nuova credenziale. La durata è quella del riavvio dei loro container: da misurare in prova, non stimata qui.

---

## 3. Consumatori RPC di bitcoind e Strategia di Migrazione

Tutti i consumatori che accedono a Bitcoin Core RPC devono essere gestiti senza interruzioni impreviste:

### Sul nodo Dell
- **`mempool-electrs`** (`/data/4TB/prod/apps/mempool-stack`): consuma bitcoind RPC su `127.0.0.1:8332`.
  - *Migrazione:* Se non configurato con cookie, migrare all'autenticazione `rpcauth` (vedere sotto) prima di rimuovere `rpcpassword`, oppure montare la directory del cookie se supportato dalla versione in uso.
- **`mempool-api`** (`/data/4TB/prod/apps/mempool-stack`): backend mempool.
  - *Migrazione:* Allineare a `rpcauth` o credenziali dedicate se accede a bitcoind RPC.

### Nel repository UTXOracle (inventario dei consumatori)

Inventario ricavato con ast-grep e ricerca strutturale su `BITCOIN_RPC_*`, `rpcuser`, `rpcpassword`, `.cookie`, `bitcoin-cli` (esclusi `archive/`). Dopo la PR il cookie ha la precedenza su utente e password; `rpcuser`/`rpcpassword` restano come fallback solo perché il Rollback Coordinato (sezione 5) li reinstalla in `bitcoin.conf`.

| Consumatore | Contesto | Autenticazione | Rilettura cookie | Riavvio dopo bitcoind | Credenziali vecchie da rimuovere |
|---|---|---|---|---|---|
| `live/backend/bitcoin_rpc.py` (`utxoracle-live.service`, `live.backend.api`) | host, utente `utxoracle`; controllo `rpc_check ... host live <unità>` | cookie, poi fallback utente/password (risoluzione: vedi sotto) | su HTTP 401, una volta | consigliato: libera dalla memoria il fallback letto all'avvio | `rpcuser`/`rpcpassword` in `bitcoin.conf` |
| `scripts/sync_utxo_lifecycle.py` (`BitcoinRPC`, usato anche da `api/routes/streams.py` e da `scripts/bootstrap/{tip_catchup_lifecycle_via_rpc,tip_spent_backfill_via_rpc,sync_spent_utxos,build_block_heights_questdb}.py`) | host, `uv run`; controllo `rpc_check ... host sync <unità>` | cookie, poi fallback utente/password (risoluzione: vedi sotto) | su HTTP 401, una volta | processi lunghi sì; i job periodici ripartono da soli | `BITCOIN_RPC_USER`/`BITCOIN_RPC_PASSWORD` in `/media/sam/1TB/UTXOracle/.env` |
| `scripts/daily_analysis.py` (`_fetch_from_bitcoin_core`, `fetch_historical_transactions`, factory `rpc_client`) | host, job cron; controllo `rpc_check ... cron daily ...` | cookie, poi fallback utente/password (risoluzione: vedi sotto); accetta la sola configurazione cookie | a ogni job | no | `rpcuser`/`rpcpassword` in `bitcoin.conf` |
| `scripts/bootstrap/fast_spent_sync_v2.py`, `historical_spent_backfill.py`, `run_combined_bootstrap.py` | host, batch lunghi | connessione da `resolve_target`; utente/password (variabili, poi `bitcoin.conf` della datadir risolta) prima, cookie solo come ripiego, letto una volta | no | **fermarli prima di riavviare bitcoind e rilanciarli dopo** (comandi di ripresa: Passo 2, punto 4) | `BITCOIN_RPC_USER`/`BITCOIN_RPC_PASSWORD` nell'ambiente di lancio |
| `scripts/bootstrap/fast_spent_sync.py`, `build_block_heights.py` | host, batch | connessione da `resolve_target` (`build_block_heights`: salvo `--rpc-url`/`--rpc-cookie` espliciti); solo cookie, letto una volta | no | fermarli e rilanciarli dopo (comandi di ripresa: Passo 2, punto 4) | nessuna |
| `UTXOracle.py` (immutabile), `scripts/diagnose_streams_health.py`, `scripts/validate_brk_integration.py`, `scripts/bootstrap/{bootstrap_utxo_lifecycle,spec061_post_mirror_chain}.sh` | `bitcoin-cli` | `bitcoin-cli` rilegge il cookie a ogni invocazione | a ogni chiamata | no | nessuna |
| `scripts/whale_flow_detector.py` | host | credenziali opzionali del costruttore; nessun chiamante le passa | n/a | no | nessuna |
| `scripts/setup_full_mempool_stack.sh` | setup legacy | estrae `rpcuser`/`rpcpassword` da `bitcoin.conf` | n/a | non eseguirlo dopo la migrazione | non usarlo |
| `api/main.py` (mining-pulse, righe 2668 e 2764) | host | importa `scripts.bitcoin_rpc`, modulo inesistente: già non funzionante, fuori ambito | n/a | no | nessuna |

Risoluzione della connessione dei tre consumatori migrati: un solo punto, `resolve_target` in `scripts/utils/rpc_cookie.py`, con la semantica di Bitcoin Core v28 (rete da `chain=`/`regtest=`/`testnet=`/`testnet4=`/`signet=`, sezione della rete attiva prima del default, opzioni network-only come `rpcport` dal default solo su main, primo valore vincente, cookie relativo nella sottodirectory di rete, `includeconf=` rifiutato). La precedenza tra argomento, `BITCOIN_DATADIR`, `BITCOIN_RPC_URL`, `BITCOIN_RPC_USER`/`BITCOIN_RPC_PASSWORD` e `bitcoin.conf` è documentata solo nella docstring di quella funzione e vale per tutti e tre: con `BITCOIN_DATADIR` impostato anche `bitcoin.conf` si legge da quella directory, come `bitcoin-cli -datadir`.

I batch di `scripts/bootstrap/` risolvono datadir, rete, host, porta e percorso del cookie con `resolve_target` come gli altri consumatori (senza `BITCOIN_DATADIR` la datadir predefinita è ora quella di Bitcoin Core, non più `/media/sam/3TB-WDC/Bitcoin`: lanciarli con `BITCOIN_DATADIR` come nei loro esempi), ma mantengono il proprio client e la propria politica di autenticazione (one-shot, nessuna rilettura del cookie): l'ordine di riavvio sopra li protegge. Convertirli al client condiviso `RpcClient` è un seguito da tracciare.

Fuori dal repository, sul Dell:
- **`brk`** (container): legge il cookie dal mount `/bitcoin:ro` con UID 1000 (Passo 4).
- **`mempool-electrs`**, **`mempool-api`**: vedere la sezione 3 sopra (`rpcauth` o cookie montato).

### Strategia di Coesistenza tramite `rpcauth`
Per supportare client legacy remoti o container che non possono leggere il file `.cookie` locale, configurare direttive `rpcauth` in `bitcoin.conf`:
```ini
rpcauth=<username>:<salt>$<hmac_sha256>
```
(generato con lo script ufficiale upstream di Bitcoin Core `share/rpcauth/rpcauth.py`).
In Bitcoin Core v28, la presenza di `rpcauth` in assenza di `rpcpassword` permette a bitcoind di **generare regolarmente il `.cookie`** per BRK e i client locali, consentendo al contempo l'autenticazione username/password standard per i client configurati in `rpcauth`.

---

## 4. Procedura Operativa in 5 Passi con Controlli e Rollback

**Regola di output:** nessun comando di questa procedura stampa un valore. I controlli mostrano soltanto nomi di flag, conteggi, esiti e codici HTTP. Non usare `cat`, `docker inspect`, `docker exec` né `ps`/`docker logs`/`journalctl` senza i filtri indicati: stampano le credenziali.

**Rollback:** ogni passo che ha modificato bitcoind, un consumatore o BRK si annulla soltanto con il **Rollback Coordinato** (sezione 5): ripristinare un solo lato lascia server e client con autenticazioni incompatibili (HTTP 401, riprodotto con Bitcoin Core v28.0.0 in regtest nella review R2).

### Preparazione (prima del Passo 1): backup e verifica RPC

Backup di tutto ciò che il Rollback Coordinato dovrà ripristinare, in una directory 0700, e definizione del controllo RPC reale usato nei passi successivi.

```bash
BK=/home/sam/brk-cookie-migration-backup
install -d -m 700 "$BK"
# bitcoind
cp -p /home/sam/.bitcoin/bitcoin.conf "$BK/bitcoin.conf"
[ -f /data/cold/12TB/Bitcoin/bitcoin.conf ] && cp -p /data/cold/12TB/Bitcoin/bitcoin.conf "$BK/bitcoin.conf.cold"
# BRK
cp -p /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml "$BK/brk-docker-compose.yml"
cp -p /data/sata/1TB/brk-v0.3.6/.env "$BK/brk.env"
# consumatori RPC: stack mempool (mempool-electrs, mempool-api) e UTXOracle
cp -p /data/4TB/prod/apps/mempool-stack/docker-compose.yml "$BK/mempool-docker-compose.yml"
[ -f /data/4TB/prod/apps/mempool-stack/.env ] && cp -p /data/4TB/prod/apps/mempool-stack/.env "$BK/mempool.env"
cp -p /media/sam/1TB/UTXOracle/.env "$BK/utxoracle.env"
```
- **Controllo:** `ls -l "$BK" | wc -l` deve contare tutti i file copiati; ogni consumatore RPC elencato nella sezione 3 deve avere il proprio file di configurazione nel backup. Se un consumatore ha altri file di configurazione RPC, aggiungerli all'elenco prima di procedere.
- **Credenziale legacy** (usata solo dai controlli post-rollback), estratta dal backup senza stamparla:
  ```bash
  ( umask 077; { sed -n 's/^rpcuser=//p' "$BK/bitcoin.conf"; sed -n 's/^rpcpassword=//p' "$BK/bitcoin.conf"; } | paste -sd: - > "$BK/legacy.cred" )
  ```

Controllo RPC reale, **attraverso ogni consumatore nel suo contesto**, non dall'host: il controllo gira nel container del consumatore (stesso UID, stesso mount, stesso file di credenziale) oppure, per i consumatori UTXOracle, con il codice del consumatore stesso. Un consumatore UTXOracle è certificato solo dal suo codice: `rpc_check <etichetta> host|cron <live|sync|daily> ...` esegue `python -m scripts.utils.rpc_cookie <etichetta> <consumatore>`, che costruisce il client con la factory di produzione di quel consumatore (`CONSUMERS` in `scripts/utils/rpc_cookie.py`) e non accetta datadir, porta, cookie o credenziali. Il ramo `host` lo lancia con `systemd-run --wait --pipe --collect` usando utente, gruppi, working directory, `Environment`/`EnvironmentFile` e isolamento (`ProtectHome`, `ProtectSystem`, `PrivateTmp`, `PrivateNetwork`, percorsi, filtri IP) letti con `systemctl show -P` dall'unità reale, senza stamparli; un'unità con `PassEnvironment` non è riproducibile e dà FAIL. Il ramo `cron` usa utente, directory e ambiente minimo di cron della riga di crontab. Mai dalla shell dell'operatore: un client costruito con i parametri del controllo non certifica il consumatore. Un cookie montato male o una password rimasta in memoria danno HTTP 401 qui, anche se l'host riceve 200. L'output è solo etichetta, esito e codice HTTP. `/health` di BRK **non** sostituisce questo controllo: non tocca bitcoind.

```bash
rpc_check() {  # uso: rpc_check <etichetta> ctr <container> <uid:gid> <file credenziale nel container, oppure - per stdin> <url> | rpc_check <etichetta> host <live|sync|daily> <unità systemd> | rpc_check <etichetta> cron <live|sync|daily> <utente> <directory> <uv assoluto>
  local code p v f flag; local -a props=() launcher=()
  case "$2" in
    ctr) code=$(docker exec -i -u "$4" "$3" sh -c 'command -v curl >/dev/null || { printf n/a; exit 0; }; printf "user = \"%s\"\n" "$(cat "$1")" | curl -sS -K - -o /dev/null -w "%{http_code}" --max-time 10 -H "content-type: text/plain;" --data-binary "{\"jsonrpc\":\"1.0\",\"id\":\"chk\",\"method\":\"getblockcount\",\"params\":[]}" "$2"' _ "$5" "$6" 2>/dev/null) ;;
    host|cron)
      case "$3" in live|sync|daily) ;; *) echo "$1: FAIL consumatore sconosciuto"; return 2 ;; esac
      if [ "$2" = host ]; then  # contesto ricavato dall'unità reale; i valori non vengono stampati
        [ -n "$(systemctl show -P PassEnvironment "$4")" ] && { echo "$1: FAIL PassEnvironment non riproducibile"; return 2; }
        for p in User Group SupplementaryGroups DynamicUser WorkingDirectory Environment UnsetEnvironment ProtectHome ProtectSystem PrivateTmp PrivateNetwork PrivateUsers ReadWritePaths ReadOnlyPaths InaccessiblePaths BindPaths BindReadOnlyPaths TemporaryFileSystem RootDirectory IPAddressAllow IPAddressDeny RestrictAddressFamilies; do
          v=$(systemctl show -P "$p" "$4"); [ -n "$v" ] && props+=(-p "$p=$v")
        done
        while read -r f flag; do
          [ -n "$f" ] && props+=(-p "EnvironmentFile=$([ "$flag" = "(ignore_errors=yes)" ] && printf -)$f")
        done < <(systemctl show -P EnvironmentFiles "$4")
        launcher=(/usr/bin/env uv)
      else  # job cron: utente, directory e ambiente minimo di cron, più le variabili della riga (CRON_ENV)
        props=(-p "User=$4" -p "WorkingDirectory=$5" -p "Environment=PATH=/usr/bin:/bin SHELL=/bin/sh ${CRON_ENV:-}")
        launcher=("$6")
      fi
      sudo systemd-run --quiet --wait --pipe --collect "${props[@]}" "${launcher[@]}" run python -m scripts.utils.rpc_cookie "$1" "$3"; return ;;
  esac
  echo "$1: HTTP ${code:-000}"
}
```
Contesto reale di ciascun consumatore, da compilare dalla configurazione effettiva (`docker compose config`, `systemctl cat`), non a memoria:
```bash
RPC_URL=http://127.0.0.1:8332/          # indirizzo RPC come lo vede il consumatore (rete host)
LIVE_UNIT=utxoracle-live.service        # unità reale di live (systemctl cat, non a memoria)
SYNC_UNIT=utxoracle-api.service         # api/routes/streams.py usa scripts.sync_utxo_lifecycle.BitcoinRPC
DAILY_CRON=(sam /media/sam/1TB/UTXOracle /home/sam/.cargo/bin/uv)   # utente, cd e uv della riga di crontab di daily_analysis
CRON_ENV=                               # variabili assegnate nella riga di crontab, se presenti
BRK_CRED=/bitcoin/.cookie               # percorso del cookie NEL container brk (mount :ro, UID 1000)
ELECTRS_UID=1000:1000; ELECTRS_CRED=/path/nel/container/electrs.cred   # file che electrs carica davvero
MEMPOOL_API_UID=1000:1000; MEMPOOL_API_CRED=/path/nel/container/api.cred
```

Atteso: `HTTP 200` per ogni consumatore. `HTTP 401` = credenziale non accettata dal consumatore; `HTTP 000` = bitcoind non raggiungibile; `HTTP n/a` = il container non ha `curl`: aggiungere la prova al ciclo di vita del client (i client UTXOracle usano i rami `host`/`cron`, non `ctr`). `FAIL consumatore sconosciuto` = il ramo `host`/`cron` accetta solo `live`, `sync`, `daily`. Mai stampare il file di credenziale.

---

### Passo 1: Stop di BRK
Arrestare lo stack BRK per evitare tentativi di connessione con credenziali non allineate.

```bash
sudo systemctl stop brk-stack.service
```
- **Controllo:**
  ```bash
  systemctl is-active --quiet brk-stack.service || echo "BRK stack stopped (OK)"
  ```
- **Rollback Passo 1:** nulla è stato ancora modificato: riavviare BRK.
  ```bash
  sudo systemctl start brk-stack.service
  ```

---

### Passo 2: bitcoin.conf, credenziali dei consumatori e restart di bitcoind
Rimuovere `rpcuser` e `rpcpassword` da bitcoind e dare a ogni consumatore che non legge il cookie una credenziale `rpcauth` propria, prima del riavvio.

1. Per ogni consumatore legacy (`mempool-electrs`, `mempool-api`) generare la credenziale con lo script ufficiale upstream; l'output contiene la password, quindi va solo su file 0600, mai al terminale:
   ```bash
   ( umask 077; python3 share/rpcauth/rpcauth.py mempool-electrs > "$BK/mempool-electrs.rpcauth.out" )
   grep '^rpcauth=' "$BK/mempool-electrs.rpcauth.out" >> /home/sam/.bitcoin/bitcoin.conf
   ( umask 077; printf '%s:%s' mempool-electrs "$(tail -n 1 "$BK/mempool-electrs.rpcauth.out")" > "$BK/mempool-electrs.cred" )
   ```
   Ripetere per `mempool-api` (file `mempool-api.cred`). Il formato dell'output è quello dello script installato: se `tail -n 1` non è la password, correggere prima di proseguire senza stampare il file.
2. Modificare `bitcoin.conf`: rimuovere o commentare `rpcuser=...` e `rpcpassword=...` (anche nella datadir secondaria `/data/cold/12TB/Bitcoin/bitcoin.conf`, se presente). Opzionale: `-rpccookieperms=group` (mai world-readable).
3. Aggiornare la configurazione di `mempool-electrs` e `mempool-api` in `/data/4TB/prod/apps/mempool-stack` con le nuove credenziali (editor, non `cat`). I consumatori UTXOracle dell'inventario (sezione 3) usano il cookie con precedenza su utente e password, ma le credenziali vecchie vanno comunque tolte: rimuovere `BITCOIN_RPC_USER` e `BITCOIN_RPC_PASSWORD` da `/media/sam/1TB/UTXOracle/.env` (editor, non `cat`) e dall'ambiente di lancio dei batch.
4. Ordine di riavvio, dopo avere fermato i batch lunghi (`historical_spent_backfill`, `fast_spent_sync*`, `run_combined_bootstrap`) che tengono la credenziale in memoria: bitcoind; poi `mempool-electrs`/`mempool-api`; poi `utxoracle-live.service` (libera il fallback letto all'avvio) e i job che rileggono l'ambiente; infine i batch fermati, rilanciati con il comando di ripresa del proprio CLI (blocco sotto). BRK resta fermo fino al Passo 4.
   ```bash
   sudo systemctl restart bitcoind.service
   docker compose -f /data/4TB/prod/apps/mempool-stack/docker-compose.yml up -d
   sudo systemctl restart utxoracle-live.service
   ```
   Ripresa dei batch fermati. Solo `historical_spent_backfill` e `run_combined_bootstrap` hanno un flag di ripresa (nel blocco sotto) e un checkpoint su disco. `fast_spent_sync` e `fast_spent_sync_v2` non hanno checkpoint: raccolgono gli input e applicano un unico `UPDATE` finale, idempotente, quindi un lancio fermato non ha scritto nulla e si ripete con lo stesso `--start-block`/`--end-block` (annotarli prima dello stop; i log mostrano solo conteggi e altezze). `build_block_heights` salta le altezze già presenti: stessi flag del lancio fermato.
   ```bash
   uv run python -m scripts.bootstrap.historical_spent_backfill --resume
   uv run python -m scripts.bootstrap.run_combined_bootstrap --resume
   uv run python -m scripts.bootstrap.fast_spent_sync --start-block <START> --end-block <END> --fast-mode
   uv run python -m scripts.bootstrap.fast_spent_sync_v2 --start-block <START> --end-block <END>
   uv run python -m scripts.bootstrap.build_block_heights --use-rpc
   ```
- **Controllo:**
  ```bash
  systemctl is-active --quiet bitcoind.service && echo "bitcoind active (OK)"
  # Conteggio, non righe: atteso >= 1
  journalctl -u bitcoind.service -n 200 --no-pager | grep -ci -- 'Using random cookie authentication'
  rpc_check "utxoracle-live (cookie)" host live "$LIVE_UNIT"
  rpc_check "utxoracle-sync (cookie)" host sync "$SYNC_UNIT"
  rpc_check "utxoracle-daily (cookie)" cron daily "${DAILY_CRON[@]}"
  rpc_check "mempool-electrs (rpcauth)" ctr mempool-electrs "$ELECTRS_UID" "$ELECTRS_CRED" "$RPC_URL"
  rpc_check "mempool-api (rpcauth)" ctr mempool-api "$MEMPOOL_API_UID" "$MEMPOOL_API_CRED" "$RPC_URL"
  ```
- **Rollback Passo 2:** eseguire il **Rollback Coordinato** (sezione 5).

---

### Passo 3: Verifica che il Cookie Esista e Sia Leggibile
Accertarsi che il file `.cookie` sia stato generato e sia accessibile in lettura dall'utente di BRK (UID 1000).

- **Controllo:**
  ```bash
  test -r /data/cold/12TB/Bitcoin/.cookie && echo "Cookie readable on host (OK)"
  # Verifica permessi (attesi 0600 o 0640, UID 1000 - MAI world-readable):
  stat -c "%a %u:%g" /data/cold/12TB/Bitcoin/.cookie
  ```
  *(Nota di sicurezza: NON stampare né visualizzare il contenuto del file cookie).*
- **Rollback Passo 3:** se il file non esiste o non è leggibile, interrompere la procedura ed eseguire il **Rollback Coordinato** (sezione 5).

---

### Passo 4: Aggiornamento Configurazione e Avvio di BRK
Aggiornare il docker-compose di BRK per utilizzare il flag cookie nativo ed eliminare i flag argv. Il backup è già in `$BK` (Preparazione).

1. Modificare `/data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml`:
   - Rimuovere o commentare gli argomenti `--rpcuser` e `--rpcpassword`.
   - Utilizzare il flag cookie nativo e il datadir in sola lettura:
     ```yaml
     command:
       - --rpccookiefile
       - /bitcoin/.cookie
     volumes:
       - /data/cold/12TB/Bitcoin:/bitcoin:ro
     ```
2. Modificare `/data/sata/1TB/brk-v0.3.6/.env`: rimuovere le variabili `BTC_RPC_USER` e `BTC_RPC_PASSWORD`.
3. Avviare il servizio BRK:
   ```bash
   sudo systemctl start brk-stack.service
   ```
- **Controllo:**
  ```bash
  systemctl is-active --quiet brk-stack.service && echo "BRK stack active (OK)"
  # Solo i NOMI dei flag trovati negli argv di tutti i processi, con il conteggio: mai i valori.
  # shellcheck disable=SC2009  (pgrep non stampa solo i nomi dei flag)
  ps -eo args= | grep -oE -- '-{1,2}rpc(user|password)' | sort | uniq -c
  ```
  *(Atteso: nessun output. Qualsiasi riga indica un flag credenziale ancora presente in argv.
  Non usare `ps` senza questo filtro, `docker inspect` né `cat` di file di configurazione: stampano i valori.)*
- **Rollback Passo 4:** eseguire il **Rollback Coordinato** (sezione 5).

---

### Passo 5: Verifica RPC Reale e Health Check
`/health` di BRK usa solo stato locale: risponde 200 anche con autenticazione RPC rotta e non certifica la connessione a bitcoind. La prova valida è la chiamata RPC reale per client.

```bash
rpc_check "brk (cookie)" ctr brk 1000:1000 "$BRK_CRED" "$RPC_URL"
rpc_check "utxoracle-live (cookie)" host live "$LIVE_UNIT"
rpc_check "utxoracle-sync (cookie)" host sync "$SYNC_UNIT"
rpc_check "utxoracle-daily (cookie)" cron daily "${DAILY_CRON[@]}"
rpc_check "mempool-electrs (rpcauth)" ctr mempool-electrs "$ELECTRS_UID" "$ELECTRS_CRED" "$RPC_URL"
rpc_check "mempool-api (rpcauth)" ctr mempool-api "$MEMPOOL_API_UID" "$MEMPOOL_API_CRED" "$RPC_URL"
curl -sS -o /dev/null -w 'brk /health: HTTP %{http_code}\n' --max-time 10 http://127.0.0.1:7070/health
```
- **Controllo:** `HTTP 200` su tutte le righe `rpc_check`; `/health` è solo un controllo di processo e non certifica l'autenticazione. Contare, senza stamparle, le righe di errore di autenticazione nei log recenti di BRK:
  ```bash
  docker logs --tail 200 brk 2>&1 | grep -ciE -- 'unauthorized|authentication failed|401|403'
  ```
  *(Atteso: 0. Non leggere i log di BRK non filtrati: possono contenere i valori delle credenziali).*
- **Rollback Passo 5:** eseguire il **Rollback Coordinato** (sezione 5).

---

## 5. Rollback Coordinato

Si applica a qualunque fallimento dal Passo 2 in poi. L'ordine è obbligatorio: bitcoind per primo, poi i consumatori, infine BRK. Ripristinare BRK prima di bitcoind lo fa autenticare con credenziali che bitcoind non accetta più (HTTP 401).

- **R1 — bitcoind**: fermare BRK se attivo, ripristinare `bitcoin.conf` dal backup e riavviare bitcoind.
  ```bash
  sudo systemctl stop brk-stack.service
  cp -p "$BK/bitcoin.conf" /home/sam/.bitcoin/bitcoin.conf
  [ -f "$BK/bitcoin.conf.cold" ] && cp -p "$BK/bitcoin.conf.cold" /data/cold/12TB/Bitcoin/bitcoin.conf
  sudo systemctl restart bitcoind.service
  # Con rpcpassword ripristinata il cookie non deve esistere: un file residuo (arresto non pulito) ha la precedenza nei client.
  test ! -e /data/cold/12TB/Bitcoin/.cookie && echo "no stale cookie (OK)"
  ```
- **R2 — consumatori**: riportare ogni consumatore alla propria configurazione di backup e riavviarlo.
  ```bash
  cp -p "$BK/mempool-docker-compose.yml" /data/4TB/prod/apps/mempool-stack/docker-compose.yml
  [ -f "$BK/mempool.env" ] && cp -p "$BK/mempool.env" /data/4TB/prod/apps/mempool-stack/.env
  cp -p "$BK/utxoracle.env" /media/sam/1TB/UTXOracle/.env
  docker compose -f /data/4TB/prod/apps/mempool-stack/docker-compose.yml up -d
  sudo systemctl restart utxoracle-live.service
  ```
  Rilanciare anche i batch fermati al Passo 2 e i job che rileggono `/media/sam/1TB/UTXOracle/.env`.
- **R3 — BRK**: ripristinare compose e `.env` di BRK dal backup e avviarlo.
  ```bash
  cp -p "$BK/brk-docker-compose.yml" /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml
  cp -p "$BK/brk.env" /data/sata/1TB/brk-v0.3.6/.env
  sudo systemctl start brk-stack.service
  ```
- **R4 — verifica**: una chiamata RPC reale per consumatore, nel suo contesto (container o entrypoint). Per i container la credenziale legacy è passata su stdin da `legacy.cred` (contesto di rete e UID reali, non il mount): la credenziale che il client carica davvero la prova il suo avvio. UTXOracle usa il fallback `rpcuser`/`rpcpassword` di `bitcoin.conf` ripristinato. `/health` di BRK non sostituisce questa prova.
  ```bash
  rpc_check "brk (legacy)" ctr brk 1000:1000 - "$RPC_URL" < "$BK/legacy.cred"
  rpc_check "utxoracle-live (legacy)" host live "$LIVE_UNIT"
  rpc_check "utxoracle-sync (legacy)" host sync "$SYNC_UNIT"
  rpc_check "utxoracle-daily (legacy)" cron daily "${DAILY_CRON[@]}"
  rpc_check "mempool-electrs (legacy)" ctr mempool-electrs "$ELECTRS_UID" - "$RPC_URL" < "$BK/legacy.cred"
  rpc_check "mempool-api (legacy)" ctr mempool-api "$MEMPOOL_API_UID" - "$RPC_URL" < "$BK/legacy.cred"
  ```
  Atteso: `HTTP 200` su ogni riga.

**Avvertenza di sicurezza:** il rollback riattiva `rpcuser`/`rpcpassword`, una credenziale da considerare compromessa perché è stata esposta in argv e nei log. Lo stato dopo il rollback è temporaneo: va seguito senza ritardo dalla rotazione della credenziale (nuova password oppure migrazione al cookie), non lasciato come configurazione definitiva.
