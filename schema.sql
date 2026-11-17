CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS rol (
    id_rol SMALLSERIAL PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE,
    descripcion VARCHAR(150)
);

INSERT INTO rol (nombre, descripcion) VALUES
 ('ADMIN', 'Administrador de la plataforma'),
 ('ORGANIZADOR', 'Crea y gestiona eventos y localidades'),
 ('CLIENTE', 'Compra boletas'),
 ('VALIDADOR', 'Valida boletas en el ingreso al evento')
ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    telefono VARCHAR(20),
    password_hash VARCHAR(100) NOT NULL,
    id_rol SMALLINT NOT NULL REFERENCES rol(id_rol),
    estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVO'
        CHECK (estado IN ('ACTIVO','INACTIVO','BLOQUEADO')),
    intentos_fallidos SMALLINT NOT NULL DEFAULT 0,
    bloqueado_hasta TIMESTAMPTZ,
    ultimo_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usuario_rol ON usuario(id_rol);

CREATE TABLE IF NOT EXISTS auditoria_login (
    id_auditoria BIGSERIAL PRIMARY KEY,
    id_usuario UUID REFERENCES usuario(id_usuario),
    email VARCHAR(150) NOT NULL,
    exito BOOLEAN NOT NULL,
    ip VARCHAR(45),
    fecha TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auditoria_email_fecha
ON auditoria_login(email, fecha DESC);

CREATE TABLE IF NOT EXISTS reserva (
    id_reserva UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario UUID NOT NULL REFERENCES usuario(id_usuario),
    id_evento UUID NOT NULL,
    evento_nombre VARCHAR(150) NOT NULL,
    evento_fecha TIMESTAMPTZ NOT NULL,
    venue VARCHAR(120),
    ciudad VARCHAR(80),
    imagen_url VARCHAR(255),
    subtotal NUMERIC(12,2) NOT NULL,
    cargo_servicio NUMERIC(12,2) NOT NULL DEFAULT 0,
    total NUMERIC(12,2) NOT NULL,
    estado VARCHAR(10) NOT NULL DEFAULT 'ACTIVA'
        CHECK (estado IN ('ACTIVA','CONVERTIDA','EXPIRADA','CANCELADA')),
    expira_en TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reserva_usuario
ON reserva(id_usuario, created_at DESC);

CREATE TABLE IF NOT EXISTS reserva_detalle (
    id_detalle BIGSERIAL PRIMARY KEY,
    id_reserva UUID NOT NULL REFERENCES reserva(id_reserva) ON DELETE CASCADE,
    id_boleta BIGINT NOT NULL,
    localidad VARCHAR(60) NOT NULL,
    fila VARCHAR(5) NOT NULL,
    asiento INT NOT NULL,
    precio NUMERIC(12,2) NOT NULL
);
