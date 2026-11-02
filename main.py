from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import asyncpg
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import db
from config import MAX_INTENTOS, BLOQUEO_MIN
from schemas import (CrearUsuario, LoginIn, RegistroCliente, TokenOut, UsuarioOut)
from security import create_token, decode_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="MS Usuarios - Autenticación", lifespan=lifespan)
bearer = HTTPBearer()


async def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        payload = decode_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    return payload


def requiere_roles(*roles: str):
    async def checker(user: dict = Depends(usuario_actual)):
        if user["rol"] not in roles:
            raise HTTPException(403, "No tienes permisos para esta acción")
        return user
    return checker


async def _insertar_usuario(data: RegistroCliente, rol: str) -> dict:
    sql = """
        INSERT INTO usuario (nombre, apellido, email, telefono, password_hash, id_rol)
        VALUES ($1, $2, lower($3), $4, $5, (SELECT id_rol FROM rol WHERE nombre = $6))
        RETURNING id_usuario::text, nombre, apellido, email, telefono, estado
    """
    try:
        async with db.get_pool().acquire() as conn:
            row = await conn.fetchrow(
                sql, data.nombre, data.apellido, data.email, data.telefono,
                hash_password(data.password), rol,
            )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "Ya existe un usuario con ese correo")
    return {**dict(row), "rol": rol}


@app.post("/auth/registro", response_model=UsuarioOut, status_code=201)
async def registro_publico(data: RegistroCliente):
    return await _insertar_usuario(data, "CLIENTE")


@app.post("/usuarios", response_model=UsuarioOut, status_code=201)
async def crear_usuario(data: CrearUsuario, _=Depends(requiere_roles("ADMIN"))):
    return await _insertar_usuario(data, data.rol.value)


@app.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn, request: Request):
    email = data.email.lower()
    ip = request.client.host if request.client else None
    ahora = datetime.now(timezone.utc)

    async with db.get_pool().acquire() as conn:
        u = await conn.fetchrow(
            """SELECT u.id_usuario, u.password_hash, u.estado, u.intentos_fallidos,
                      u.bloqueado_hasta, r.nombre AS rol
               FROM usuario u JOIN rol r ON r.id_rol = u.id_rol
               WHERE u.email = $1""", email)

        async def auditar(ok: bool, uid=None):
            await conn.execute(
                "INSERT INTO auditoria_login (id_usuario, email, exito, ip) VALUES ($1,$2,$3,$4)",
                uid, email, ok, ip)

        if not u:
            await auditar(False)
            raise HTTPException(401, "Credenciales incorrectas")

        if u["estado"] in ("INACTIVO", "BLOQUEADO"):
            await auditar(False, u["id_usuario"])
            raise HTTPException(403, "Usuario inactivo")

        if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
            await auditar(False, u["id_usuario"])
            raise HTTPException(status.HTTP_423_LOCKED, "Cuenta bloqueada temporalmente, intenta más tarde")

        if not verify_password(data.password, u["password_hash"]):
            intentos = u["intentos_fallidos"] + 1
            bloqueo = ahora + timedelta(minutes=BLOQUEO_MIN) if intentos >= MAX_INTENTOS else None
            await conn.execute(
                """UPDATE usuario SET intentos_fallidos = $1, bloqueado_hasta = $2, updated_at = now()
                   WHERE id_usuario = $3""",
                0 if bloqueo else intentos, bloqueo, u["id_usuario"])
            await auditar(False, u["id_usuario"])
            raise HTTPException(401, "Credenciales incorrectas")

        await conn.execute(
            """UPDATE usuario SET intentos_fallidos = 0, bloqueado_hasta = NULL,
                      ultimo_login = now(), updated_at = now()
               WHERE id_usuario = $1""", u["id_usuario"])
        await auditar(True, u["id_usuario"])

    token = create_token(str(u["id_usuario"]), u["rol"])
    return TokenOut(access_token=token, rol=u["rol"])


