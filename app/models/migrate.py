import asyncio
from app.db.session import engine
from app.models.models import Base

async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Listo')

asyncio.run(create())