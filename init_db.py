import asyncio
import asyncpg
from pathlib import Path
from config import DATABASE_URL

async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        schema = Path("schema.sql").read_text(encoding="utf-8")
        await conn.execute(schema)
        print("Base de datos inicializada correctamente.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
