# AGENTS.md — AI Agent Orientation Guide
# AIKosh Dataset Quality Evaluation Toolkit

> **Read this first before touching any other file.**
> This document is written for AI agents. It answers every question an agent typically needs before starting work.

---

## 1. What Is This Project?

A **user-facing, browser-first web application** for automated MIDAS-grade health dataset quality assessment — with a secure multi-tenant backend, async processing pipeline, and a REST API surface that external platforms (AIKosh) can integrate with programmatically.

Dataset custodians log in via the web UI, upload health research datasets, and receive structured quality scores across 15 MIDAS 2.0 domains. The AIKosh platform integrates programmatically via REST API and receives quality metadata via webhook on assessment completion.

**This is NOT a library, plugin, or embeddable SDK.** It is a standalone full-stack application.

---

## 2. Architecture Pattern

```
Browser User ──→ Next.js Frontend (port 3000)
                        │
                        │ HTTP + HttpOnly session cookie
                        ▼
AIKosh Platform ──────→ FastAPI API (port 8000)
                        │
              ┌─────────┼──────────┐
              │         │          │
         SQLAlchemy  Redis      boto3 (S3)
              │     (broker)       │
              ▼         │          ▼
         PostgreSQL  Celery     MinIO / S3
          (port 5432) Workers   (port 9000)
                        │
                     [13-step pipeline]
                        │
                        └──→ Webhook POST → AIKosh
```

**Key architectural facts:**
- The frontend is the **primary interface** — everything is auth-gated behind login
- The FastAPI backend serves **both** the browser UI (cookie auth) and external API consumers (Bearer key auth)
- Assessment processing is **fully async** — never blocking the API thread
- Files are stored in **S3/MinIO permanently** until the user manually deletes them

---

## 3. Tech Stack (Ideal Target)

### Frontend
| Layer | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Components | shadcn/ui (Radix UI + Tailwind) |
| Data Fetching | TanStack Query v5 |
| Forms | React Hook Form + Zod |
| Global State | Zustand |
| Charts | Recharts |

### Backend
| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Language | Python 3.10+ |
| Task Queue | Celery 5.4 |
| Broker / Cache | Redis 7.2 |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Config | Pydantic Settings v2 |
| Logging | structlog |
| Auth | pyjwt + passlib[bcrypt] |
| Profiling | pandas 2.2 + pyarrow |
| Reports | Jinja2 + WeasyPrint |
| Object Storage Client | boto3 |

### Infrastructure
| Layer | Technology |
|---|---|
| Dev Orchestration | Docker Compose (7 services) |
| Production | Kubernetes (k8s/) |
| Object Storage | MinIO (dev) / S3-compatible (prod) |
| Worker Monitoring | Flower (port 5555) |

> **⚠️ Current State:** Frontend is currently React + Vite (not Next.js yet). Migration to Next.js + TypeScript + Tailwind is planned. See Section 7 for current implementation status.

---

## 4. Auth Model

Two mechanisms, same endpoints:

| Client Type | Mechanism | Header / Cookie |
|---|---|---|
| Browser UI | JWT in `HttpOnly` `Secure` `SameSite=Lax` cookie | Cookie: `session_token` |
| External API / AIKosh | API key as Bearer token | `Authorization: Bearer tkt_live_...` |

**Roles:**
- `user` — can submit, view own assessments, download own reports, delete own files
- `reviewer` — all user permissions + can view audit logs
- `admin` — can list/suspend/reactivate users ONLY. **Cannot** view datasets or reports (strict privacy boundary)

**All endpoints require auth except:** `GET /api/v1/health`, `POST /api/v1/auth/login`, `POST /api/v1/auth/register`

---

## 5. Database Entity Dependency Order

Entities cascade in this order — never create a child without its parent existing:

