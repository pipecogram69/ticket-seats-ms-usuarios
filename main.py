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

        if u["estado"] == "INACTIVO":
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
