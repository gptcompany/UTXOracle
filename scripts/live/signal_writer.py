from datetime import datetime, timezone
import json
import logging
from typing import Dict, Any

from api.questdb_repository import QuestDBRepository

logger = logging.getLogger(__name__)

BIAS_THRESHOLD = 0.5
FLOW_SCALE_BTC = 5000.0
RESERVE_RISK_CENTER = 0.003
RESERVE_RISK_SCALE = 100.0
VALUATION_CENTER = 1.0

class SignalSnapshotWriter:
    def __init__(self, repo: QuestDBRepository):
        self.repo = repo

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _first_numeric(self, source: Dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = self._as_float(source.get(key))
            if value is not None:
                return value
        return None

    def calculate_regime_score(self, nupl: float | None, reserve_risk: float | None) -> float:
        # NUPL scale maps roughly to regime. 
        # Typically NUPL is between -0.5 and 1.0. We clamp to [-1, 1]
        score = 0.0
        inputs = 0
        if nupl is not None:
            score += max(-1.0, min(1.0, nupl * 1.5))
            inputs += 1
        
        if reserve_risk is not None:
            # high reserve risk = high price vs hodl = bearish regime (maybe)
            # normalize RR: e.g. 0.001 to 0.01 is common, so we just use an arbitrary safe mapping for now to satisfy [-1, 1] bounds
            rr_mapped = max(-1.0, min(1.0, (reserve_risk - RESERVE_RISK_CENTER) * RESERVE_RISK_SCALE))
            score -= rr_mapped # Inverse mapping
            inputs += 1

        if inputs == 0:
            return 0.0
        return score / inputs

    def calculate_flow_score(self, flow: Dict[str, Any]) -> float:
        net_flow_btc = self._as_float(flow.get("net_flow_btc"))
        if net_flow_btc is None:
            net_flow_btc = 0.0
        absorption = self._as_float(flow.get("absorption_rate_24h"))
        if absorption is None:
            absorption = 1.0
        
        # normalize to [-1, 1]
        flow_mapped = max(-1.0, min(1.0, net_flow_btc / FLOW_SCALE_BTC))
        abs_mapped = max(-1.0, min(1.0, (absorption - 1.0)))
        
        return (flow_mapped + abs_mapped) / 2.0

    def extract_flow_inputs(self, flow_bundle: Dict[str, Any]) -> Dict[str, Any]:
        whale_summary = flow_bundle.get("whale_summary", {}) or {}
        recent_window = flow_bundle.get("recent_whale_window", {}) or {}
        absorption_rates = flow_bundle.get("absorption_rates", {}) or {}

        net_flow_btc = self._first_numeric(
            recent_window,
            "net_flow_btc",
            "whale_net_flow_btc",
            "net_btc_flow",
            "net_flow",
        )
        if net_flow_btc is None:
            inflow_btc = self._first_numeric(
                recent_window,
                "inflow_btc",
                "total_inflow_btc",
                "whale_inflow_btc",
            )
            outflow_btc = self._first_numeric(
                recent_window,
                "outflow_btc",
                "total_outflow_btc",
                "whale_outflow_btc",
            )
            if inflow_btc is not None and outflow_btc is not None:
                net_flow_btc = inflow_btc - outflow_btc
        if net_flow_btc is None:
            net_flow_btc = self._first_numeric(whale_summary, "net_flow_btc")

        absorption_context = self._first_numeric(
            recent_window,
            "absorption_rate_24h",
            "absorption_rate",
            "absorption_context",
        )
        if absorption_context is None:
            absorption_context = self._first_numeric(
                absorption_rates,
                "absorption_rate_24h",
                "absorption_rate",
                "absorption_context",
            )
        if absorption_context is None:
            institutional_absorption = self._first_numeric(
                absorption_rates,
                "institutional_absorption",
            )
            retail_absorption = self._first_numeric(absorption_rates, "retail_absorption")
            if institutional_absorption is not None and retail_absorption is not None:
                absorption_context = 1.0 + institutional_absorption - retail_absorption

        return {
            "net_flow_btc": net_flow_btc if net_flow_btc is not None else 0.0,
            "absorption_rate_24h": absorption_context if absorption_context is not None else 1.0,
            "absorption_context": absorption_context if absorption_context is not None else 1.0,
            "dominant_absorber": absorption_rates.get("dominant_absorber"),
            "absorption_confidence": absorption_rates.get("confidence"),
        }

    def calculate_valuation_score(self, mvrv: float | None) -> float:
        if mvrv is None:
            return 0.0
        # MVRV typical range: 0.5 to 4.0. 1.0 is fair value.
        # Below 1 = undervalued (bullish, positive score)
        # Above 2 = overvalued (bearish, negative score)
        val = VALUATION_CENTER - mvrv
        return max(-1.0, min(1.0, val))

    def extract_valuation_inputs(self, cohort_bundle: Dict[str, Any]) -> Dict[str, Any]:
        cost_basis = cohort_bundle.get("cost_basis", {}) or {}
        sth_mvrv = self._first_numeric(cost_basis, "sth_mvrv")
        lth_mvrv = self._first_numeric(cost_basis, "lth_mvrv")
        mvrv = self._first_numeric(cost_basis, "mvrv", "total_mvrv")
        if mvrv is None:
            mvrv_values = [value for value in (sth_mvrv, lth_mvrv) if value is not None]
            if mvrv_values:
                mvrv = sum(mvrv_values) / len(mvrv_values)

        return {
            "mvrv": mvrv,
            "mvrv_used": mvrv,
            "sth_mvrv": sth_mvrv,
            "lth_mvrv": lth_mvrv,
            "sth_cost_basis": cost_basis.get("sth_cost_basis"),
            "lth_cost_basis": cost_basis.get("lth_cost_basis"),
            "total_cost_basis": cost_basis.get("total_cost_basis"),
            "current_price_usd": cost_basis.get("current_price_usd"),
        }

    def evaluate_bias(self, regime: float, flow: float, valuation: float) -> str:
        total = regime + flow + valuation
        if total > BIAS_THRESHOLD:
            return "bullish"
        elif total < -BIAS_THRESHOLD:
            return "bearish"
        return "neutral"

    @staticmethod
    def _derive_service_status(bundle_statuses: list[str]) -> str:
        non_empty_statuses = [status for status in bundle_statuses if status]
        if not non_empty_statuses:
            return "empty"
        if all(status == "empty" for status in non_empty_statuses):
            return "empty"
        if any(status == "misconfigured" for status in non_empty_statuses):
            return "misconfigured"
        if any(status == "stale" for status in non_empty_statuses):
            return "stale"
        if any(status == "degraded" for status in non_empty_statuses):
            return "degraded"
        if any(status == "empty" for status in non_empty_statuses):
            return "degraded"
        return "healthy"

    async def write_signal_snapshot(self) -> None:
        try:
            core_row = await self.repo.get_latest_feature_bundle("btc_core_live.v1")
            flow_row = await self.repo.get_latest_feature_bundle("btc_flow.v1")
            macro_row = await self.repo.get_latest_feature_bundle("btc_macro.v1")
            cohort_row = await self.repo.get_latest_feature_bundle("btc_cohort.v1")

            core = json.loads(core_row["payload_json"]) if core_row else {}
            flow = json.loads(flow_row["payload_json"]) if flow_row else {}
            macro = json.loads(macro_row["payload_json"]) if macro_row else {}
            cohort = json.loads(cohort_row["payload_json"]) if cohort_row else {}

            core_meta = core.get("metadata", {})
            flow_meta = flow.get("metadata", {})
            macro_meta = macro.get("metadata", {})
            cohort_meta = cohort.get("metadata", {})

            # Count valid/non-degraded inputs
            expected_inputs = 4
            valid_inputs = 0
            degraded_reasons = []
            bundle_statuses = []

            for meta in [core_meta, flow_meta, macro_meta, cohort_meta]:
                bundle_status = meta.get("bundle_status")
                if bundle_status:
                    bundle_statuses.append(bundle_status)
                if bundle_status == "healthy":
                    valid_inputs += 1
                elif bundle_status:
                    degraded_reasons.append(f"{meta.get('bundle_id')} is {bundle_status}")

            service_status = self._derive_service_status(bundle_statuses)

            quality_score = valid_inputs / expected_inputs if expected_inputs > 0 else 0.0

            # Calculate scores
            macro_metrics = macro.get("macro_metrics", {})
            regime = self.calculate_regime_score(
                macro_metrics.get("nupl"), 
                macro_metrics.get("reserve_risk")
            )

            flow_metrics = self.extract_flow_inputs(flow)
            flow_score = self.calculate_flow_score(flow_metrics)

            valuation_inputs = self.extract_valuation_inputs(cohort)
            valuation = self.calculate_valuation_score(valuation_inputs.get("mvrv"))

            bias = self.evaluate_bias(regime, flow_score, valuation)
            
            participating_scores = []
            if macro_meta.get("bundle_status") == "healthy":
                participating_scores.append(regime)
            if flow_meta.get("bundle_status") == "healthy":
                participating_scores.append(flow_score)
            if cohort_meta.get("bundle_status") == "healthy":
                participating_scores.append(valuation)

            if not participating_scores:
                conviction = 0.0
            else:
                signs = [1 if s > 0 else -1 if s < 0 else 0 for s in participating_scores]
                pos = signs.count(1)
                neg = signs.count(-1)
                conviction = max(pos, neg) / len(participating_scores)

            produced_at = datetime.now(timezone.utc)
            
            # The sequence_id should be monotonic for signals. We can fetch the latest sequence_id and increment.
            # But the prompt said we could just use a timestamp-based or query the db.
            # Let's query latest sequence_id
            latest_signal = await self.repo.get_latest_signal_snapshot()
            seq_id = 1
            if latest_signal:
                seq_id = latest_signal.get("sequence_id", 0) + 1

            payload = {
                "schema_version": "v1",
                "sequence_id": seq_id,
                "produced_at": produced_at.isoformat(),
                "block_height": core.get("live_snapshot", {}).get("block_height", 0),
                "service_status": service_status,
                "bias": bias,
                "conviction": conviction,
                "regime_score": regime,
                "flow_score": flow_score,
                "valuation_score": valuation,
                "quality_score": quality_score,
                "degraded_reasons": degraded_reasons,
                "input_refs": {
                    "core_sequence_id": core_meta.get("sequence_id"),
                    "flow_sequence_id": flow_meta.get("sequence_id"),
                    "macro_sequence_id": macro_meta.get("sequence_id"),
                    "cohort_sequence_id": cohort_meta.get("sequence_id"),
                },
                "component_details": {
                    "constants": {
                        "bias_threshold": BIAS_THRESHOLD,
                        "flow_scale_btc": FLOW_SCALE_BTC,
                        "reserve_risk_center": RESERVE_RISK_CENTER,
                        "reserve_risk_scale": RESERVE_RISK_SCALE,
                        "valuation_center": VALUATION_CENTER,
                    },
                    "regime_components": {"nupl": macro_metrics.get("nupl"), "reserve_risk": macro_metrics.get("reserve_risk")},
                    "flow_components": flow_metrics,
                    "valuation_components": valuation_inputs
                }
            }

            symbols = {
                "schema_version": "v1",
                "service_status": service_status,
            }
            columns = {
                "sequence_id": seq_id,
                "produced_at": produced_at,
                "payload_json": json.dumps(payload),
                "ts": produced_at,
            }
            
            await self.repo.async_send_row("btc_signal_snapshots", symbols, columns, produced_at)
            await self.repo.async_flush_ingestion()

            logger.info(f"Signal snapshot written: seq={seq_id} status={service_status}")
        except Exception as e:
            logger.error(f"Failed to write signal snapshot: {e}")
