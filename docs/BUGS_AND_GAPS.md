# Bugs & Gaps — Full Static Audit Report

**Last Updated:** 28 Jun 2026  
**Scope:** Full static audit of AIKosh Dataset Quality Evaluation Toolkit — frontend, backend, DB, Docker, k8s, configs, 5 design docs  
**Audit Method:** Cross-reference PRD v1.1, TDD v1.1, OpenAPI v1.1, Questionnaire v1.1, Security Audit Checklist v1.0 against every code file

---

## Severity Key

| Label | Meaning |
|---|---|
| **P0** | Blocks startup — must fix before `docker-compose up` works |
| **P1** | Breaks core contract — will fail in E2E or production |
| **P2** | Architectural drift / security hardening gap |
| **P3** | Nice-to-have / dev-only / doc inconsistency |

---

## P0 — Blocks Startup

### P0.1 Dead code file with import error

| | |
|---|---|
| **File** | `backend/app/engine/domains.py` (1043 lines) |
| **Line** | 17 |
| **Bug** | `from app.engine.scoring import BaseDomainScorer, DomainScoreResult` — `app/engine/scoring/__init__.py` is **empty** and does NOT export these classes |
| **Where classes actually live** | `app/engine/domains/base.py` |
| **Why it doesn't crash today** | `tasks.py` imports `DOMAIN_SCORERS` from `app.engine.domains` which resolves to the **package** (`domains/__init__.py`), not this file. This file is dead code — Python prioritizes the package directory over the `.py` file when both exist |
| **Risk** | If someone renames the `domains/` package directory, or the Python import order changes, this file gets loaded instead — causing `ImportError` at runtime and breaking the entire assessment pipeline |
| **Fix** | Delete `backend/app/engine/domains.py` entirely. All 15 scorers are duplicated in individual files under `domains/` which is the live code path |

### P0.2 Empty `scoring/` package

| | |
|---|---|
| **File** | `backend/app/engine/scoring/__init__.py` |
| **Bug** | Empty file. Nobody imports from it, so no crash — but the directory exists and is misleading. The classes `BaseDomainScorer` and `DomainScoreResult` that the dead file P0.1 tries to import from here actually live in `domains/base.py` |
| **Fix** | Either delete the entire `scoring/` directory or add re-exports (`from app.engine.domains.base import BaseDomainScorer`) if planned for future use |

---

## P1 — Breaks Core Contract

### P1.1 Missing API endpoint: `GET /api/v1/assess/{assessment_id}/audit`

| | |
|---|---|
| **Doc** | OpenAPI §7.14 specifies returning full audit log array (requires `reviewer` role) |
| **Code** | No endpoint exists in `backend/app/api/v1/assess.py` or anywhere else |
| **Impact** | Reviewers cannot read audit logs via API even though events are written to the database |
| **Fix** | Add route calling `get_current_active_reviewer` dep, query `AuditLog` where `assessment_id == id`, return as array |

### P1.2 Missing API endpoint: `GET /api/v1/datasets/{dataset_id}/assessments`

| | |
|---|---|
| **Doc** | OpenAPI §7.13 + TDD specify a `datasets.py` router for querying assessment history by AIKosh dataset ID |
| **Code** | File `backend/app/api/v1/datasets.py` does not exist |
| **Impact** | AIKosh platform integration cannot query assessment history for a given dataset |
| **Fix** | Create `datasets.py` with `GET /api/v1/datasets/{dataset_id}/assessments` returning paginated list |

### P1.3 Webhook payload `domain_scores` shape wrong

| | |
|---|---|
| **Doc** | OpenAPI §8 shows `domain_scores` as an object with **named keys** and **structured values**: `{"1_annotation_labelling_reliability": {"score": 3, "confidence": "Medium"}, ...}` |
| **Code** (`tasks.py:369`) | `"domain_scores": {str(ds.domain_number): ds.score for ds in domain_scores_list}` — produces `{"1": 3, "2": 2, ...}` — flat int dict, no names, no confidence |
| **Impact** | AIKosh integration contract is broken — AIKosh expects structured objects with metadata and gets bare numbers |
| **Fix** | Change to: `{f"{ds.domain_number}_{ds.domain_name_slug}": {"score": ds.score, "confidence": ds.confidence_level, "not_applicable": ds.not_applicable}}` |

