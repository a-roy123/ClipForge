from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core import security
from app.core.ratelimit import limiter
from app.db.models import RefreshToken, User
from app.db.session import get_db
from app.schema.user import UserAuthResponse, UserCreate, UserLogin

# The prefix lives purely in main.py to prevent doubling
router = APIRouter(tags=["Authentication"])


@router.post("/register", response_model=UserAuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate, 
    response: Response, 
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user account.
    - Validates uniqueness of email and username (409 Conflict)
    - Hashes password securely
    - Generates Access & Refresh JWT pairs
    - Stores the Refresh Token hash in the database (keyed by JTI)
    - Sets the raw Refresh Token in a secure httpOnly cookie
    - Returns a structured dictionary containing the access token and user metadata
    """
    
    # 1. Check if the email or username already exists (Issue 1: Using 409 Conflict)
    email_check = await db.execute(select(User).where(User.email == user_in.email))
    if email_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )
        
    username_check = await db.execute(select(User).where(User.username == user_in.username))
    if username_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This username is already taken."
        )

    # 2. Hash password and instantiate the database model
    hashed_pwd = security.hash_password(user_in.password)
    new_user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hashed_pwd
    )
    
    db.add(new_user)
    await db.flush()  # Populates new_user.id for token creation

    # 3. Generate Token Pairs
    access_token = security.create_access_token(user_id=str(new_user.id))
    raw_refresh_token, jti_uuid = security.create_refresh_token(user_id=str(new_user.id))
    
    # 4. Save Refresh Token Record to Database
    refresh_expiry = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    db_refresh_token = RefreshToken(
        id=uuid.UUID(jti_uuid),
        token_hash=security.hash_token(raw_refresh_token),
        user_id=new_user.id,
        expires_at=refresh_expiry
    )
    
    db.add(db_refresh_token)
    await db.commit()  
    await db.refresh(new_user)

    # 5. Set the httpOnly cookie on the response
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,  
        max_age=30 * 24 * 60 * 60  
    )

    # 6. Return standard structured dictionary (Issue 2 Fix)
    return {
        "access_token": access_token,
        "user": new_user
    }


@router.post("/login", response_model=UserAuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,  # Required by slowapi to evaluate rate limits
    user_in: UserLogin, 
    response: Response, 
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate a user.
    - Rate limited to 10 requests per minute via slowapi
    - Looks up user by email
    - Verifies password hash
    - Generates Access + Refresh pairs
    - Stores the Refresh Token hash in the database (keyed by JTI)
    - Sets httpOnly cookie and returns access token + user object
    """
    
    # 1. Find user by email
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()
    
    # 2. Verify password (Use a generic 401 error message to hide user existence details)
    if not user or not security.verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated"
        )

    # 3. Same token generation flow as register
    access_token = security.create_access_token(user_id=str(user.id))
    raw_refresh_token, jti_uuid = security.create_refresh_token(user_id=str(user.id))
    
    # 4. Save Refresh Token Record to Database (JTI as ID, hashed token as column value)
    refresh_expiry = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    db_refresh_token = RefreshToken(
        id=uuid.UUID(jti_uuid),
        token_hash=security.hash_token(raw_refresh_token),
        user_id=user.id,
        expires_at=refresh_expiry
    )
    
    db.add(db_refresh_token)
    await db.commit()

    # 5. Set the httpOnly cookie on the response
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Dev mode
        max_age=30 * 24 * 60 * 60  # 30 days in seconds
    )

    # 6. Return standard structured dictionary matching UserAuthResponse
    return {
        "access_token": access_token,
        "user": user
    }



@router.post("/refresh", response_model=UserAuthResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request,  # Kept first for slowapi compliance
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh Token Rotation Flow.
    - Rate limited to 20 requests per minute via slowapi
    - Extracts raw refresh token from httpOnly cookie
    - Decodes JWT payload to extract JTI and User ID
    - Queries DB by JTI to verify token existence, hash matching, and expiration/revocation
    - Invalidates the used refresh token (revoked=True)
    - Issues and stores a brand-new token pair
    """
    
    # 1. Read refresh token from the cookie
    raw_refresh_token = request.cookies.get("refresh_token")
    if not raw_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )

    # 2. Decode the token (automatically validates structure and internal expiration time)
    payload = security.decode_refresh_token(raw_refresh_token)
    jti_uuid = payload.get("jti")
    user_id = payload.get("sub")

    if not jti_uuid or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token signature"
        )

    # 3. Look up token state in DB by JTI (the primary key 'id')
    result = await db.execute(select(RefreshToken).where(RefreshToken.id == uuid.UUID(jti_uuid)))
    db_token = result.scalar_one_or_none()

    # 4. Strict structural verification checks
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token record not found"
        )
        
    if db_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )
        
    # Standardize timezone handling for DB datetime comparison
    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )
        
    if db_token.token_hash != security.hash_token(raw_refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token fingerprint mismatch"
        )

    # 5. Verify the associated user is still valid and active
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = user_result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Associated user account is inactive or missing"
        )

    # 6. Token Rotation: Revoke the old token row
    db_token.revoked = True

    # 7. Generate a new token pair
    new_access_token = security.create_access_token(user_id=str(user.id))
    new_raw_refresh_token, new_jti_uuid = security.create_refresh_token(user_id=str(user.id))
    
    # 8. Save the new refresh token row using the JTI architecture rules
    refresh_expiry = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    new_db_refresh_token = RefreshToken(
        id=uuid.UUID(new_jti_uuid),
        token_hash=security.hash_token(new_raw_refresh_token),
        user_id=user.id,
        expires_at=refresh_expiry
    )
    
    db.add(new_db_refresh_token)
    await db.commit()  # Save the revocation and the new token state atomically

    # 9. Overwrite cookie with the new raw refresh token string
    response.set_cookie(
        key="refresh_token",
        value=new_raw_refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Dev mode
        max_age=30 * 24 * 60 * 60  # 30 days
    )

    # 10. Return fresh access context
    return {
        "access_token": new_access_token,
        "user": user
    }



@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Log out the current user.
    - Extracts raw refresh token from httpOnly cookie
    - Safely decodes token to look up the JTI 
    - Marks the token row as revoked in the database
    - Clears the client-side httpOnly cookie unconditionally
    """
    raw_refresh_token = request.cookies.get("refresh_token")
    
    if raw_refresh_token:
        try:
            # Decode to pull the JTI and locate the DB record
            payload = security.decode_refresh_token(raw_refresh_token)
            jti_uuid = payload.get("jti")
            
            if jti_uuid:
                result = await db.execute(
                    select(RefreshToken).where(RefreshToken.id == uuid.UUID(jti_uuid))
                )
                db_token = result.scalar_one_or_none()
                
                if db_token and not db_token.revoked:
                    db_token.revoked = True
                    await db.commit()
                    
        except HTTPException:
            # If the token was already expired or invalid, security.decode_refresh_token
            # raises a 401. We pass gracefully here so the user can still clear their cookie.
            pass

    # Unconditionally wipe the cookie from the user's browser
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        samesite="lax",
        secure=False  # Dev mode
    )
    
    # Returns an empty 204 No Content response
    return