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
    tarea = asyncio.create_task(expirar_reservas())
    yield
    tarea.cancel()
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


@app.middleware("http")
async def sin_cache_estaticos(request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- Reservas ----------
import asyncio
from decimal import Decimal

import httpx

from config import EVENTOS_URL


class BoletaVersion(BaseModel):
    id_boleta: int
    version: int


class ReservaIn(BaseModel):
    id_evento: UUID
    boletas: list[BoletaVersion] = Field(min_length=1, max_length=20)


class NotificarIn(BaseModel):
    id_evento: UUID
    estado: Literal["CONVERTIDA", "CANCELADA"]


async def ctx(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    payload = await usuario_actual(cred)
    payload["token"] = cred.credentials          # se reenvía al MS de eventos
    return payload


def con_roles(*roles: str):
    async def checker(user: dict = Depends(ctx)):
        if user["rol"] not in roles:
            raise HTTPException(403, "No tienes permisos para esta acción")
        return user
    return checker


async def llamar_eventos(metodo: str, ruta: str, token: str | None = None, cuerpo: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.request(metodo, EVENTOS_URL + ruta, headers=headers, json=cuerpo)
    except httpx.HTTPError:
        raise HTTPException(502, "No se pudo contactar al servicio de eventos")
    if r.status_code >= 400:
        try:
            detalle = r.json().get("detail")
        except Exception:
            detalle = None
        if not isinstance(detalle, str):
            detalle = "Error en el servicio de eventos"
        raise HTTPException(r.status_code if r.status_code in (401, 403, 404, 409, 422) else 502, detalle)
    return r.json()


def a_fecha(texto: str) -> datetime:
    dt = datetime.fromisoformat(texto)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def expirar_reservas():
    while True:
        try:
            async with db.get_pool().acquire() as conn:
                await conn.execute(
                    """UPDATE reserva SET estado = 'EXPIRADA', updated_at = now()
                       WHERE estado = 'ACTIVA' AND expira_en < now()""")
        except Exception as e:
            print("[reservas] expiración:", e)
        await asyncio.sleep(60)


@app.post("/reservas", status_code=201)
async def crear_reserva(data: ReservaIn, user=Depends(con_roles("CLIENTE", "ADMIN"))):
    res = await llamar_eventos("POST", "/inventario/reservar", user["token"], {
        "id_evento": str(data.id_evento),
        "boletas": [b.model_dump() for b in data.boletas]})
    ev = await llamar_eventos("GET", f"/eventos/{data.id_evento}")
    async with db.get_pool().acquire() as conn:
        async with conn.transaction():
            id_reserva = await conn.fetchval(
                """INSERT INTO reserva (id_usuario, id_evento, evento_nombre, evento_fecha, venue, ciudad,
                          imagen_url, subtotal, cargo_servicio, total, expira_en)
                   VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING id_reserva""",
                user["sub"], data.id_evento, ev["nombre"], a_fecha(ev["fecha_inicio"]), ev.get("venue"),
                ev.get("ciudad"), ev.get("imagen_url"), Decimal(str(res["subtotal"])),
                Decimal(str(res["cargo_servicio"])), Decimal(str(res["total"])), a_fecha(res["expira_en"]))
            await conn.executemany(
                """INSERT INTO reserva_detalle (id_reserva, id_boleta, localidad, fila, asiento, precio)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                [(id_reserva, r["id_boleta"], r["localidad"], r["fila"], r["asiento"], Decimal(str(r["precio"])))
                 for r in res["reservadas"]])
    return {**res, "id_reserva": str(id_reserva)}


@app.get("/reservas/mias")
async def mis_reservas(user=Depends(con_roles("CLIENTE", "ADMIN"))):
    async with db.get_pool().acquire() as conn:
        rs = await conn.fetch(
            """SELECT id_reserva, id_evento, evento_nombre, evento_fecha, venue, ciudad, imagen_url,
                      subtotal, cargo_servicio, total, expira_en, created_at,
                      CASE WHEN estado = 'ACTIVA' AND expira_en < now() THEN 'EXPIRADA' ELSE estado END AS estado
               FROM reserva WHERE id_usuario = $1::uuid ORDER BY created_at DESC LIMIT 50""", user["sub"])
        ds = await conn.fetch(
            """SELECT id_reserva, id_boleta, localidad, fila, asiento, precio
               FROM reserva_detalle WHERE id_reserva = ANY($1::uuid[]) ORDER BY id_detalle""",
            [r["id_reserva"] for r in rs])
    por: dict = {}
    for d in ds:
        por.setdefault(d["id_reserva"], []).append(dict(d))
    return [{**dict(r), "detalle": por.get(r["id_reserva"], [])} for r in rs]


@app.post("/reservas/notificar")
async def notificar(data: NotificarIn, user=Depends(con_roles("CLIENTE", "ADMIN"))):
    """Lo llama el MS de órdenes cuando una reserva se paga (CONVERTIDA) o se cancela."""
    async with db.get_pool().acquire() as conn:
        n = await conn.fetchval(
            """WITH x AS (UPDATE reserva SET estado = $3, updated_at = now()
                          WHERE id_usuario = $1::uuid AND id_evento = $2 AND estado = 'ACTIVA' RETURNING 1)
               SELECT count(*) FROM x""", user["sub"], data.id_evento, data.estado)
    return {"actualizadas": n}


@app.post("/reservas/{id_reserva}/cancelar")
async def cancelar_reserva(id_reserva: UUID, user=Depends(con_roles("CLIENTE", "ADMIN"))):
    async with db.get_pool().acquire() as conn:
        r = await conn.fetchrow(
            "SELECT id_usuario::text AS u, id_evento, estado FROM reserva WHERE id_reserva = $1", id_reserva)
        if not r:
            raise HTTPException(404, "Reserva no encontrada")
        if r["u"] != user["sub"]:
            raise HTTPException(403, "Esta reserva no es tuya")
        if r["estado"] != "ACTIVA":
            raise HTTPException(409, f"La reserva está {r['estado']}")
        ids = [x["id_boleta"] for x in await conn.fetch(
            "SELECT id_boleta FROM reserva_detalle WHERE id_reserva = $1", id_reserva)]
    try:       # si ya expiró, el MS de eventos ya liberó los asientos
        await llamar_eventos("POST", "/inventario/liberar", user["token"],
                             {"id_evento": str(r["id_evento"]), "ids": ids})
    except HTTPException:
        pass
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE reserva SET estado = 'CANCELADA', updated_at = now() WHERE id_reserva = $1 AND estado = 'ACTIVA'",
            id_reserva)
    return {"estado": "CANCELADA"}


# ---------- Configuración pública para el navegador ----------
import json
import os

from fastapi.responses import Response


@app.get("/config.js", include_in_schema=False)
async def config_js():
    cfg = {"eventos": os.getenv("EVENTOS_PUBLIC_URL", ""), "ordenes": os.getenv("ORDENES_PUBLIC_URL", "")}
    return Response("window.TS_CONFIG = " + json.dumps(cfg) + ";",
                    media_type="application/javascript", headers={"Cache-Control": "no-store"})