### P1.4 Missing `inferred` field on `DomainScoreObject`

| | |
|---|---|
| **Doc** | OpenAPI §7.9: `DomainScoreObject` includes `inferred: boolean` indicating whether the score was inferred from data vs confirmed by user |
| **Code** (`backend/app/schemas/assessment.py:46`) | `DomainScoreObject` Pydantic model does not have an `inferred` field |
| **Impact** | Consumers cannot distinguish inferred vs confirmed scores; OpenAPI contract is broken |
| **Fix** | Add `inferred: bool = False` to `DomainScoreObject` |

### P1.5 No general API rate limiting

| | |
|---|---|
| **Doc** | OpenAPI §5 specifies `100 req/min, 10 concurrent` general rate limit; Security checklist §2 item 21 |
| **Code** | Only auth endpoints have rate limiting (5/min per IP in `auth.py:35-51`). No middleware or dependency for general API |
| **Impact** | All non-auth endpoints (assess, datasets, reports, admin) are unprotected against brute force / DoS |
| **Fix** | Add FastAPI middleware or dependency checking Redis sliding-window counter per API key or IP |

### P1.6 No `X-Request-ID` middleware

| | |
|---|---|
| **Doc** | OpenAPI §4: every response must include `X-Request-ID` header for request tracing |
| **Code** | Not implemented anywhere |
| **Impact** | No way to correlate frontend error reports with backend logs |
| **Fix** | Add Starlette middleware generating UUID per request, set header on response, log with each event |

### P1.7 `secure=False` hardcoded in session cookie

| | |
|---|---|
| **File** | `backend/app/api/v1/auth.py:64` |
| **Doc** | Security checklist §3.2.2 |
| **Code** | `response.set_cookie(..., secure=False, ...)` — cookie transmitted over HTTP even in production |
| **Impact** | Session token can be intercepted on production HTTPS if this isn't changed to `True` |
| **Fix** | Change to `secure=(settings.ENVIRONMENT == "production")` |

### P1.8 No SSRF protection on webhook URL

| | |
|---|---|
| **File** | `backend/app/integration/aikosh_webhook.py` |
| **Doc** | Security checklist §3.4.10, §1.10 item 162 |
| **Code** | `webhook_url` from user-supplied `MetadataForm` is called with `httpx.Client().post(webhook_url, json=payload)` — no IP validation |
| **Impact** | Attacker supplies `webhook_url=http://169.254.169.254/latest/meta-data/` (AWS metadata) or `http://redis:6379` to probe internal services |
| **Fix** | Before HTTP call, resolve hostname and reject RFC-1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), link-local (169.254.0.0/16) using `ipaddress.ip_address()` |

### P1.9 `.env.example` references Vite instead of Next.js

| | |
|---|---|
| **File** | `.env.example:37` |
| **Code** | `VITE_API_URL=http://localhost:8000/api/v1` — frontend was migrated from Vite to Next.js |
| **Frontend uses** | `NEXT_PUBLIC_API_URL` (see `frontend/lib/api/client.ts:1`) |
| **Impact** | Anyone copying `.env.example` to `.env` will have frontend silently communicating with wrong endpoint |
| **Fix** | Change to `NEXT_PUBLIC_API_URL=http://localhost:8000` (note: no `/api/v1` suffix; `client.ts` appends it) |

### P1.10 Report redirect hardcodes MinIO URL instead of presigned URL

| | |
|---|---|
| **File** | `backend/app/api/v1/reports.py:25` |
| **Code** | `url=f"http://localhost:9000/aikosh-datasets/reports/{...}/report.{format}"` — direct MinIO URL, no auth |
| **Impact** | In production, this redirects to MinIO's HTTP API without any credential. Anyone who sees the redirect target can download any report. Also hardcodes `localhost:9000` which won't work in production |
| **Fix** | Use `s3_client.generate_presigned_url(f"reports/{assessment.assessment_id}/report.{format}")` |

