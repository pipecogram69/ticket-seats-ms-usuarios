from enum import Enum
from pydantic import BaseModel, EmailStr, Field

class RolEnum(str, Enum):
    ADMIN = "ADMIN"
    ORGANIZADOR = "ORGANIZADOR"
    CLIENTE = "CLIENTE"
    VALIDADOR = "VALIDADOR"

class RegistroCliente(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    apellido: str = Field(min_length=2, max_length=80)
    email: EmailStr
    telefono: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=72)

class CrearUsuario(RegistroCliente):
    rol: RolEnum

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str

class UsuarioOut(BaseModel):
    id_usuario: str
    nombre: str
    apellido: str
    email: str
    telefono: str | None
    rol: str
    estado: str
