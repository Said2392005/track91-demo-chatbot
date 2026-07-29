from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_auth_service
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, auth_service: AuthService = Depends(get_auth_service)) -> LoginResponse:
    try:
        token, expires_in = await auth_service.login(body.email, body.password)
    except AuthError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return LoginResponse(access_token=token, expires_in=expires_in)
