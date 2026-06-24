import asyncio
import uuid
import jwt
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy import delete, text

from app.main import app
from app.database import AsyncSessionLocal, async_engine
from app.config import settings
from app.models.user import User
from app.models.assessment import Assessment

def generate_test_jwt(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=15)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def run_security_tests():
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    assessment_id = uuid.uuid4()
    
    # 1. Create User A, User B, and Admin in database async
    async with AsyncSessionLocal() as db:
        user_a = User(
            id=user_a_id,
            email="usera@example.com",
            hashed_password="somehashedpwd123",
            role="user",
            is_active=True
        )
        user_b = User(
            id=user_b_id,
            email="userb@example.com",
            hashed_password="somehashedpwd123",
            role="user",
            is_active=True
        )
        admin_user = User(
            id=admin_id,
            email="admin@example.com",
            hashed_password="somehashedpwd123",
            role="admin",
            is_active=True
        )
        db.add_all([user_a, user_b, admin_user])
        await db.flush()
        
        assessment = Assessment(
            assessment_id=assessment_id,
            dataset_id="dataset_b_123",
            user_id=user_b_id,
            status="complete",
            toolkit_version="1.0.0"
        )
        db.add(assessment)
        await db.commit()

    try:
        # 2. Make requests using AsyncClient to verify isolation boundaries
        async with AsyncClient(app=app, base_url="http://test") as client:
            # --- TEST CASE 1: BOLA (Broken Object Level Authorization) ---
            jwt_token_a = generate_test_jwt(user_a_id)
            client.cookies.set("session_token", jwt_token_a)
            
            # User A tries to view User B's assessment status (should get 403)
            response = await client.get(f"/api/v1/assess/{assessment_id}")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied. You do not own this assessment."
            
            # User A tries to download User B's report (should get 403)
            report_response = await client.get(f"/api/v1/assess/{assessment_id}/report?format=json")
            assert report_response.status_code == 403
            assert report_response.json()["detail"] == "Access denied. You do not own this assessment."
            
            # --- TEST CASE 2: Admin Isolation ---
            jwt_token_admin = generate_test_jwt(admin_id)
            client.cookies.set("session_token", jwt_token_admin)
            
            # Admin tries to view User B's assessment status (should get 403)
            admin_response = await client.get(f"/api/v1/assess/{assessment_id}")
            assert admin_response.status_code == 403
            assert admin_response.json()["detail"] == "Access denied. System admins are strictly isolated from assessment data."
            
    finally:
        # 3. Clean up database records using session.delete to handle cascading relationships correctly
        async with AsyncSessionLocal() as db:
            # Drop append-only rule temporarily to allow cascade deletion of assessments/audit_logs
            try:
                await db.execute(text("DROP RULE IF EXISTS no_delete_audit ON audit_logs;"))
                await db.commit()
            except Exception as e:
                print(f"Error dropping rule: {e}")
                
            # Reload and delete
            res_a = await db.execute(select(Assessment).where(Assessment.assessment_id == assessment_id))
            a_obj = res_a.scalars().first()
            if a_obj:
                await db.delete(a_obj)
                
            # Delete users
            res_users = await db.execute(select(User).where(User.id.in_([user_a_id, user_b_id, admin_id])))
            for u in res_users.scalars().all():
                await db.delete(u)
                
            await db.commit()
            
            # Restore append-only rule on audit_logs
            try:
                await db.execute(text("CREATE RULE no_delete_audit AS ON DELETE TO audit_logs DO INSTEAD NOTHING;"))
                await db.commit()
            except Exception as e:
                print(f"Error restoring rule: {e}")
            
        # Dispose of engine to release database connections bound to this loop
        await async_engine.dispose()

def test_security_isolation_boundaries():
    """Triggers both BOLA and Admin isolation boundary integration tests."""
    asyncio.run(run_security_tests())
