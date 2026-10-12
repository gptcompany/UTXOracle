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

---

## 3. Consumatori RPC di bitcoind e Strategia di Migrazione

Tutti i consumatori che accedono a Bitcoin Core RPC devono essere gestiti senza interruzioni impreviste:

### Sul nodo Dell
- **`mempool-electrs`** (`/data/4TB/prod/apps/mempool-stack`): consuma bitcoind RPC su `127.0.0.1:8332`.
  - *Migrazione:* Se non configurato con cookie, migrare all'autenticazione `rpcauth` (vedere sotto) prima di rimuovere `rpcpassword`, oppure montare la directory del cookie se supportato dalla versione in uso.
- **`mempool-api`** (`/data/4TB/prod/apps/mempool-stack`): backend mempool.
  - *Migrazione:* Allineare a `rpcauth` o credenziali dedicate se accede a bitcoind RPC.

### Nel repository UTXOracle
- **`live/backend/bitcoin_rpc.py`**: dispone già di fallback nativo su `cookie_path` (`os.path.join(data_dir, ".cookie")`) quando `rpcpassword` non è definita in `bitcoin.conf`.
- **`UTXOracle.py`**: dispone già di fallback automatico su `.cookie`.
- **`scripts/sync_utxo_lifecycle.py`**, **`scripts/daily_analysis.py`**, **`scripts/bootstrap/fast_spent_sync_v2.py`**: script operativi che leggevano `bitcoin.conf`; devono utilizzare il percorso `.cookie` o `rpcauth`.
- **`scripts/setup_full_mempool_stack.sh`**: script legacy di setup; non estrarre più `rpcpassword` in chiaro.

### Strategia di Coesistenza tramite `rpcauth`
Per supportare client legacy remoti o container che non possono leggere il file `.cookie` locale, configurare direttive `rpcauth` in `bitcoin.conf`:
```ini
rpcauth=<username>:<salt>$<hmac_sha256>
```
(generato con lo script ufficiale upstream di Bitcoin Core `share/rpcauth/rpcauth.py`).
In Bitcoin Core v28, la presenza di `rpcauth` in assenza di `rpcpassword` permette a bitcoind di **generare regolarmente il `.cookie`** per BRK e i client locali, consentendo al contempo l'autenticazione username/password standard per i client configurati in `rpcauth`.

---

## 4. Procedura Operativa in 5 Passi con Controlli e Rollback

### Passo 1: Stop di BRK
Arrestare lo stack BRK per evitare tentativi di connessione con credenziali non allineate.

```bash
sudo systemctl stop brk-stack.service
```
- **Controllo:**
  ```bash
  systemctl is-active --quiet brk-stack.service || echo "BRK stack stopped (OK)"
  ```
- **Rollback Passo 1:**
  ```bash
  sudo systemctl start brk-stack.service
  ```

---

### Passo 2: Modifica di `bitcoin.conf` e Restart di bitcoind
Rimuovere `rpcuser` e `rpcpassword` e predisporre il cookie (ed eventuali `rpcauth`).

1. Backup preventivo con preservazione dei permessi:
   ```bash
   cp -p /home/sam/.bitcoin/bitcoin.conf /home/sam/.bitcoin/bitcoin.conf.bak
   # e se presente nella datadir secondaria:
   [ -f /data/cold/12TB/Bitcoin/bitcoin.conf ] && cp -p /data/cold/12TB/Bitcoin/bitcoin.conf /data/cold/12TB/Bitcoin/bitcoin.conf.bak
   ```
2. Modificare `bitcoin.conf`:
   - Rimuovere o commentare le righe `rpcuser=...` e `rpcpassword=...`.
   - Se necessario per i client legacy (es. mempool), aggiungere la riga `rpcauth=...`.
   - Configurare opzionalmente `-rpccookieperms=group` se necessario per il gruppo di sistema (mai world-readable).
3. Riavviare bitcoind:
   ```bash
   sudo systemctl restart bitcoind.service
   ```
