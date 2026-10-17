# Gate statico BRK: cookie RPC, niente credenziali in argv

Il gate è `tests/rpc_argv_gate.py`, eseguito da `tests/test_rpc_security.py`.

## Cosa verifica

1. **Completezza.** Ogni file del repo che avvia BRK (una unit systemd, oppure un YAML con `services` di primo livello che cita `brk` o `bitcoinresearchkit`) deve essere elencato nel manifest `docs/contracts/brk_deployed_files.json`, qualunque sia il suo nome. Un file non elencato fa fallire il gate.
2. **Invarianti testuali sui soli file elencati.** Nessun `rpcpassword` né `rpcuser` (maiuscole e commenti inclusi) e `--rpccookiefile` presente.

Il manifest è validato con lo schema `docs/contracts/brk_deployed_files.schema.json` (jsonschema, lo stesso motore di `check-jsonschema`):

```bash
check-jsonschema --schemafile docs/contracts/brk_deployed_files.schema.json docs/contracts/brk_deployed_files.json
```

Oggi il manifest è vuoto: nessun file del repo avvia BRK, che sul Dell è distribuito fuori dal repo.

## Cosa NON verifica (fuori scopo dichiarato)

Il gate non interpreta la sintassi di systemd né di Compose, quindi non vede: escape C nel comando, drop-in e reset di `ReadOnlyPaths`, `ReadWritePaths`, caricamenti `docker compose -f` con altri file, merge di override, file di avvio con estensioni diverse da unit systemd e `.yml`/`.yaml`. Un gate statico su quella sintassi non può essere completo. La verifica sulla configurazione effettiva (`docker compose config`, `systemctl show`, `docker inspect`) è il controllo runtime post-deploy tracciato in #16, obbligatorio prima della migrazione sul Dell.
