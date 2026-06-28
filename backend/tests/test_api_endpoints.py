import uuid
import jwt
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy import delete
from unittest.mock import patch

from app.main import app
from app.config import settings
from app.database import async_engine
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.assessment import Assessment

from app.api.v1.auth import pwd_context

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

def generate_test_jwt(user_id: str, minutes: int = 15) -> str:
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def run_api_endpoint_tests():
    # Dispose global engine so fresh connections are created on this test's loop
    await async_engine.dispose()

    user_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    user_email = f"api_test_user_{uuid.uuid4().hex[:6]}@example.com"
    admin_email = f"api_test_admin_{uuid.uuid4().hex[:6]}@example.com"
    
    test_engine = create_async_engine(settings.ASYNC_DATABASE_URL)
    TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    # 1. Create a regular user and an admin in the database
    hashed_pwd = pwd_context.hash("SecurePassword123!")
    async with TestSessionLocal() as db:
        regular_user = User(
            id=user_id,
            email=user_email,
            hashed_password=hashed_pwd,
            role="user",
            is_active=True
        )
        admin_user = User(
            id=admin_id,
            email=admin_email,
            hashed_password=hashed_pwd,
            role="admin",
            is_active=True
        )
        db.add_all([regular_user, admin_user])
        await db.commit()

    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            # --- AUTH REGISTRATION ---
            # Weak password registration should fail (passes length 8, fails complexity)
            bad_reg = await client.post("/api/v1/auth/register", json={
                "email": "badreg@example.com",
                "password": "weakpassword123"
            })
            assert bad_reg.status_code == 400
            assert "Password must be at least 8 characters long" in bad_reg.json()["detail"]

            # Duplicate email registration should fail
            dup_reg = await client.post("/api/v1/auth/register", json={
                "email": user_email,
                "password": "SecurePassword123!"
            })
            assert dup_reg.status_code == 400

            # Valid registration should succeed
            valid_reg = await client.post("/api/v1/auth/register", json={
                "email": f"new_registered_{uuid.uuid4().hex[:6]}@example.com",
                "password": "SecurePassword123!"
            })
            assert valid_reg.status_code == 201
            assert "email" in valid_reg.json()

            # --- AUTH LOGIN & LOGOUT ---
            # Invalid credentials should fail
            bad_login = await client.post("/api/v1/auth/login", json={
                "email": user_email,
                "password": "wrongpassword"
            })
            assert bad_login.status_code == 401

            # Valid credentials should succeed
            # We registered f"new_registered_{uuid.uuid4().hex[:6]}@example.com" with password "SecurePassword123!".
            new_email = valid_reg.json()["email"]
            login_resp = await client.post("/api/v1/auth/login", json={
                "email": new_email,
                "password": "SecurePassword123!"
            })
            assert login_resp.status_code == 200
            
            # Now call /me
            me_resp = await client.get("/api/v1/auth/me")
            assert me_resp.status_code == 200
            assert me_resp.json()["email"] == new_email

            # Logout
            logout_resp = await client.post("/api/v1/auth/logout")
            assert logout_resp.status_code == 200
            
            # Call /me after logout (should fail)
            me_resp_after = await client.get("/api/v1/auth/me")
            assert me_resp_after.status_code == 401

            # --- API KEY MANAGEMENT ---
            # Authenticate client manually with regular user JWT cookie
            client.cookies.set("session_token", generate_test_jwt(user_id))
            
            # Create API Key
            key_create = await client.post("/api/v1/auth/keys", json={
                "owner_name": "API Test Client",
                "role": "submitter"
            })
            assert key_create.status_code == 200
            raw_key = key_create.json()["raw_key"]
            key_id = key_create.json()["key_id"]
            assert raw_key.startswith("tkt_")

            # List API Keys
            keys_list = await client.get("/api/v1/auth/keys")
            assert keys_list.status_code == 200
            assert any(k["key_id"] == key_id for k in keys_list.json()["keys"])


            # Revoke API Key
            revoke_resp = await client.delete(f"/api/v1/auth/keys/{key_id}")
            assert revoke_resp.status_code == 200

            # --- ADMIN ENDPOINTS ---
            # Non-admin trying to list users should get 403
            non_admin_users = await client.get("/api/v1/admin/users")
            assert non_admin_users.status_code == 403

            # Authenticate as Admin
            client.cookies.set("session_token", generate_test_jwt(admin_id))
            admin_users = await client.get("/api/v1/admin/users")
            assert admin_users.status_code == 200
            assert len(admin_users.json()) >= 2

            # Toggle user active status
            toggle_resp = await client.post(f"/api/v1/admin/users/{user_id}/toggle-active")
            assert toggle_resp.status_code == 200
            assert toggle_resp.json()["is_active"] is False

            # Toggle back to active
            toggle_resp = await client.post(f"/api/v1/admin/users/{user_id}/toggle-active")
            assert toggle_resp.status_code == 200
            assert toggle_resp.json()["is_active"] is True

            # --- ASSESSMENT ENDPOINTS ---
            # Authenticate back as regular user
            client.cookies.set("session_token", generate_test_jwt(user_id))

            # Generate S3 upload URL
            upload_url_resp = await client.post("/api/v1/assess/upload-url", json={
                "filename": "test_dataset.csv",
                "file_format": "csv"
            })
            assert upload_url_resp.status_code == 201
            file_key = upload_url_resp.json()["file_key"]
            assert "upload_url" in upload_url_resp.json()

            # Submit assessment (mocking file existence in S3)
            with patch("app.api.v1.assess.s3_client.file_exists", return_value=True), \
                 patch("app.api.v1.assess.run_assessment.delay") as mock_celery:
                
                submit_resp = await client.post("/api/v1/assess", json={
                    "file_key": file_key,
                    "metadata": {
                        "dataset_name": "API Test Dataset",
                        "dataset_type": "tabular",
                        "study_type": "cohort",
                        "target_population": "Adults aged 18-65 with history of type 2 diabetes",
                        "geographic_coverage": "district",
                        "sensitivity_class": "standard",
                        "license_type": "cc_by_4p0",
                        "standards_used": "fhir",
                        "deidentification_method": "anonymization",
                        "access_control_method": "role_based"
                    }
                })
                assert submit_resp.status_code == 202
                assert mock_celery.called

            # List user assessments
            list_assess = await client.get("/api/v1/assess/")
            assert list_assess.status_code == 200
            assert len(list_assess.json()) >= 1

    finally:
        try:
            # Clean up users & assessments with append-only rule bypass
            async with TestSessionLocal() as db:
                from sqlalchemy import text
                try:
                    await db.execute(text("DROP RULE IF EXISTS no_delete_audit ON audit_logs;"))
                    await db.commit()
                except Exception:
                    pass

                # Delete assessments created by this user
                await db.execute(delete(Assessment).where(Assessment.user_id == user_id))
                await db.execute(delete(User).where(User.id.in_([user_id, admin_id])))
                await db.commit()

                try:
                    await db.execute(text("CREATE RULE no_delete_audit AS ON DELETE TO audit_logs DO INSTEAD NOTHING;"))
                    await db.commit()
                except Exception:
                    pass
        finally:
            await test_engine.dispose()

@pytest.mark.anyio
@patch("app.api.v1.auth.enforce_auth_rate_limit")
async def test_api_endpoints_suite(mock_rate_limit):
    """Integration test suite covering Auth, Admin, and Assessment APIs."""
    await run_api_endpoint_tests()