```
users
  └── api_keys          (FK → users.id)
  └── assessments       (FK → users.id, api_keys.key_id)
        └── dataset_metadata    (FK → assessments.assessment_id)
        └── dataset_profiles    (FK → assessments.assessment_id)
        └── domain_scores       (FK → assessments.assessment_id) × 15 rows
        └── assessment_results  (FK → assessments.assessment_id)
        └── audit_logs          (FK → assessments.assessment_id) — APPEND ONLY
```

**Critical rules:**
- `audit_logs` are append-only enforced by a PostgreSQL `CREATE RULE no_delete_audit`. Never try to delete them.
- Raw dataset content is **never** stored in the database. Only statistics, counts, and flags.
- `domain_scores` always has exactly 15 rows per assessment (Domain 11 gets `score=NULL, not_applicable=True` if no synthetic data).

---

## 6. Async Assessment Pipeline (13 Steps)

The Celery `run_assessment` task in `backend/app/worker/tasks.py` must execute these steps:

```
1.  Update assessment status → "processing"
2.  audit_event("assessment_started")
3.  Load metadata from DB (dataset_metadata table)
4.  Download dataset file from S3 using file_key
5.  Run profiler → generate profile JSON
    → store profile JSON to S3
    → write dataset_profiles record to DB
6.  Run 15 domain scorers in parallel (Celery group)
    → each returns DomainScoreResult
    → write 15 domain_scores records to DB
7.  Compute CQI (formula: sum_of_scores / max_possible × 100)
8.  Compute PRS (formula: baseline_risk × sensitivity_multiplier)
9.  Run release classification engine
10. Generate reports (JSON + HTML + PDF) → upload to S3
11. Write assessment_results record to DB
12. Update assessment status → "complete", set completion_timestamp
13. Dispatch webhook task (separate Celery queue: "webhook")
    audit_event("assessment_complete")

On ANY step failure:
    → status = "failed"
    → error_message + error_traceback populated in assessments table
    → audit_event("assessment_failed", {"step": N, "error": "..."})
    → No partial results returned
```

**⚠️ Current Status:** Steps 1-3 are NOT wired. `run_assessment` is a stub returning `{status: "complete"}`. The full pipeline needs implementation.

---

## 7. Current Implementation Status

| Component | Status | File(s) |
|---|---|---|
| Auth (register/login/logout/me/keys) | ✅ Complete | `backend/app/api/v1/auth.py` |
| Admin user management | ✅ Complete | `backend/app/api/v1/admin.py` |
| ORM Models (all 9 tables) | ✅ Complete | `backend/app/models/` |
| DB Schema (PostgreSQL DDL) | ✅ Complete | `backend/alembic/` |
| Health endpoint | ✅ Complete | `backend/app/api/v1/health.py` |
| Assessment submission (skeleton) | ⚠️ Skeleton | `backend/app/api/v1/assess.py` — DB record created, no S3 or Celery dispatch |
| Pre-signed S3 upload URL endpoint | ❌ Not built | Spec in TDD §16, OpenAPI §7.1 |
| Celery assessment pipeline | ❌ Stub | `backend/app/worker/tasks.py` — returns mock |
| Dataset profiler | ❌ Stub/Mock | `backend/app/engine/profiler.py` — hardcoded JSON |
| 15 Domain scorers | ❌ Not built | `backend/app/engine/scoring.py` — abstract base only |
| CQI engine | ❌ Not built | Spec in TDD §10, PRD §17.5 |
| PRS engine | ❌ Not built | Spec in TDD §11, PRD §17.5 |
| Release classifier | ⚠️ Partial | `backend/app/engine/` — may exist but not wired |
| Report generator | ❌ Not built | Spec in TDD §13 |
| S3 client wrapper | ❌ Not built | `backend/app/storage/s3_client.py` missing |
| AIKosh webhook sender | ❌ Not built | Spec in TDD §14 |
| Audit logger | ❌ Not built | Spec in TDD §18 |
| Frontend (Login + Register) | ✅ Working | `frontend/src/pages/LoginPage.jsx`, `RegisterPage.jsx` |
| Frontend (Upload, Dashboard, Report) | ⚠️ Placeholder | `frontend/src/pages/` — pages exist, no real data |
| Frontend (Admin page) | ❌ Not built | |
| Frontend router | ⚠️ Manual state | `frontend/src/App.jsx` — uses `currentView` state, no URL routing |
| Next.js migration | ❌ Planned | Currently React + Vite |

