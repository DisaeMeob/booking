import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from src.init import redis_manager
from src.middleware import middleware_logger
from src.api.hotels import router as router_hotels
from src.api.auth import router as auth_router
from src.api.rooms import router as rooms_router
from src.api.bookings import router as bookings_router
from src.api.facilities import router as facilities_router
from src.api.images import router as images_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте приложении
    await redis_manager.connect()
    print(1)
    yield
    # При выключении приложения
    await redis_manager.close()
    print(2)


app = FastAPI(lifespan=lifespan)

app.include_router(auth_router)
app.include_router(router_hotels)
app.include_router(rooms_router)
app.include_router(facilities_router)
app.include_router(bookings_router)
app.include_router(images_router)

app.middleware('http')(middleware_logger)

if __name__ == '__main__':
    uvicorn.run('src.main:app', reload=True)

