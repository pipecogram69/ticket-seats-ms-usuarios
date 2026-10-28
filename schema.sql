CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE rol (
    id_rol      SMALLSERIAL PRIMARY KEY,
    nombre      VARCHAR(30)  NOT NULL UNIQUE,
    descripcion VARCHAR(150)
);

INSERT INTO rol (nombre, descripcion) VALUES
 ('ADMIN',       'Administrador de la plataforma'),
 ('ORGANIZADOR', 'Crea y gestiona eventos y localidades'),
 ('CLIENTE',     'Compra boletas'),
 ('VALIDADOR',   'Valida boletas en el ingreso al evento');

CREATE TABLE usuario (
    id_usuario        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre            VARCHAR(80)  NOT NULL,
    apellido          VARCHAR(80)  NOT NULL,
    email             VARCHAR(150) NOT NULL UNIQUE,
    telefono          VARCHAR(20),
    password_hash     VARCHAR(100) NOT NULL,
    id_rol            SMALLINT NOT NULL REFERENCES rol(id_rol),
    estado            VARCHAR(10) NOT NULL DEFAULT 'ACTIVO'
                      CHECK (estado IN ('ACTIVO','INACTIVO','BLOQUEADO')),
    intentos_fallidos SMALLINT NOT NULL DEFAULT 0,
    bloqueado_hasta   TIMESTAMPTZ,
    ultimo_login      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_usuario_rol ON usuario(id_rol);

CREATE TABLE auditoria_login (
    id_auditoria BIGSERIAL PRIMARY KEY,
    id_usuario   UUID REFERENCES usuario(id_usuario),
    email        VARCHAR(150) NOT NULL,
    exito        BOOLEAN NOT NULL,
    ip           VARCHAR(45),
    fecha        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_auditoria_email_fecha ON auditoria_login(email, fecha DESC);
