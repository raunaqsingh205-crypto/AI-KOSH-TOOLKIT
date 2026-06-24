from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.user import User
from app.api.deps import get_current_active_admin
from app.schemas.user import UserResponse

router = APIRouter()

@router.get(
    "/users",
    response_model=list[UserResponse],
    responses={
        401: {"description": "Not authenticated or invalid token"},
        403: {"description": "Forbidden. Admin privileges required."}
    }
)
async def list_users(
    admin: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """Admin-only endpoint to list all users in the system."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post(
    "/users/{user_id}/toggle-active",
    response_model=UserResponse,
    responses={
        400: {"description": "Cannot deactivate own admin account"},
        401: {"description": "Not authenticated or invalid token"},
        403: {"description": "Forbidden. Admin privileges required."},
        404: {"description": "User not found"}
    }
)
async def toggle_user_active(
    user_id: str,
    admin: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_async_db)
):
    """Admin-only endpoint to activate or suspend a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own admin account"
        )
        
    # Toggle active status
    user.is_active = not user.is_active
    return user
