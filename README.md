# AIKosh Dataset Quality Evaluation Toolkit

![AIKosh Logo](https://img.shields.io/badge/AIKosh-Dataset%20Quality-blue?style=for-the-badge)

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)](#)
[![Python Version](https://img.shields.io/badge/python-3.10-blue?style=flat-square&logo=python)](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/requirements.txt)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.x-blue?style=flat-square&logo=postgresql)](#)
[![Celery](https://img.shields.io/badge/Celery-5.4.0-green?style=flat-square&logo=celery)](#)
[![Redis](https://img.shields.io/badge/Redis-7.2-red?style=flat-square&logo=redis)](#)
[![MinIO](https://img.shields.io/badge/MinIO-Object%20Storage-orange?style=flat-square)](#)

> Automated dataset quality assessment, clinical profiling, and privacy scoring toolkit for the AIKosh platform.

---

## Table of Contents
1. [Overview & Concept](#1-overview--concept)
2. [Key Features](#2-key-features)
3. [System Architecture](#3-system-architecture)
4. [Tech Stack](#4-tech-stack)
5. [Security & Authentication](#5-security--authentication)
6. [Living Documentation & Reference Disclaimer](#6-living-documentation--reference-disclaimer)
7. [Prerequisites](#7-prerequisites)
8. [Quick Start](#8-quick-start)
9. [Configuration Reference](#9-configuration-reference)
10. [Development Setup (Without Docker)](#10-development-setup-without-docker)
11. [Database Migrations (Alembic)](#11-database-migrations-alembic)
12. [Testing](#12-testing)
13. [Production Deployment (Kubernetes)](#13-production-deployment-kubernetes)

---

## 1. Overview & Concept

The **AIKosh Dataset Quality Evaluation Toolkit** provides a robust, standardized framework to evaluate, profile, and audit datasets intended for artificial intelligence and machine learning applications in clinical and healthcare domains. 

In clinical AI, data quality directly correlates with patient safety, algorithmic bias, and model generalizability. The toolkit acts as a gatekeeper, scoring uploaded datasets across **15 distinct evaluation domains** including clinical representative balance, annotation methodology accuracy, and privacy compliance. It computes a unified Clinical Quality Index (CQI) and Patient Risk Score (PRS), generating downloadable audit reports in HTML, JSON, and PDF formats.

This system is built to scale horizontally using an asynchronous task architecture, supporting massive tabular datasets (e.g., millions of clinical rows) while preserving low API latency.

---

## 2. Key Features

| Feature | Description | Reference |
| :--- | :--- | :--- |
| **CQI Scoring Engine** | Evaluates datasets against 15 clinical and technical domains, calculating a normalized CQI score (0–100) and mapping it to certification bands (Diamond, Platinum, Gold, Silver, Bronze, Remediation). | [TDD §4.1](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docs/TDD_AIKosh_Dataset_Quality_Toolkit.md) |
| **PRS Calculation** | Computes Patient Risk Scores (PRS) based on data sensitivity levels, de-identification methods, and the application of Differential Privacy. | [TDD §4.2](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docs/TDD_AIKosh_Dataset_Quality_Toolkit.md) |
| **Automated Profiling** | Background workers compute structural and statistical summaries of uploaded datasets using a fast Arrow/Pandas ingestion pipeline. | [dataset_profile.py](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/app/models/dataset_profile.py) |
| **Compliance Auditing** | Tracks all evaluation job transitions and model overrides in an append-only, deletion-protected audit log table. | [audit_log.py](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/app/models/audit_log.py) |
| **Multi-Format Reports** | Generates downloadable and shareable evaluation reports in JSON, HTML, and print-ready PDF formats. | [assessment_result.py](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/app/models/assessment_result.py) |

---

## 3. System Architecture

### Data Flow Overview

```
                      +-------------------+
                      |   React Frontend  | (Port 3000)
                      +---------+---------+
                                |
                                | HTTP REST APIs (with API Key)
                                v
                      +-------------------+
                      |   FastAPI App     | (Port 8000)
                      +----+----+----+----+
                           |    |    |
           +---------------+    |    +---------------+
           | SQL (Async)        |                    | S3 API (Boto3)
           v                    v Redis Broker       v
     +-----------+         +----+------+       +-----------+
     | PostgreSQL|         |   Redis   |       |   MinIO   | (Ports 9000/9001)
     +-----------+         +----+------+       +-----------+
                                |
                                | Queues: "assessment", "webhook"
                                v
                      +---------+---------+
                      |   Celery Workers  | (Asynchronous Pipelines)
                      +---------+---------+
                                |
                                +--> [Ingestion] -> [Profiling] -> [Domain Scoring] -> [Report Generation]
```

### Repository Structure

```
.
├── .agents/                 # Internal development configurations
├── backend/                 # Backend codebase (FastAPI + Celery)
│   ├── alembic/             # Database migrations configuration and versions
│   ├── app/
│   │   ├── api/             # API Router endpoints (assessments, reports, health)
│   │   ├── models/          # SQLAlchemy Database Models (TDD §6 compliant)
│   │   ├── schemas/         # Pydantic Schemas for Request/Response validation
│   │   ├── worker/          # Celery worker definitions and task pipelines
│   │   ├── config.py        # Settings configuration using Pydantic Settings
│   │   ├── database.py      # SQLAlchemy engine and session pool setups
│   │   └── main.py          # FastAPI application entry point
│   ├── tests/               # Backend test suites
│   ├── Dockerfile           # Backend container image build blueprint
│   └── requirements.txt     # Python backend dependencies
├── frontend/                # Frontend codebase (React + Vite)
│   ├── src/                 # React component declarations and state
│   ├── Dockerfile           # Frontend web-server container configuration
│   └── package.json         # Node.js dependencies configuration
├── k8s/                     # Production Kubernetes deployments manifests
│   ├── api-deployment.yaml  # FastAPI web-server pods deployment (3 replicas)
│   ├── ingress.yaml         # Ingress Nginx TLS and routing definitions
│   ├── postgres-statefulset.yaml # StatefulSet definition for Postgres storage
│   ├── redis-deployment.yaml # Key-value store deployment
│   ├── worker-deployment.yaml # Split Celery worker deployments (assessment / webhook)
│   └── worker-hpa.yaml      # Horizontal Pod Autoscaler for assessment workers
└── docker-compose.yml       # Local developer compose setup (8 coordinated services)
```

---

## 4. Tech Stack

| Technology | Purpose | Configuration File |
| :--- | :--- | :--- |
| **FastAPI** | High-performance, asynchronous REST API gateway. | [backend/app/main.py](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/app/main.py) |
| **React (Vite)** | Responsive single-page application dashboard. | [frontend/package.json](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/frontend/package.json) |
| **PostgreSQL 16** | Core relational persistence with custom enums, check constraints, and append-only rules. | [docker-compose.yml](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docker-compose.yml) |
| **Celery** | Asynchronous task queue for long-running dataset profiling and scoring. | [backend/requirements.txt](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/requirements.txt) |
| **Redis** | Message broker for Celery queues and task result caching. | [docker-compose.yml](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docker-compose.yml) |
| **MinIO** | S3-compatible local object storage for raw dataset uploads and generated reports. | [docker-compose.yml](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docker-compose.yml) |

---

## 5. Security & Authentication

API calls to protected endpoints are secured using a headers-based validation scheme:
*   Header parameter: `X-API-Key`
*   Database backed table: `api_keys` (stores SHA-256 hashes of client secrets)
*   Roles available: `submitter`, `reviewer`, `admin`

Only clients possessing a valid API key with appropriate permissions (e.g. `submitter` for job submissions, `admin` for metadata overrides) can execute evaluations.

---

## 6. Living Documentation & Reference Disclaimer

> [!IMPORTANT]
> The architectural design patterns, dataset questionnaires, and schemas found inside the **[docs/](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/docs/)** folder are **living reference guidelines**. They represent target specifications but are subject to modification and refinements as development progresses and integration challenges arise. The active code base remains the source of truth.

---

## 7. Prerequisites

Ensure you have the following system-level software installed before setup:
*   **Docker Engine:** version `20.10.x` or newer (supporting Compose V2)
*   **Python:** version `3.10.x` (for local backend development)
*   **Node.js:** version `18.x` LTS (for local frontend development)
*   **PostgreSQL Client (`psql`):** version `16.x` (optional, for direct SQL debugging)

---

## 8. Quick Start

Run the entire platform locally with a single command:

```bash
# 1. Start all 8 docker compose services
docker compose up --build

# 2. Apply database schemas
docker compose exec backend alembic upgrade head

# 3. Access the platform
# - React Web Dashboard: http://localhost:3000
# - API Swagger Docs: http://localhost:8000/docs
# - MinIO Object Storage Panel: http://localhost:9001 (minioadmin / minioadmin)
# - Flower Celery Monitor: http://localhost:5555
```

---

## 9. Configuration Reference

System behavior is configured using environment variables defined in `.env` files. You can copy the template files:
*   Root compose configuration: [`.env.example`](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/.env.example) -> `.env`
*   Backend local overrides: [`backend/.env.example`](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/backend/.env.example) -> `backend/.env`

Key configurations:
*   `POSTGRES_DB`: Name of target PostgreSQL database (`aikosh_quality`).
*   `REDIS_URL`: Redis connection URL (`redis://redis:6379/0`).
*   `S3_ENDPOINT_URL`: Object storage connection endpoint (`http://minio:9000`).
*   `API_KEY_SECRET`: Encryption key for static fallback checks.

---

## 10. Development Setup (Without Docker)

To run the components locally on your host machine for faster debugging cycles:

### A. Run Backend App
1. Navigate to the backend directory and create a virtual environment:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run Alembic migrations:
   ```bash
   alembic upgrade head
   ```
4. Start FastAPI server using Uvicorn:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

### B. Run Frontend App
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node packages:
   ```bash
   npm install
   ```
3. Run development web server:
   ```bash
   npm run dev
   ```

---

## 11. Database Migrations (Alembic)

Database schema modifications are managed using Alembic.
*   **Apply all pending migrations:**
    ```bash
    docker compose exec backend alembic upgrade head
    ```
*   **Revert the last applied migration:**
    ```bash
    docker compose exec backend alembic downgrade -1
    ```
*   **Generate a new autodetected migration script:**
    ```bash
    docker compose exec backend alembic revision --autogenerate -m "description_of_change"
    ```

---

## 12. Testing

Run the test suites using `pytest` inside the backend container:

```bash
docker compose exec backend pytest
```

Test coverage focuses on scoring formulas, PRS risk calculations, dataset metadata model relationships, and API endpoints validation.

---

## 13. Production Deployment (Kubernetes)

Production manifests are housed inside the **[k8s/](file:///c:/Users/medha/OneDrive/Desktop/AI-KOSH-TOOLKIT/k8s/)** directory, targeting the namespace `aikosh-quality-toolkit`.

To deploy the cluster services:
```bash
# 1. Apply databases and brokers
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/redis-deployment.yaml

# 2. Deploy API servers and Celery workers
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml

# 3. Configure Ingress routes and Autoscalers
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/worker-hpa.yaml
```

The system scales background worker pods dynamically between `3` and `20` replicas via the Horizontal Pod Autoscaler (`k8s/worker-hpa.yaml`) based on Celery queue depth metrics.
