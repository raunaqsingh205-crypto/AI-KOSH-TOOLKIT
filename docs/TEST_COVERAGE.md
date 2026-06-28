# Test Coverage — AIKosh Dataset Quality Toolkit

> **Why this doc exists:** So the next agent can read one file instead of cross-referencing AGENTS.md + git diff + BUGS_AND_GAPS + every test file. Every entry links to the actual source.

---

## Overview

Three test layers plus fixed infrastructure bugs:

| Layer | Tests | Location |
|---|---|---|
| Engine (golden + unit) | 62 | [`backend/tests/engine/`](../backend/tests/engine/) |
| Questionnaire (Pydantic + HTTP + E2E) | 66 | [`backend/tests/questionnaire/`](../backend/tests/questionnaire/) |
| Fixed infra tests | 2 | [`tests/test_api_endpoints.py`](../backend/tests/test_api_endpoints.py), [`tests/test_auth_bola.py`](../backend/tests/test_auth_bola.py) |
| **Total (non-E2E)** | **127 pass** | `pytest tests/ -m "not e2e"` |
| **Total (all)** | **130 collected** | 3 E2E require `-m e2e` |

---

## Layer 1: Engine Tests — *"Run the actual profiler + scorers against a known golden CSV, and assert every metric, domain score, CQI, PRS, and release classification is exactly right."*

These are the ground truth. They establish that the pipeline produces correct output given known input, so any regression is immediately caught.

### Golden Integration Tests — [`tests/engine/golden/test_golden.py`](../backend/tests/engine/golden/test_golden.py)

32 tests that run the **real** profiler, 15 domain scorers, CQI engine, PRS engine, and release classifier against a fixed 11-row CSV slice.

| Class | Tests | What it asserts |
|---|---|---|
| `TestProfiler` (L114) | 10 | file_info, shape, PII scan, completeness, duplicates, standards_detected, split_columns, label_columns, age_distribution, schema_consistency, column_profiles_exist |
| `TestDomains` (L201) | 15 | Each domain scorer returns the expected score given golden metadata + profiler output |
| `TestCQI` (L307) | 1 | Combined Quality Index computed correctly from 15 domain scores |
| `TestPRS` (L319) | 1 | Privacy Risk Score computed correctly from profiler + metadata |
| `TestRelease` (L331) | 5 | Release classifier produces correct tier (open_access, restricted, etc.) |

### Unit Tests — [`tests/engine/test_domains.py`](../backend/tests/engine/test_domains.py) + [`tests/engine/test_cqi.py`](../backend/tests/engine/test_cqi.py) + [`tests/engine/test_prs.py`](../backend/tests/engine/test_prs.py) + [`tests/engine/test_release.py`](../backend/tests/engine/test_release.py) + [`tests/engine/test_profiler.py`](../backend/tests/engine/test_profiler.py)

30 additional unit tests exercising edge cases (all-zeros, max scores, PII detection, release policy overrides).

| File | Tests | Coverage |
|---|---|---|
| [`test_domains.py`](../backend/tests/engine/test_domains.py) | 15 | Each domain scorer with edge inputs |
| [`test_cqi.py`](../backend/tests/engine/test_cqi.py) | 4 | CQI at boundaries (max/min/mixed) |
| [`test_prs.py`](../backend/tests/engine/test_prs.py) | 4 | PRS for direct identifiers, DP, location, sensitivity |
| [`test_release.py`](../backend/tests/engine/test_release.py) | 2 | Release policy overrides + standard matrix |
| [`test_profiler.py`](../backend/tests/engine/test_profiler.py) | 2 | Completeness/shape + PII detection + standards detection |

---

## Layer 2: Questionnaire Tests — *"The metadata form schema is the contract between frontend UI and backend engine. Every field, every enum, every cross-field rule must be enforced at the Pydantic level and at the HTTP level, and the scores must match."*

Three test files covering Pydantic (unit), HTTP (contract), and E2E (pipeline wiring).

### Pydantic Unit — [`tests/questionnaire/test_metadata_form.py`](../backend/tests/questionnaire/test_metadata_form.py)

53 tests across 6 classes validating the `MetadataForm` Pydantic schema directly (no HTTP, no DB).

| Class (line) | Tests | What it validates |
|---|---|---|
| `TestRequiredFields` (L10) | 12 | Each required field rejects `None`; `consent_type` has default |
| `TestEnumValues` (L71) | 11 | Each `Literal[]` field rejects invalid strings |
| `TestFieldConstraints` (L128) | 11 | min_length, age range bounds, IRR [0–1], synthetic_data_pct [0–100], num_annotators >0, dp_epsilon >0 |
| `TestDefaultValues` (L185) | 8 | Defaults for sex_distribution, dq_checks, rare_condition, DP, equity, version, data_dictionary, consent_type |
| `TestCrossFieldValidators` (L227) | 11 | DP↔dp_epsilon, date ordering, age_range ordering, future dates, extra fields, non-string consent_type |

### HTTP Contract — [`tests/questionnaire/test_metadata_contract.py`](../backend/tests/questionnaire/test_metadata_contract.py)

10 tests exercising the **real** FastAPI `/api/v1/assess` endpoint (with mocked S3 file existence).

