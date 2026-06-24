import hashlib
import re
import secrets
from datetime import datetime, timedelta
import jwt
import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.database import get_async_db
from app.config import settings
from app.models.user import User
from app.models.api_key import ApiKey
from app.api.deps import get_current_user
from app.schemas.user import UserCreate, UserLogin, UserResponse, ApiKeyResponse, ApiKeyCreateResponse

router = APIRouter()

# Password Hashing Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redis Client for Rate Limiting
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# Regex to enforce: Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special character
PASSWORD_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$")

class ApiKeyGenerateRequest(BaseModel):
    owner_name: str
    role: str = "submitter"

def enforce_auth_rate_limit(request: Request):
    """Simple Redis-backed IP rate limiter capping auth attempts to 5 per minute."""
    client_ip = request.client.host
    redis_key = f"auth_rate_limit:{client_ip}"
    try:
        attempts = redis_client.incr(redis_key)
        if attempts == 1:
            redis_client.expire(redis_key, 60)
        if attempts > 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please try again in 1 minute."
            )
    except redis.RedisError as e:
        # Fallback in case Redis container is unavailable (do not block auth in dev, but log warning)
        print(f"Redis Rate Limiter Error: {e}")

def create_session_cookie(response: Response, user_id: str):
    """Signs a JWT token and attaches it to the response via secure HttpOnly cookie."""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire
    }
    encoded_jwt = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    
    response.set_cookie(
        key="session_token",
        value=encoded_jwt,
        httponly=True,
        max_age=settings.JWT_EXPIRY_MINUTES * 60,
        expires=expire.strftime("%a, %d-%b-%Y %H:%M:%S GMT"),
        path="/",
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid password complexity or email already exists"},
        429: {"description": "Too many registration attempts"}
    }
)
async def register(
    request: Request,
    response: Response,
    user_in: UserCreate,
    db: AsyncSession = Depends(get_async_db)
):
    # Enforce Rate Limiting
    enforce_auth_rate_limit(request)
    
    # 1. Enforce Password Complexity (Security Policy)
    if not PASSWORD_REGEX.match(user_in.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, one number, and one special character."
        )

    # 2. Check if user already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account with this email already exists."
        )

    # 3. Create User (Instant Account Activation)
    hashed_password = pwd_context.hash(user_in.password)
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        role="user",
        is_active=True
    )
    db.add(new_user)
    await db.flush() # Populate user ID
    
    # 4. Auto-login on registration
    create_session_cookie(response, new_user.id)
    
    return new_user

@router.post(
    "/login",
    response_model=UserResponse,
    responses={
        400: {"description": "Invalid JSON or body parsing error"},
        401: {"description": "Invalid email or password"},
        403: {"description": "Account has been suspended"},
        429: {"description": "Too many login attempts"}
    }
)
async def login(
    request: Request,
    response: Response,
    user_in: UserLogin,
    db: AsyncSession = Depends(get_async_db)
):
    enforce_auth_rate_limit(request)
    
    # 1. Fetch User
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalars().first()
    
    # 2. Verify Credentials
    if not user or not pwd_context.verify(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended by an administrator."
        )

    # 3. Establish Session Cookie
    create_session_cookie(response, user.id)
    
    return user

@router.post("/logout")
async def logout(response: Response):
    # Expire the session cookie immediately
    response.set_cookie(
        key="session_token",
        value="",
        httponly=True,
        max_age=0,
        expires=0,
        path="/",
        samesite="lax",
        secure=False
    )
    return {"message": "Logged out successfully"}

@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated or invalid token"}
    }
)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# --- API KEY MANAGEMENT ENDPOINTS ---

@router.get(
    "/keys",
    response_model=list[ApiKeyResponse],
    responses={
        401: {"description": "Not authenticated or invalid token"}
    }
)
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.is_active == True)
    )
    return result.scalars().all()

@router.post(
    "/keys",
    response_model=ApiKeyCreateResponse,
    responses={
        400: {"description": "Invalid JSON or body parsing error"},
        401: {"description": "Not authenticated or invalid token"}
    }
)
async def generate_key(
    request: ApiKeyGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    # Generate tkt_ prefix + 32 hex character token
    token_suffix = secrets.token_hex(16)
    raw_key = f"tkt_{token_suffix}"
    
    # Compute SHA-256 hash of raw key
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:10] # tkt_ + first 6 chars
    
    new_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=current_user.id,
        owner_name=request.owner_name,
        role=request.role,
        is_active=True
    )
    
    db.add(new_key)
    await db.flush() # Populate key_id
    
    # Return create payload including raw key (Only shown once!)
    return ApiKeyCreateResponse(
        key_id=new_key.key_id,
        raw_key=raw_key,
        key_prefix=new_key.key_prefix,
        owner_name=new_key.owner_name,
        role=new_key.role,
        created_at=new_key.created_at
    )

@router.delete(
    "/keys/{key_id}",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated or invalid token"},
        404: {"description": "API Key not found or does not belong to you"}
    }
)
async def revoke_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_id == key_id, ApiKey.user_id == current_user.id)
    )
    key = result.scalars().first()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key not found or does not belong to you."
        )
        
    # Mark as inactive to revoke
    key.is_active = False
    return {"message": "API Key revoked successfully"}
