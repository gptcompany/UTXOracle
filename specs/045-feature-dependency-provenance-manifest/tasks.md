# Tasks: spec-045 Feature Dependency & Provenance Manifest

**Input**: design documents from `/specs/045-feature-dependency-provenance-manifest/`
**Prerequisites**: `spec.md`, `plan.md`

## Format: `[ID] [Markers] Description`

### Task Markers
- **[P]**: can run in parallel
- **[E]**: complex integration or validation task

---

## Phase 1: Schema

- [x] T001 Define backend classes and provenance field vocabulary
- [x] T002 Define failure mode vocabulary
- [x] T003 Create `docs/contracts/feature_provenance_manifest.yaml`
- [x] T004 Seed the manifest with priority route families

**Checkpoint**: one authoritative manifest structure exists.

---

## Phase 2: Priority Mapping

- [x] T005 Map `/api/prices/*` to QuestDB tables and writer owner
- [x] T006 Map `/api/whale/*` families to QuestDB and monitoring writers
- [x] T007 Map DuckDB-backed metric families to their specific tables/views
- [x] T008 Map RPC-backed and external-API-backed metric families
- [x] T009 Mark `computed_inline` routes such as `Puell Multiple`
- [x] T010 Attach required env vars and credentials for every external dependency family

**Checkpoint**: priority route families have no ambiguous dependency attribution.

---

## Phase 3: Documentation

- [x] T011 Generate `docs/FEATURE_DEPENDENCY_MATRIX.md`
- [x] T012 Align naming and route-family grouping with spec-044 contract registry
- [x] T013 Document failure semantics for empty, stale, degraded, and misconfigured states

**Checkpoint**: humans can read the same truth represented in the YAML.

---

## Phase 4: Optional Metadata Endpoint

- [x] T014 [E] Define response schema for `GET /api/meta/features`
- [x] T015 Implement metadata endpoint derived from the manifest
- [x] T016 Add tests proving manifest-backed metadata output is stable

**Checkpoint**: provenance becomes queryable without reading the repo.

---

## Phase 5: Validation

- [x] T017 Add validation checks for missing backend class, owner, or failure mode
- [x] T018 Detect route-family drift between roadmap docs and manifest
- [x] T019 Add operator guidance for updating the manifest when route behavior changes

**Checkpoint**: provenance metadata stays current as implementation evolves.
