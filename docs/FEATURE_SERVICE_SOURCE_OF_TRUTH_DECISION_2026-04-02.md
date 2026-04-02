# Feature Service Source-of-Truth Decision

Date: 2026-04-02

Status: Active engineering policy freeze for overlapping metrics

Primary policy documents:

- [docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md](/media/sam/1TB/UTXOracle/docs/METRIC_SOURCE_OF_TRUTH_MANIFEST.md)
- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)

## 1. Decision

For overlapping macro analytics, `UTXOracle` should not re-implement by default what the local `BRK` service already computes and exposes.

Engineering rule:

- if `BRK` already computes and exposes a metric with acceptable semantics, treat `BRK` as the preferred upstream source
- only build or keep a repo-local implementation when:
  - the metric is not exposed by `BRK`
  - the metric is repo-specific
  - the local methodology is intentionally different and documented
  - the local implementation is needed for validation or research only

## 2. Why This Exists

The repo had drifted into an ambiguous hybrid state:

- architecture docs already described `BRK` as the broad on-chain feature engine
- the runtime still used a narrow curated subset from `BRK`
- some roadmap slices still treated overlapping local metric productization as the default next step

That combination creates duplication risk and wasted work.

## 3. Current Decisions

| Metric | Source-of-truth decision | Practical implication |
|------|------|------|
| `utxoracle_price` | `UTXOracle` canonical | never replace with `BRK` |
| `realized_price_usd` | `BRK` first | use upstream rather than opening a new local productization track |
| `liveliness` | `BRK` first for shared feature use | local cointime remains valid for research and validation |
| `reserve_risk` | `BRK` first | do not continue local route productization by default |
| `nupl` | undecided beyond research | future promotion must explicitly choose `BRK` adoption or a reduced local contract |
| `cost_basis` | local `UTXOracle` | repo-native DuckDB implementation remains the preferred path |

## 4. Immediate Operational Consequence

The uncommitted local hardening/productization work on `/api/metrics/reserve-risk` was intentionally discarded.

Reason:

- it was duplicating an overlapping macro metric that `BRK` already computes for this stack
- there was no written decision yet justifying a separate local admitted path

## 5. What This Does Not Mean

- it does not mean DuckDB is obsolete
- it does not mean every local metric should move to `BRK`
- it does not mean repo-local research implementations should be deleted

DuckDB still owns repo-specific and UTXO-lifecycle-centric surfaces such as:

- `cost-basis`
- Wave 1 holder/cohort analytics
- custom research workflows
- any route where `BRK` does not provide a suitable exposed equivalent

## 6. Next Local Engineering Priority

The next substantive local milestone should be Wave 1 history/materialization debt, not more overlapping macro duplication.

`reserve-risk` should only be reopened if one of these happens:

1. `BRK` adoption is blocked operationally or contractually
2. a deliberately different local reserve-risk methodology is approved
3. the repo wants a research-only validation implementation and explicitly keeps it out of the downstream contract

## 7. Required Discipline Going Forward

Before productizing any overlapping metric family:

1. check whether `BRK` already computes and exposes it
2. decide `adopt`, `validate`, or `local-only`
3. write that decision into the metric source-of-truth manifest
4. only then open implementation work