### P1.11 `MetadataForm` missing `extra='forbid'` — mass assignment

**FIXED** — `model_config = ConfigDict(extra='forbid')` was already present in the code at time of audit. P1.11 is a false positive.

### P1.13 `MetadataForm` fields not matching Questionnaire required status

| | |
|---|---|
| **File** | `backend/app/schemas/metadata_form.py` |
| **Doc** | Questionnaire marks `license_type` (Q5), `standards_used` (Q18), `deidentification_method` (Q23), `consent_type` (Q29), `access_control_method` (Q33) as required |
| **Code** | All five were `Optional[str] = None` (consent_type was `Optional[Literal] = "not_applicable"`) |
| **Impact** | Forms could be submitted without these critical fields, causing downstream scorers to receive `None` for fields they expect to have values |
| **Fix** | Removed `Optional` from all five. `consent_type` keeps its default `"not_applicable"`. The other four are now truly required (no default). |
| **Tests** | `tests/questionnaire/test_metadata_form.py::TestRequiredFields` |

### P1.14 `MetadataForm` missing cross-field validators

| | |
|---|---|
| **File** | `backend/app/schemas/metadata_form.py` |
| **Doc** | Questionnaire Q10: age_range_min ≤ age_range_max. Questionnaire Q12: neither date can be in the future. |
| **Code** | No validators existed for these constraints |
| **Impact** | Invalid data pairs (e.g. min_age > max_age, future collection dates) would be accepted by the API and stored in DB |
| **Fix** | Added `validate_age_range` and `validate_future_dates` model validators |
| **Tests** | `tests/questionnaire/test_metadata_form.py::TestCrossFieldValidators` |

### P1.12 Celery `webhook` queue not routed in code

| | |
|---|---|
| **Doc** | OpenAPI §5.3 specifies separate `webhook` queue; docker-compose launches `worker_webhook` with `-Q webhook` (line 127) |
| **Code** (`celery_app.py`) | No `task_routes` configured — `send_webhook` task has no explicit queue routing |
| **Impact** | Webhook tasks will be routed to the `celery` default queue, not the `webhook` queue. The `worker_webhook` container sits idle, and the `worker_assessment` container might process webhook tasks |
| **Fix** | Add `celery_app.conf.task_routes = {"app.worker.tasks.send_webhook": {"queue": "webhook"}}` |

---

## P2 — Architectural Drift & Security Hardening

### P2.1 k8s Redis no password set

| | |
|---|---|
| **Doc** | TDD §22.1 |
| **Docker-compose** | Redis runs with `--requirepass ${REDIS_PASSWORD:-redispassword123}` |
| **k8s** (`redis-deployment.yaml`) | No `--requirepass` flag; clients connect without auth. k8s worker configs also omit password in `REDIS_URL` |
| **Impact** | In k8s, any pod on the cluster can connect to Redis, read Celery task messages, reset rate-limit counters, inject fake tasks |
| **Fix** | Add `--requirepass $(REDIS_PASSWORD)` to Redis container command in k8s; mount password from K8s Secret; update k8s worker `REDIS_URL` to include password |

### P2.2 No MinIO deployment in k8s

| | |
|---|---|
| **Doc** | TDD/Stack shows S3-compatible storage in all environments |
| **k8s** | No MinIO deployment exists, but `api-deployment.yaml` and `worker-deployment.yaml` both set `S3_ENDPOINT_URL=http://minio:9000` |
| **Impact** | In k8s, the hostname `minio` won't resolve — all S3 storage calls fail |
| **Fix** | Either add MinIO StatefulSet to k8s or change `S3_ENDPOINT_URL` to point to external S3-compatible service |

### P2.3 No Flower deployment in k8s

