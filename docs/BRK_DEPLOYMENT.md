# BRK Dell: configurazione versionata, apply separato

Refs gptcompany/gbg-agents#1253. Nessun apply eseguito dalla PR.
Il runbook cookie esistente resta separato e invariato.

## Fotografia e limite (2026-11-12 18:09 UTC, 13 novembre sul Dell)

Container `brk`, avviato il 4 novembre, restart 0, Memory/MemorySwap 0.
Argomenti, mount, progetto Compose `brk`, restart `unless-stopped` e rete host
sono conservati. RPC usa 127.0.0.1; il server HTTP 0.3.6 fa bind hardcoded
**0.0.0.0:7070**, senza flag bind. Il coordinatore ha escluso esplicitamente
il cambio di rete dal task e registra il limite in #1253; nessuna attestazione
loopback. `/health` risponde healthy, versione 0.3.6, tip/indexed/computed 975578.

| Misura | Valore |
|---|---:|
| /proc PID VmRSS | 403848 KiB |
| /proc PID VmSwap | 5732548 KiB |
| /proc PID VmHWM | 7896528 KiB |
| cgroup memory.current | 799342592 byte |
| cgroup memory.peak | 15135117312 byte |
| cgroup memory.swap.current | 5870129152 byte |
| cgroup memory.swap.peak | 6122180608 byte |

RSS + swap = (403848 + 5732548) * 1024 = 6283669504 byte.
Il picco cgroup include cache e supera sia questo totale sia VmHWM:
ceil(max(6283669504, 7896528 * 1024, 15135117312) / 2**30) = **15 GiB**.
Nessun margine percentuale inventato. `mem_limit: 15g` = 16106127360 byte;
`memswap_limit` uguale disabilita lo swap del container. Se il working set
supera il limite il kernel può uccidere brk; Docker lo riavvia per evento OOM
con `unless-stopped`, senza timer. Il vecchio swap non è liberato prima dell’apply.

## Immagine e credenziali

`docker image inspect` risolve il RepoDigest locale
`brk@sha256:ca2e444a0598a5c0847642add4bd3f111ff3cc805b8d51aba10c0cfc2317c6c3`
allo stesso Image ID del container. Tag locale precedente `brk:latest`, creato
il 10 agosto 2026. `pull_policy: never`: non è un digest di registry upstream
pubblicato, non tentare pull o rebuild durante questo passaggio.
Provenienza osservabile: checkout `/data/sata/1TB/brk-v0.3.6`, upstream
https://github.com/bitcoinresearchkit/brk, tag `v0.3.6`, commit
`528880bd046de6a859c5eda24b54fe40f766496a`; Dockerfile locale costruisce
`brk` con Cargo e ENTRYPOINT brk. `/health` conferma versione 0.3.6.
Questa evidenza non costituisce attestazione crittografica della build locale.

Usare il file **esterno al repo**, già esistente e modo 0600:
`/data/sata/1TB/brk-v0.3.6/.env`. Le chiavi `BTC_RPC_USER` e
`BTC_RPC_PASSWORD` alimentano gli stessi argomenti RPC; non leggere/stampare
valori, output completo inspect, argv o `docker compose config` interpolato.
Il binario supporta anche config.toml ma qui non si migra l’autenticazione:
il segreto rimane visibile nell’argv Docker, rischio accettato dall’operatore.
I mount usano BITCOIN_DATA_DIR e BRK_DATA_DIR dal file esterno, con default
versionati uguali ai mount osservati. Nessuna copia plaintext nel repo.

## Apply dopo merge: B5, con autorizzazione dell’operatore

1. Checkout pulito del merge SHA in `/data/sata/1TB/UTXOracle`; registrare SHA.
   Verificare esistenza del digest locale e modo 0600 del file esterno, senza
   emetterne contenuto. I default dell’inventario Dell sono nel compose e nelle
   variabili BRK_COMPOSE_FILE/BRK_ENV_FILE dell’unità: cambiare la sorgente
   versionata per altri host, nessun override/drop-in locale.
2. Registrare `/health` e tip iniziale. Conservare fuori repo il vecchio
   `/etc/systemd/system/brk-stack.service` per rollback. Fermare brk tramite
   la vecchia unità, che usa `/data/sata/1TB/brk-v0.3.6/docker/docker-compose.yml`.
   Nessun `down -v`, nessuna cancellazione di dati.
3. Installare byte per byte `brk-stack.service` dalla checkout al percorso
   systemd esistente, poi daemon-reload e start della stessa unità.
   Il nuovo ExecStart usa direttamente il compose versionato, progetto brk;
   non copiare o generare un secondo compose sull’host.
4. Verificare con il controllo selettivo sotto: digest, entrambi i limiti,
   healthy e tip. Attendere l’indicizzazione di un nuovo blocco e ripetere:
   tip/indexed devono avanzare rispetto alla misura precedente; nessun timeout
   arbitrario. Se non avanzano o il servizio entra in loop OOM, rollback.
5. Confrontare l’unità installata con la sorgente al merge SHA (diff vuoto),
   compose in uso con la stessa sorgente (identità byte), mount effettivi
   con inventario sopra; registrare esito e SHA. Nessun file brk è riscritto
   dal servizio. Il confronto schedulato è coperto dall’inventario di convergenza
   gptcompany/gbg-agents#1247: il coordinatore vi registra brk con questa
   prova d’effetto. Nessun secondo meccanismo viene aggiunto qui.

Controllo selettivo (solo B5 durante apply; non stampa credenziali):

```python
import json
import subprocess
import urllib.request

c = json.loads(subprocess.check_output(["docker", "inspect", "brk"]))[0]
assert c["Image"] == "sha256:ca2e444a0598a5c0847642add4bd3f111ff3cc805b8d51aba10c0cfc2317c6c3"
assert c["HostConfig"]["Memory"] == c["HostConfig"]["MemorySwap"] == 16106127360
with urllib.request.urlopen("http://127.0.0.1:7070/health") as response:
    h = json.load(response)
assert h["status"] == "healthy"
print({k: h[k] for k in ("status", "tip_height", "indexed_height")})
print({"memory": c["HostConfig"]["Memory"], "oom": c["State"]["OOMKilled"],
       "restarts": c["RestartCount"]})
```

## Allarme e rollback

Manca un produttore di metrica restart/OOM per brk: node_exporter Dell è up
nel Prometheus tk-mon ma espone solo node_vmstat_oom_kill dell’intero host.
Il cAdvisor esistente copre k3s, non Docker sul Dell. Nessun secondo meccanismo
installato: metrica e regola nello stack esistente sono finding **UTXOracle#77**,
con criterio di passaggio e scadenza prima dell’apply. Non spacciare un allarme
host per un allarme brk; non forzare OOM sul servizio live per provarlo.

Rollback: fermare la nuova unità, ripristinare l’unità precedente salvata,
daemon-reload e start. Usa compose precedente e stessa .env esterna, mount e
dati conservati. Verificare healthy e tip avanzato come sopra; il rollback
ripristina anche l’assenza di limite, quindi è temporaneo e va registrato
come drift/finding. Nessuna migrazione cookie, modifica RPC o apply in questa PR.
