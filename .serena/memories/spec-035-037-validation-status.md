# Stato Validazione Metriche (2025-12-28)

## Backfill in Corso
- **PID**: Controlla con `pgrep -f historical_spent_backfill`
- **Log**: `tail -f backfill.log`
- **Checkpoint**: `cat data/backfill_checkpoint.json`
- **ETA**: ~3-4 ore da inizio (rate ~65-1000 blk/s variabile)

## Quando Finisce il Backfill
```bash
# 1. Verifica completamento
cat data/backfill_checkpoint.json  # last_block dovrebbe essere ~927966

# 2. Ricalcola metriche daily con nuova formula liveliness
uv run python -m scripts.metrics.calculate_daily_metrics --recalculate

# 3. Ri-valida contro RBN
uv run python -m scripts.integrations.validation_batch --days 30
```

## Stato Metriche vs RBN (ultimo run)

| Metrica | Status | MAPE | Note |
|---------|--------|------|------|
| SOPR | ✅ PASS | 0% | Perfetto |
| Power Law | ✅ PASS | 0% | Perfetto |
| NUPL | ⚠️ WARN | 5.4% | Accettabile |
| Realized Cap | ⚠️ WARN | 5.4% | Accettabile |
| MVRV-Z | ❌ FAIL | 75% | Formula diversa da RBN |
| Liveliness | ❌ FAIL | 100% | Risolto dopo backfill |

## Fix Applicati (commits su branch 037-database-consolidation)
1. `1c63f68` - Fix formula liveliness (coinblocks invece di count)
2. `526a1ac` - Script backfill storico
3. `751582a` - Fix colonna age_blocks mancante

## Spec-035 Task Rimanente
- [ ] T034: Validate quickstart.md end-to-end (quasi completo, aspetta backfill)

## Comandi Utili
```bash
# Stato backfill
cat data/backfill_checkpoint.json

# Resume backfill se interrotto
nohup uv run python -m scripts.bootstrap.historical_spent_backfill --resume > backfill.log 2>&1 &

# Validazione rapida
uv run python -m scripts.integrations.validation_batch --days 7

# Check Bitcoin Core
bitcoin-cli -datadir=/media/sam/3TB-WDC/Bitcoin getblockchaininfo
```

## Valori di Riferimento (Dic 2025)
- NUPL: ~0.55 (55%)
- MVRV-Z: ~2.0-2.5
- BTC Price: ~$105,000