| | |
|---|---|
| **Doc** | TDD mentions Flower for Celery monitoring |
| **Docker-compose** | Flower service on port 5555 |
| **k8s** | No Flower manifest |
| **Impact** | No Celery task monitoring in production/k8s |
| **Fix** | Add Flower deployment + service (with `--basic_auth` for security) |

### P2.4 Redis `emptyDir` in k8s (no persistence)

| | |
|---|---|
| **File** | `k8s/redis-deployment.yaml` |
| **k8s** | `volumes: [{name: redis-data, emptyDir: {}}]` |
| **Impact** | All Redis data (Celery results, rate-limit counters, task state) lost on pod restart |
| **Fix** | Add `PersistentVolumeClaim` + reference as `persistentVolumeClaim` volume |

### P2.5 Hardcoded secrets in all YAMLs

| | |
|---|---|
| **Files** | `docker-compose.yml`, `k8s/api-deployment.yaml`, `k8s/worker-deployment.yaml`, `k8s/redis-deployment.yaml` |
| **Pattern** | Secrets like `JWT_SECRET`, `API_KEY_SECRET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` hardcoded as `value:` strings — not `valueFrom.secretKeyRef` |
| **Doc** | Security checklist §3.6.2 |
| **Impact** | Secrets committed to git; cannot rotate without code change; no environment segregation |
| **Fix** | Create K8s Secrets (`kubectl create secret generic toolkit-secrets ...`) and reference via `valueFrom.secretKeyRef` in all yamls |

### P2.6 `ingress.yaml` contains 3 unrelated resources

| | |
|---|---|
| **File** | `k8s/ingress.yaml` |
| **Issue** | Single file contains: Frontend Deployment, Frontend Service, AND Ingress — misnamed and violates one-file-per-resource convention |
| **Fix** | Split into `k8s/frontend-deployment.yaml`, `k8s/frontend-service.yaml`, `k8s/ingress.yaml` |

### P2.7 Questionnaire gate booleans missing from `MetadataForm`

| | |
|---|---|
| **Doc** | Questionnaire shows gate questions: Q13 (has annotated data), Q37 (has synthetic data), Q35 (has named steward), Q28 (has ethics approval), Q40 (has linked models) |
| **Frontend code** (`upload/page.tsx:108-113`) | Gates tracked in local state only — `hasAnnotatedData`, `hasSyntheticData`, etc. — not sent to API |
| **Backend code** (`metadata_form.py`) | No boolean fields for these gates |
| **Impact** | API cannot distinguish "user skipped section because gate is off" from "user left fields empty". Scoring logic cannot tell if annotation section was intentionally skipped |
| **Fix** | Add boolean fields (e.g. `has_annotated_data: bool = False`, `has_synthetic_data: bool = False`) to `MetadataForm` and submit them from frontend |

### P2.8 `study_type` enum missing options from Questionnaire

| | |
|---|---|
| **Doc** | Questionnaire Q6: "Options include: [...] Disease registry, Epidemiological surveillance, Biobank / specimen collection" |
| **Code** (`metadata_form.py:9`) | `Literal["RCT", "cohort", "cross_sectional", "registry", "observational", "case_control", "other"]` |
| **Missing** | `"epidemiological_surveillance"`, `"biobank"` |
| **Fix** | Add missing options |

### P2.9 `license_type` should be enum, not free-text

| | |
|---|---|
| **Doc** | Questionnaire Q5: 8 specific options (CC BY 4.0, CC BY-NC 4.0, etc.) + conditional free-text for "Proprietary / Custom license" |
| **Code** (`metadata_form.py:45`) | `license_type: Optional[str]` — accepts any string with no validation |
| **Fix** | Change to `Literal["CC_BY_4", "CC_BY_NC_4", "CC_BY_NC_ND_4", "CC_BY_SA_4", "GODL_INDIA", "RESTRICTED_DUA", "PROPRIETARY", "NOT_DECIDED"]` matching Questionnaire |

### P2.10 No rate limiting on registration (enumeration vector)

