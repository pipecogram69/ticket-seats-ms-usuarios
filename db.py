import asyncpg
from config import DATABASE_URL

pool: asyncpg.Pool | None = None

async def init_pool():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

async def close_pool():
    if pool:
        await pool.close()

def get_pool() -> asyncpg.Pool:
    return pool
