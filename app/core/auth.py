"""
Dependencias de autenticación FastAPI.
Compatible con el nuevo sistema de API keys de Supabase.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.supabase_client import get_auth_client

bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    def __init__(self, user_id: UUID, email: str, role: str, raw_payload: dict):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.raw = raw_payload


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        auth = get_auth_client()
        # Verificación remota — funciona con nuevo y legacy key system
        payload = await auth.verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub") or payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token sin user_id")

    return AuthenticatedUser(
        user_id=UUID(str(user_id)),
        email=payload.get("email", ""),
        role=payload.get("role", "authenticated"),
        raw_payload=payload,
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