| | |
|---|---|
| **Doc** | Security checklist §3.1.7 |
| **Code** | `auth.py:88` applies rate limiter to login, `auth.py:138` applies to login (different path) — but registration endpoint has no rate limiter |
| **Impact** | Bot can spam registrations; timing side-channel for email enumeration |
| **Fix** | Apply `enforce_auth_rate_limit` to register endpoint; return constant-time response for existing vs new email |

### P2.11 No `HPA` for API deployment in k8s

| | |
|---|---|
| **Doc** | Security checklist §1.8 item 138 |
| **k8s** | Only `worker-assessment` has HPA. `api` deployment runs fixed 1 replica in k8s yaml |
| **Impact** | API cannot auto-scale under load |
| **Fix** | Add HPA for `api` deployment on CPU >= 70%, minReplicas: 2, maxReplicas: 10 |

### P2.12 No `NetworkPolicy` in k8s

| | |
|---|---|
| **Doc** | Security checklist §1.8 item 136 |
| **k8s** | No `NetworkPolicy` resources exist. Any pod can reach any other pod |
| **Impact** | Compromised API pod can reach DB, Redis, MinIO directly |
| **Fix** | Create `k8s/network-policies.yaml` with least-privilege rules |

---

## P3 — Hardening & Dev-Only Gaps

### P3.1 No MinIO bucket versioning

| | |
|---|---|
| **Doc** | Security checklist §1.5 item 103 |
| **Impact** | Report files in `reports/` prefix can be overwritten without recovery |
| **Fix** | Enable versioning on `aikosh-datasets` bucket |

### P3.2 No non-root user in Dockerfiles

| | |
|---|---|
| **Doc** | Security checklist §3.6.3 |
| **Code** | Both `backend/Dockerfile` and `frontend/Dockerfile` have no `USER` directive — containers run as root |
| **Impact** | Container escape = host compromise |
| **Fix** | Add `RUN addgroup --gid 1000 appgroup && adduser --uid 1000 --gid 1000 --disabled-password appuser && chown -R appuser:appgroup /app` + `USER appuser` |

### P3.3 No `docker-compose.prod.yml`

| | |
|---|---|
| **Doc** | TDD references "production Docker composition" |
| **Code** | Does not exist |
| **Fix** | Create for production-specific settings (no port exposure to host, read-only volumes, resource limits) |

### P3.4 No CI/CD (`.github/` directory missing)

| | |
|---|---|
| **Doc** | Security checklist §4 references GitHub Actions for SAST (bandit), DAST (ZAP), SCA (pip-audit, npm audit, Trivy), secret scanning (TruffleHog) |
| **Code** | `.github/` directory does not exist |
| **Impact** | No automated testing, no security scanning, no linting on push — every deploy is manual |

### P3.5 No frontend tests

| | |
|---|---|
| **Doc** | Playwright installed per `package.json` |
| **Code** | Zero test files in frontend directory |
| **Impact** | No regression protection for UI changes |

### P3.6 Single DB user for all services

| | |
|---|---|
| **Doc** | Security checklist §1.4 item 89 recommends separate `toolkit_api` (SELECT/INSERT on assessment tables) and `toolkit_worker` (INSERT on results) roles |
| **Code** | API and Worker share same DB connection string with full read/write access to all tables |
| **Fix** | Create separate DB roles with least privilege |

### P3.7 No audit log `TRUNCATE` protection

| | |
|---|---|
| **Doc** | Security checklist §1.4 item 86, §2 item 23 |
| **Code** | Migration `27bf1154c14b` has `CREATE RULE no_delete_audit` but not `TRUNCATE` protection |
| **Impact** | Attacker with DB access can `TRUNCATE audit_logs` which the DELETE rule does not block |
| **Fix** | Add `CREATE RULE no_truncate_audit AS ON TRUNCATE TO audit_logs DO INSTEAD NOTHING` |

### P3.8 Missing security tests (14+ files)

All tests referenced in Security checklist §2 do not exist:

