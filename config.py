import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/ticketseats_auth")
JWT_SECRET = os.getenv("JWT_SECRET", "cambia-esto-en-produccion")
JWT_ALG = "HS256"
JWT_EXP_MIN = 60
MAX_INTENTOS = 5
BLOQUEO_MIN = 15
