from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from config import JWT_SECRET, JWT_ALG, JWT_EXP_MIN

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, rol: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "rol": rol, "iat": now, "exp": now + timedelta(minutes=JWT_EXP_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