| Test file | Purpose |
|---|---|
| `backend/tests/test_cors.py` | CORS restrictive origins |
| `backend/tests/test_cookie_security.py` | Cookie flags (HttpOnly, Secure, SameSite, Path) |
| `backend/tests/test_file_upload_security.py` | Magic bytes, size limit, path traversal, ZIP bomb |
| `backend/tests/test_sql_injection.py` | Parameterized queries |
| `backend/tests/test_concurrency.py` | Race conditions in parallel submissions |
| `backend/tests/test_rate_limiting.py` | 429 on excess requests |
| `backend/tests/test_csrf.py` | Cross-origin POST rejection |
| `backend/tests/test_audit_append_only.py` | DELETE/TRUNCATE on audit_logs |
| `backend/tests/test_s3_security.py` | Expired presigned URL returns 403 |
| `backend/tests/test_auth_bypass.py` | No cookie/bearer returns 401 |
| `backend/tests/test_webhook_retry.py` | Retry on 5xx |
| `backend/tests/test_health_endpoint.py` | No info leak |

---

## P4 — Doc-Internal Inconsistencies (no code fix)

| # | Issue | Details |
|---|---|---|
| P4.1 | Bucket name mismatch | PRD/TDD say `aikosh-toolkit-bucket/`, docker-compose/code say `aikosh-datasets` |
| P4.2 | TDD DDL missing `submitter_id` | Migration adds it; TDD DDL doesn't list it |
| P4.3 | TDD DDL has `started_at` but migration drops it | Migration `27bf1154c14b` removes `started_at` column |
| P4.4 | OpenAPI shows `started_at` in response | Field was dropped from DB model — no longer returned |
| P4.5 | `ingress.yaml` mislabeled | File named for Ingress but contains Frontend Deployment + Service too |

---

## E2E Verification Checklist

After fixing P0 and P1 items, run through this sequence to validate everything works:

| Step | Action | How | Pass Criteria |
|---|---|---|---|
| 1 | Build all images | `docker-compose build --no-cache` | All 6 images build without error |
| 2 | Start stack | `docker-compose up -d` | All 8 containers healthy (`docker ps`) |
| 3 | Run migrations | `docker exec tkt_backend alembic upgrade head` | No errors, current head matches latest |
| 4 | Register user | `POST /api/v1/auth/register` with email + password | 201 + `session_token` cookie |
| 5 | Login | `POST /api/v1/auth/login` with same creds | 200 + `session_token` cookie |
| 6 | Generate upload URL | `POST /api/v1/assess/upload-url` | 201 with `upload_url`, `file_key`, `assessment_id` |
| 7 | Upload file | `PUT {upload_url}` with CSV/XLSX body | 200 |
| 8 | Submit assessment | `POST /api/v1/assess` with file_key + metadata | 202 + status=queued |
| 9 | Poll until complete | `GET /api/v1/assess/{id}` every 5s | Eventually returns status=complete with domain_scores |
| 10 | Download report | `GET /api/v1/assess/{id}/report?format=html` | 302 redirect to URL that returns HTML |
| 11 | Webhook sent | Check `worker_webhook` logs | POST sent; `audit_logs` has `aikosh_webhook_sent` |
| 12 | BOLA test | User A fetches User B's assessment ID | 403 |
| 13 | Admin isolation | Admin user fetches any assessment | 403 |
| 14 | Rate limit auth | Send 6 rapid `POST /auth/login` requests | 429 on 6th request |
| 15 | No auth | `GET /api/v1/assess/` without cookie or bearer | 401 |
| 16 | Invalid file | Submit with file_key that doesn't exist in S3 | 404 |

---

## Architecture Summary (for orientation)

```
Browser → Next.js (port 3000)  ──→  FastAPI (port 8000)  ──→  Celery Workers
                                    │                         ├─ assessment queue
                                    ├─ PostgreSQL (5432)      └─ webhook queue
                                    ├─ Redis (6379)
                                    └─ MinIO (9000)
                                        ├─ uploads/{assessment_id}/
                                        ├─ profiles/{assessment_id}/
                                        └─ reports/{assessment_id}/
```
