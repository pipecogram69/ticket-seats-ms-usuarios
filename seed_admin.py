import asyncio
import asyncpg
from config import DATABASE_URL
from security import hash_password

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        """INSERT INTO usuario (nombre, apellido, email, password_hash, id_rol)
           VALUES ('Admin', 'Sistema', 'admin@ticketseats.com', $1,
                   (SELECT id_rol FROM rol WHERE nombre = 'ADMIN'))
           ON CONFLICT (email) DO NOTHING""",
        hash_password("Admin12345"))
    await conn.close()
    print("Admin creado: admin@ticketseats.com / Admin12345")

asyncio.run(main())