@app.get("/auth/me", response_model=UsuarioOut)
async def me(user: dict = Depends(usuario_actual)):
    async with db.get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.id_usuario::text, u.nombre, u.apellido, u.email, u.telefono,
                      u.estado, r.nombre AS rol
               FROM usuario u JOIN rol r ON r.id_rol = u.id_rol
               WHERE u.id_usuario = $1::uuid""", user["sub"])
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    return dict(row)


# ---------- Frontend ----------
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


@app.get("/", include_in_schema=False)
async def inicio():
    return RedirectResponse("/static/login.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Gestión de usuarios (ADMIN) ----------
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from schemas import RolEnum


class CambioRol(BaseModel):
    rol: RolEnum


class CambioEstado(BaseModel):
    estado: Literal["ACTIVO", "INACTIVO", "BLOQUEADO"]


class CambioPassword(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=72)


_SEL_USUARIO = """SELECT u.id_usuario::text, u.nombre, u.apellido, u.email, u.telefono,
                         u.estado, r.nombre AS rol
                  FROM usuario u JOIN rol r ON r.id_rol = u.id_rol"""


@app.get("/usuarios", response_model=list[UsuarioOut])
async def listar_usuarios(rol: str | None = None, estado: str | None = None,
                          q: str | None = None, _=Depends(requiere_roles("ADMIN"))):
    sql = _SEL_USUARIO + """
        WHERE ($1::text IS NULL OR r.nombre = $1)
          AND ($2::text IS NULL OR u.estado = $2)
          AND ($3::text IS NULL OR u.email ILIKE '%' || $3 || '%'
               OR u.nombre ILIKE '%' || $3 || '%' OR u.apellido ILIKE '%' || $3 || '%')
        ORDER BY u.created_at DESC LIMIT 200"""
    async with db.get_pool().acquire() as conn:
        rows = await conn.fetch(sql, rol, estado, q)
    return [dict(r) for r in rows]


@app.patch("/usuarios/{id_usuario}/rol", response_model=UsuarioOut)
async def cambiar_rol(id_usuario: UUID, data: CambioRol, admin=Depends(requiere_roles("ADMIN"))):
    if str(id_usuario) == admin["sub"]:
        raise HTTPException(400, "No puedes cambiar tu propio rol")
    async with db.get_pool().acquire() as conn:
        ok = await conn.fetchval(
            """UPDATE usuario SET id_rol = (SELECT id_rol FROM rol WHERE nombre = $1), updated_at = now()
               WHERE id_usuario = $2 RETURNING 1""", data.rol.value, id_usuario)
        if not ok:
            raise HTTPException(404, "Usuario no encontrado")
        row = await conn.fetchrow(_SEL_USUARIO + " WHERE u.id_usuario = $1", id_usuario)
    return dict(row)


@app.patch("/usuarios/{id_usuario}/estado", response_model=UsuarioOut)
async def cambiar_estado(id_usuario: UUID, data: CambioEstado, admin=Depends(requiere_roles("ADMIN"))):
    if str(id_usuario) == admin["sub"]:
        raise HTTPException(400, "No puedes cambiar tu propio estado")
    async with db.get_pool().acquire() as conn:
        ok = await conn.fetchval(
            """UPDATE usuario
               SET estado = $1,
                   intentos_fallidos = CASE WHEN $1 = 'ACTIVO' THEN 0 ELSE intentos_fallidos END,
                   bloqueado_hasta   = CASE WHEN $1 = 'ACTIVO' THEN NULL ELSE bloqueado_hasta END,
                   updated_at = now()
               WHERE id_usuario = $2 RETURNING 1""", data.estado, id_usuario)
        if not ok:
            raise HTTPException(404, "Usuario no encontrado")
        row = await conn.fetchrow(_SEL_USUARIO + " WHERE u.id_usuario = $1", id_usuario)
    return dict(row)


@app.patch("/auth/password")
async def cambiar_password(data: CambioPassword, user: dict = Depends(usuario_actual)):
    async with db.get_pool().acquire() as conn:
        actual = await conn.fetchval(
            "SELECT password_hash FROM usuario WHERE id_usuario = $1::uuid", user["sub"])
        if not actual or not verify_password(data.password_actual, actual):
            raise HTTPException(400, "La contraseña actual es incorrecta")
        await conn.execute(
            "UPDATE usuario SET password_hash = $1, updated_at = now() WHERE id_usuario = $2::uuid",
            hash_password(data.password_nueva), user["sub"])
    return {"ok": True}