| Class (line) | Tests | What it asserts |
|---|---|---|
| `TestValidMetadata` (L13) | 1 | Valid metadata → 202 Accepted |
| `TestInvalidMetadata` (L22) | 8 | Bad enum → 422, short name → 422, missing field → 422, missing multiple → 422, extra fields → 422, DP epsilon missing → 422, invalid age_range → 422, future date → 422 |
| `TestAuth` (L73) | 1 | No auth cookie → 401 Unauthorized |

### E2E Metadata→Score — [`tests/questionnaire/test_metadata_to_scores.py`](../backend/tests/questionnaire/test_metadata_to_scores.py)

3 tests marked `@pytest.mark.e2e` that submit real metadata through the full Celery pipeline and verify domain scores.

| Class (line) | Assertion | What it proves |
|---|---|---|
| `TestSensitivityToPRS` (L61) | `critical` sensitivity raises PRS score vs `standard` | Sensitivity→PRS wiring works end-to-end |
| `TestDPToPrivacy` (L73) | DP applied with epsilon=1 → privacy score >= 4 | DP→Privacy Domain scorer is reachable from the pipeline |
| `TestConsentToEthics` (L88) | Individual consent → ethics score >= consent_not_obtained | Consent→Ethics Domain scorer fires correctly |

**Run with:** `pytest tests/questionnaire/test_metadata_to_scores.py -v -m e2e`

---

## Layer 3: Fixed Test Infrastructure — *"Pre-existing bugs in the test harness were preventing two integration tests from running at all. The test logic was correct — only the wiring was wrong."*

### [`test_api_endpoints.py`](../backend/tests/test_api_endpoints.py) — Full pipeline smoke test using cookie auth

**What it tests:** Registration (weak pwd → 400, duplicate → 400, valid → 201), login (bad → 401, valid → 200), `/me` before/after logout, API key CRUD, admin user list + toggle-active, upload URL generation, assessment submission with mocked S3.

**Bug:** Used `asyncio.run(run_api_endpoint_tests())` at line 214 inside a sync `def` — creates a new event loop, asyncpg connections from the global pool break. Also metadata dict was missing 4 fields newly required by the questionnaire changes.

**Fix (3 parts):**
1. Changed to `async def` + `@pytest.mark.anyio` + `await` (removed `asyncio.run()`)
2. Added `await async_engine.dispose()` at start to flush stale pool connections from previous anyio tests
3. Uses private `test_engine` (line 34) for direct DB setup/cleanup instead of global `AsyncSessionLocal`
4. Added 4 required fields (`license_type`, `standards_used`, `deidentification_method`, `access_control_method`) to metadata payload

### [`test_auth_bola.py`](../backend/tests/test_auth_bola.py) — BOLA guard + admin isolation test using Bearer API key

**What it tests:** User A fetching User B's assessment → 403, User A downloading User B's report → 403, admin viewing User B's assessment → 403, exact error message strings verified.

**Bug:** Same `asyncio.run()` + stale global engine pool issue.

**Fix:** Same 3-part fix as `test_api_endpoints.py`.

---

## Source Changes

### Schema: [`backend/app/schemas/metadata_form.py`](../backend/app/schemas/metadata_form.py)

| Change | Location | Why |
|---|---|---|
| 5 fields made required (removed `Optional`) | `standards_used` (L32), `deidentification_method` (L35), `license_type` (L48), `access_control_method` (L60), `consent_type` (L34, kept default `"not_applicable"`) | `Questionnaire.md` marks them Required; prevents silent `None` submissions |
| `validate_age_range` validator added | L86 | Rejects inverted age ranges (`max < min`) |
| `validate_future_dates` validator added | L93 | Rejects collection dates in the future |

### Worker: [`backend/app/worker/tasks.py`](../backend/app/worker/tasks.py)

| Change | Location | Why |
|---|---|---|
| `class DecimalEncoder(json.JSONEncoder)` added | L39 | `dp_epsilon` is `Numeric(10,4)` → Python `Decimal` → `json.dumps` crashed. Converts `Decimal` to `float` during JSON serialization |

### Config: [`backend/pytest.ini`](../backend/pytest.ini)

Registers the `e2e` custom pytest marker so `pytest -m "not e2e"` doesn't produce unknown-mark warnings.

### Docs: [`docs/OpenAPI.md`](../docs/OpenAPI.md) §6.1

Updated Required column and validation rules to match `metadata_form.py`.

### Bugs: [`docs/BUGS_AND_GAPS.md`](../docs/BUGS_AND_GAPS.md)

P1.11 removed (was false positive), P1.13 (5 fields required) and P1.14 (cross-field validators) added.

---

## Test Suite Command Reference

| Command | Scope |
|---|---|
| `pytest tests/ -v -m "not e2e"` | All non-E2E tests (127) |
| `pytest tests/questionnaire/ -v -m "not e2e"` | Questionnaire only (63) |
| `pytest tests/questionnaire/test_metadata_to_scores.py -v -m e2e` | E2E only (3, requires Celery + Redis + S3) |
| `pytest tests/engine/ -v` | Engine tests (62) |
| `pytest tests/test_api_endpoints.py tests/test_auth_bola.py -v` | Fixed infra tests (2) |
| `pytest tests/ -v -m "not e2e" --tb=short` | Default: full regression with short tracebacks |

---

*Generated for agent handoff. Last updated: 28 Jun 2026.*
