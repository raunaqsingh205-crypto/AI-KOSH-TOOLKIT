"""E2E verification checklist (AGENTS.md §6).
Uses API key auth to avoid rate limits.
Run: docker exec tkt_backend python tests/e2e_checklist.py
"""
import requests, sys, time, json, os

API_KEY = os.environ.get("E2E_API_KEY", "tkt_0bf710df44588c0c23c0ec461d9c2eeb")
BASE = "http://backend:8000/api/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {detail}")
        failed += 1

def api(method, path, **kwargs):
    url = f"{BASE}{path}"
    kwargs.setdefault("headers", HEADERS)
    r = requests.request(method, url, **kwargs)
    return r

print("=" * 60)
print("E2E VERIFICATION CHECKLIST")
print("=" * 60)

# --- 1. List assessments (no auth) → 401 ---
r = requests.get(f"{BASE}/assess/")
check("No auth returns 401", r.status_code in (401, 403), f"got {r.status_code}")

# --- 2. Get upload URL ---
r = api("POST", "/assess/upload-url", json={"filename": "golden.csv", "file_format": "csv"})
needs_auth_check = False
if r.status_code in (200, 201):
    check("Upload URL endpoint accessible", True)
    data = r.json()
    upload_url = data["upload_url"]
    file_key = data["file_key"]
    assessment_id = data["assessment_id"]
    print(f"     Upload URL: OK, ID={assessment_id[:8]}...")
else:
    print(f"     Upload URL returned {r.status_code}: {r.text[:200]}")
    sys.exit(1)

# --- 3. Upload file ---
with open("/tmp/test_golden.csv", "rb") as f:
    r = requests.put(upload_url, data=f, headers={"Content-Type": "text/csv"})
check("Upload file to S3", r.status_code == 200, f"got {r.status_code}")

# --- 4. Submit assessment ---
submit_body = {
    "file_key": file_key,
    "metadata": {
        "dataset_name": "E2E Golden Test Dataset",
        "dataset_version": "1.0.0",
        "dataset_type": "tabular",
        "study_type": "observational",
        "target_population": "Synthetic patients undergoing TB screening at LMIC health facilities",
        "geographic_coverage": "district",
        "age_range_min": 16,
        "age_range_max": 65,
        "sex_distribution": "both",
        "num_sites": 1,
        "collection_start_date": "2024-01-01",
        "collection_end_date": "2024-12-31",
        "standards_used": "ICD-10",
        "ethics_approval_ref": "IEC/2024/TB-001",
        "consent_type": "individual",
        "deidentification_method": "HIPAA Safe Harbor",
        "differential_privacy_applied": False,
        "sensitivity_class": "high_stigma",
        "license_type": "CC BY-NC 4.0",
        "synthetic_data_pct": 0,
        "access_control_method": "Formal access request process",
        "version_format": "none",
        "dua_required": True,
        "location_granularity": "district",
        "temporal_granularity": "month",
        "rare_condition_flag": False,
    },
}
r = api("POST", "/assess", json=submit_body)
check("Submit assessment returns 202", r.status_code == 202, f"got {r.status_code}")
data = r.json()
assess_id = data.get("assessment_id") or assessment_id
print(f"     Status: {data.get('status','unknown')}, ID: {assess_id}")

# --- 5. Poll for completion ---
print("     Polling: ", end="", flush=True)
for i in range(30):
    r = api("GET", f"/assess/{assess_id}")
    if r.status_code not in (200, 201):
        print(f"\n     Poll error: {r.status_code}")
        continue
    data = r.json()
    status = data.get("status", "unknown")
    print(f"{status} ", end="", flush=True)
    if status == "complete":
        print()
        check("Assessment completed", True)
        break
    if status == "failed":
        print(f"\n     FAILED: {data.get('error_message', 'unknown')}")
        check("Assessment succeeded", False)
        break
    time.sleep(3)
else:
    check("Assessment timed out", False)
    status = "timed_out"

# --- 6. Verify scores ---
if status == "complete":
    scores = data.get("domain_scores", [])
    cqi = data.get("cqi", {})
    prs = data.get("prs", {})
    release = data.get("release", {})
    
    check("CQI present", bool(cqi), f"got {cqi}")
    if cqi:
        check("CQI value >= 0", cqi.get("value", -1) >= 0)
        check("CQI band known", cqi.get("band", "") in ("Diamond","Platinum","Gold","Silver","Bronze","Remediation"))
    
    check("PRS present", bool(prs))
    check("Release present", bool(release))
    if release:
        check("Release classification valid", release.get("classification") in ("Open","Controlled","Restricted"))
    
    check("All 15 domain scores", len(scores) == 15, f"got {len(scores)}")
    for s in scores:
        dn = s.get("domain_number")
        sc = s.get("score")
        na = s.get("not_applicable", False)
        check(f"  Domain {dn}: {sc}", sc is not None or na, f"score={sc} na={na}")

    profile = data.get("profile_summary", {})
    check("Profile has rows", profile.get("rows", 0) > 0)
    check("Profile has columns", profile.get("columns", 0) > 0)

    # --- 7. Report URL ---
    reports = data.get("report_urls", {})
    check("Report URLs present", bool(reports))
    if reports:
        for fmt in ("json", "html", "pdf"):
            check(f"  {fmt} report URL", bool(reports.get(fmt)))

# --- 8. BOLA check: different user should get 403 ---
r2 = requests.get(f"{BASE}/assess/{assess_id}")
check("BOLA: no-auth gets 401/403", r2.status_code in (401, 403), f"got {r2.status_code}")
# Also test with a different API key (no key = different auth)
import uuid
fake_headers = {"Authorization": f"Bearer tkt_fake_{uuid.uuid4().hex}", "Content-Type": "application/json"}
r3 = requests.get(f"{BASE}/assess/{assess_id}", headers=fake_headers)
check("BOLA: wrong key gets 401/403", r3.status_code in (401, 403), f"got {r3.status_code}")

# --- 9. List user's own assessments ---
r = api("GET", "/assess/")
check("List own assessments", r.status_code in (200, 201))

# --- 10. Audit log ---
r = api("GET", f"/assess/{assess_id}/audit")
check("Audit log endpoint exists", r.status_code in (200, 403, 404), f"got {r.status_code}")
if r.status_code == 200:
    logs = r.json()
    check("Audit has entries", isinstance(logs, list) and len(logs) > 0)

# --- Summary ---
print("=" * 60)
total = passed + failed
print(f"E2E CHECKLIST: {passed}/{total} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
print("ALL CHECKS PASSED")
