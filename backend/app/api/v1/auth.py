
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address

from ... import models, schemas
from ...database import get_db
from ...core.security import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_current_user
)
from ...core.config import settings
from ...services import users as user_service

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=schemas.TokenWithRefresh)
@limiter.limit("5/minute")  # Max 5 login attempts per minute per IP
def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    User login endpoint with refresh token support.

    Rate Limit: 5 requests per minute per IP (防止暴力破解)

    Returns:
        - access_token: Short-lived token (30 minutes)
        - refresh_token: Long-lived token (7 days) for automatic refresh
        - token_type: "bearer"
        - expires_in: Access token expiration in seconds

    Usage:
        1. Store both tokens securely (e.g., httpOnly cookies or localStorage)
        2. Use access_token for API calls
        3. When access_token expires, use refresh_token to get a new one via /auth/refresh
        4. When refresh_token expires (after 7 days), user needs to login again
    """
    user = user_service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token (short-lived)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )

    # Create refresh token (long-lived, stored in database)
    # Extract client info for security tracking
    device_info = request.headers.get("User-Agent", "Unknown")
    client_ip = request.client.host if request.client else None

    refresh_token_obj = create_refresh_token(
        db=db,
        user=user,
        device_info=device_info,
        ip_address=client_ip
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_obj.token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    }

@router.post("/refresh", response_model=schemas.TokenWithRefresh)
@limiter.limit("10/minute")  # Max 10 refresh requests per minute per IP
def refresh_access_token(
    request: Request,
    token_request: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    Rate Limit: 10 requests per minute per IP

    This endpoint allows users to get a new access token without re-login.
    The refresh token is verified and a new pair of tokens is issued.

    Security:
        - Old refresh token is revoked (one-time use)
        - New refresh token is issued
        - Validates token expiration and revocation status

    Returns:
        New access_token and refresh_token pair
    """
    # Verify the refresh token
    user = verify_refresh_token(db, token_request.refresh_token)

    # Revoke the old refresh token (one-time use for better security)
    revoke_refresh_token(db, token_request.refresh_token)

    # Create new access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )

    # Create new refresh token
    device_info = request.headers.get("User-Agent", "Unknown")
    client_ip = request.client.host if request.client else None

    new_refresh_token_obj = create_refresh_token(
        db=db,
        user=user,
        device_info=device_info,
        ip_address=client_ip
    )

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token_obj.token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout")
def logout(
    logout_request: schemas.LogoutRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Logout user by revoking the refresh token.

    This prevents the refresh token from being used to obtain new access tokens.
    The current access token will remain valid until it expires (max 30 minutes).

    Args:
        logout_request: Contains the refresh_token to revoke
        current_user: Current authenticated user (from access_token)

    Returns:
        Success message
    """
    revoked = revoke_refresh_token(db, logout_request.refresh_token)

    return {
        "message": "Successfully logged out",
        "revoked": revoked
    }


@router.post("/logout-all-devices")
def logout_all_devices(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Logout from all devices by revoking ALL refresh tokens for the current user.

    Use cases:
        - User suspects account compromise
        - User wants to force re-login on all devices
        - Password change (recommended)

    Security:
        - Revokes all active refresh tokens
        - User needs to re-login on all devices
        - Current access token still valid for max 30 minutes

    Returns:
        Number of tokens revoked
    """
    count = revoke_all_user_tokens(db, current_user.id)

    return {
        "message": f"Successfully logged out from all devices",
        "tokens_revoked": count
    }


@router.post("/register", response_model=schemas.UserRead)
@limiter.limit("3/hour")  # Max 3 registrations per hour per IP
def register_user(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    User registration endpoint.

    Rate Limit: 3 requests per hour per IP (防止大量註冊攻擊)
    """
    created = user_service.create_user(
        db,
        username=user.username,
        email=user.email,
        password=user.password,
        role=user.role or "assistant",
    )
    return created


@router.get("/me", response_model=schemas.UserRead)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user