---

## 8. Key File Locations

| What | Where |
|---|---|
| FastAPI entry point | `backend/app/main.py` |
| Auth endpoints | `backend/app/api/v1/auth.py` |
| Admin endpoints | `backend/app/api/v1/admin.py` |
| Assessment endpoints | `backend/app/api/v1/assess.py` |
| Report endpoints | `backend/app/api/v1/reports.py` |
| Health endpoint | `backend/app/api/v1/health.py` |
| FastAPI dependencies (auth guards) | `backend/app/api/deps.py` |
| DB models | `backend/app/models/` (9 files) |
| Pydantic schemas | `backend/app/schemas/` |
| Celery app config | `backend/app/worker/celery_app.py` |
| Celery tasks (pipeline) | `backend/app/worker/tasks.py` ← STUB |
| Profiling engine | `backend/app/engine/profiler.py` ← STUB |
| Scoring engine base | `backend/app/engine/scoring.py` |
| App config / env vars | `backend/app/config.py` |
| Docker orchestration | `docker-compose.yml` |
| Kubernetes manifests | `k8s/` |
| Frontend pages | `frontend/src/pages/` |
| Frontend API client | `frontend/src/api/client.js` |
| Domain scoring YAML config | `backend/config/domain_criteria.yaml` |
| Alembic migrations | `backend/alembic/versions/` |

---

## 9. What NOT To Do

| ❌ Never | Why |
|---|---|
| Store raw dataset rows in PostgreSQL | Only statistics, counts, flags. Files live in S3 only. |
| Delete from `audit_logs` | PostgreSQL rule enforces append-only. It will silently no-op. |
| Use ML/neural models in domain scorers | Scoring must be deterministic and auditable. Pure Python rules from YAML config. |
| Add `allow_origins=["*"]` to CORS | Auth requires `allow_credentials=True` with explicit origins. Wildcard breaks cookies. |
| Auto-delete uploaded files after assessment | Files are user-owned and retained until manually deleted. |
| Return partial results on assessment failure | All-or-nothing. On failure: status="failed", full error logged, no domain scores committed. |
| Hardcode scoring rules in Python | All criteria live in `config/domain_criteria.yaml`. MIDAS 2.0 may change post-Delphi. |
| Break the dual-auth model | Both cookie auth (browser) and Bearer key auth (API) must work on all protected endpoints. |

---

## 10. Docs Reference Guide

| Document | Purpose | Read When |
|---|---|---|
| `AGENTS.md` (this file) | Quick orientation for any agent | First thing, every time |
| `docs/PRD_AIKosh_Dataset_Quality_Toolkit.md` | Product requirements, user stories, 15-domain framework, acceptance criteria | Understanding WHAT and WHY |
| `docs/TDD_AIKosh_Dataset_Quality_Toolkit.md` | Full technical architecture: DB schema, pipeline design, API design, deployment | Understanding HOW |
| `docs/OpenAPI.md` | Complete API contract with request/response schemas and examples | Building or consuming any API endpoint |
| `README.md` | Quick start, dev setup, commands cheatsheet | Getting the stack running |

---

## 11. Development Philosophy

> *"Build a fully functional, secure, end-to-end pipeline skeleton first — UI → API → Worker → DB/S3 → Polling — then implement real engines one by one. Stability and security before complexity."*

**Priority order for new work:**
1. Security and auth correctness always first
2. Pipeline wiring (S3 upload URL → Celery dispatch → status polling) before real scoring logic
3. Real profiler before domain scorers
4. Domain scorers before CQI/PRS engines
5. Dashboard UI after backend results are real

---

*Last updated: June 24, 2026 | v1.1*