- **Controllo:**
  ```bash
  systemctl is-active --quiet bitcoind.service && echo "bitcoind active (OK)"
  # Conteggio, non righe: atteso >= 1
  journalctl -u bitcoind.service -n 200 --no-pager | grep -ci -- 'Using random cookie authentication'
  ```
- **Rollback Passo 2:**
  ```bash
  cp -p /home/sam/.bitcoin/bitcoin.conf.bak /home/sam/.bitcoin/bitcoin.conf
  [ -f /data/cold/12TB/Bitcoin/bitcoin.conf.bak ] && cp -p /data/cold/12TB/Bitcoin/bitcoin.conf.bak /data/cold/12TB/Bitcoin/bitcoin.conf
  sudo systemctl restart bitcoind.service
  ```

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
- **Rollback Passo 3:**
  Se il file non esiste o non è leggibile, interrompere la procedura e ripristinare `bitcoin.conf`:
  eseguire **Rollback Passo 2**.

---

### Passo 4: Aggiornamento Configurazione e Avvio di BRK
Aggiornare il docker-compose di BRK per utilizzare il flag cookie nativo ed eliminare i flag argv.

1. Backup preventivo dei file di configurazione di BRK:
   ```bash
   cp -p /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml.bak
   cp -p /data/sata/1TB/brk-v0.3.6/.env /data/sata/1TB/brk-v0.3.6/.env.bak
   ```
2. Modificare `/data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml`:
   - Rimuovere o commentare gli argomenti `--rpcuser` e `--rpcpassword`.
   - Utilizzare il flag cookie nativo:
     ```yaml
     - --rpccookiefile
     - /bitcoin/.cookie
     ```
3. Modificare `/data/sata/1TB/brk-v0.3.6/.env`:
   - Rimuovere le variabili `BTC_RPC_USER` e `BTC_RPC_PASSWORD`.
4. Avviare il servizio BRK:
   ```bash
   sudo systemctl start brk-stack.service
   ```
- **Controllo:**
  ```bash
  systemctl is-active --quiet brk-stack.service && echo "BRK stack active (OK)"
  # Solo i NOMI dei flag trovati negli argv di tutti i processi, con il conteggio: mai i valori.
  ps -eo args= | grep -oE -- '-{1,2}rpc(user|password)' | sort | uniq -c
  ```
  *(Atteso: nessun output. Qualsiasi riga indica un flag credenziale ancora presente in argv.
  Non usare `ps` senza questo filtro, `docker inspect` né `cat` di file di configurazione: stampano i valori.)*
- **Rollback Passo 4:**
  ```bash
  sudo systemctl stop brk-stack.service
  cp -p /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml.bak /data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml
  cp -p /data/sata/1TB/brk-v0.3.6/.env.bak /data/sata/1TB/brk-v0.3.6/.env
  sudo systemctl start brk-stack.service
  ```

---

### Passo 5: Health Check sulla Porta :7070
Verificare che BRK risponda correttamente e si sia autenticato con successo a bitcoind via cookie.

```bash
curl -fsS http://127.0.0.1:7070/health && echo "BRK health endpoint OK"
```
- **Controllo:**
  Il comando `curl -fsS` fallisce con codice di uscita diverso da 0 se l'endpoint risponde con errori HTTP (es. 500 Authentication Failed o 401).
  Contare, senza stamparle, le righe di errore di autenticazione nei log recenti di BRK:
  ```bash
  docker logs --tail 200 brk 2>&1 | grep -ciE -- 'unauthorized|authentication failed|401|403'
  ```
  *(Atteso: 0. Non leggere i log di BRK non filtrati: possono contenere i valori delle credenziali).*
- **Rollback Passo 5:**
  In caso di errore nell'endpoint `/health`:
  1. Eseguire **Rollback Passo 4**.
  2. Se necessario ripristinare anche bitcoind, eseguire **Rollback Passo 2**.
