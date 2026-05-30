"""
Cliente Supabase centralizado para ARCA.
Compatible con el nuevo sistema de API keys de Supabase (sb_publishable_ / sb_secret_)
y con el sistema legacy (anon / service_role JWT).

Los tokens de usuario (Auth) siguen siendo JWTs — se verifican contra el JWKS
del proyecto en lugar del JWT secret hardcodeado.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth — verificación de tokens de usuario
# ---------------------------------------------------------------------------

class SupabaseAuthClient:
    """
    Verifica tokens JWT emitidos por Supabase Auth.

    Supabase nuevo sistema: los tokens de USUARIO siguen siendo JWTs firmados
    con la clave del proyecto. Se verifican via el endpoint /auth/v1/user
    (más robusto que verificar el JWT localmente, funciona con ambos sistemas).
    """

    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        # Publishable key = la nueva "anon key" (sb_publishable_... o el JWT anon legacy)
        self.publishable_key = settings.SUPABASE_ANON_KEY
        # JWT secret — solo necesario si usas verificación local (sistema legacy)
        self.jwt_secret = settings.SUPABASE_JWT_SECRET

    async def verify_token(self, token: str) -> dict:
        """
        Verifica un token de usuario contra Supabase Auth.
        Funciona con ambos sistemas (nuevo y legacy).
        Retorna el payload del usuario si es válido.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": self.publishable_key,
                },
                timeout=10,
            )
        if resp.status_code == 200:
            data = resp.json()
            # Normalizar respuesta al formato que espera el resto del backend
            return {
                "sub": data.get("id"),
                "email": data.get("email"),
                "role": data.get("role", "authenticated"),
                **data,
            }
        elif resp.status_code == 401:
            raise ValueError("Token inválido o expirado")
        else:
            raise ValueError(f"Error verificando token: {resp.status_code}")

    def verify_token_local(self, token: str) -> dict:
        """
        Verificación local del JWT (más rápida, no hace request HTTP).
        Solo funciona si tienes SUPABASE_JWT_SECRET configurado.
        Útil para reducir latencia en endpoints de alta frecuencia.
        """
        if not self.jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET no configurado")
        try:
            import jwt as pyjwt
            return pyjwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except Exception as e:
            raise ValueError(f"Token inválido: {e}")


# ---------------------------------------------------------------------------
# Storage — PDFs de certificados
# ---------------------------------------------------------------------------

class SupabaseStorageClient:
    """
    Maneja PDFs de certificados en Supabase Storage.
    Bucket: 'certificates' (público para lectura, privado para escritura).

    Usa el service/secret key para operaciones de escritura.
    """

    BUCKET = "certificates"

    def __init__(self):
        self.base_url = f"{settings.SUPABASE_URL}/storage/v1"
        # service_key = sb_secret_... (nuevo) o service_role JWT (legacy)
        self.service_key = settings.SUPABASE_SERVICE_KEY
        self.publishable_key = settings.SUPABASE_ANON_KEY

    def _auth_headers(self) -> dict:
        """Headers con service key — para operaciones de escritura."""
        return {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }

    def _read_headers(self) -> dict:
        """Headers con publishable key — para operaciones de lectura."""
        return {
            "Authorization": f"Bearer {self.publishable_key}",
            "apikey": self.publishable_key,
        }

    async def upload_pdf(self, cert_id: str, pdf_bytes: bytes, subject_name: str) -> str:
        path = f"{cert_id}.pdf"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/object/{self.BUCKET}/{path}",
                headers={
                    **self._auth_headers(),
                    "Content-Type": "application/pdf",
                    "x-upsert": "true",
                },
                content=pdf_bytes,
                timeout=30,
            )
        if resp.status_code not in (200, 201):
            logger.error(f"Storage upload failed: {resp.status_code} — {resp.text}")
            raise RuntimeError(f"Error subiendo PDF: {resp.status_code}")
        return self.get_public_url(path)

    def get_public_url(self, path: str) -> str:
        return f"{settings.SUPABASE_URL}/storage/v1/object/public/{self.BUCKET}/{path}"

    async def get_signed_url(self, cert_id: str, expires_in: int = 3600) -> str:
        path = f"{cert_id}.pdf"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/object/sign/{self.BUCKET}/{path}",
                headers=self._auth_headers(),
                json={"expiresIn": expires_in},
                timeout=10,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Error generando URL firmada: {resp.status_code}")
        token = resp.json().get("signedURL", "")
        return f"{settings.SUPABASE_URL}/storage/v1{token}"

    async def delete_pdf(self, cert_id: str) -> bool:
        path = f"{cert_id}.pdf"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.base_url}/object/{self.BUCKET}/{path}",
                headers=self._auth_headers(),
                timeout=10,
            )
        return resp.status_code in (200, 204)

    async def ensure_bucket_exists(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/bucket/{self.BUCKET}",
                headers=self._auth_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"Bucket '{self.BUCKET}' ya existe")
                return
            resp = await client.post(
                f"{self.base_url}/bucket",
                headers=self._auth_headers(),
                json={
                    "id": self.BUCKET,
                    "name": self.BUCKET,
                    "public": True,
                    "fileSizeLimit": 5242880,
                    "allowedMimeTypes": ["application/pdf"],
                },
                timeout=10,
            )
        if resp.status_code in (200, 201):
            logger.info(f"Bucket '{self.BUCKET}' creado")
        else:
            logger.error(f"Error creando bucket: {resp.status_code} — {resp.text}")


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_auth_client() -> SupabaseAuthClient:
    return SupabaseAuthClient()


@lru_cache(maxsize=1)
def get_storage_client() -> SupabaseStorageClient:
    return SupabaseStorageClient()
