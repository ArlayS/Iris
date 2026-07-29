import asyncio

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import logging
from config import CORS_ORIGINS
from database import client, initialize_indexes
from routers import admin, auth, members, profiles, resources, staff, tickets, animateur_projects, animateur_calendar
from services.storage_service import init_storage


app = FastAPI(title="Iris API")


@app.get("/api/")
async def root() -> dict[str, str]:
    return {"message": "Iris API opérationnelle"}


app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(resources.router, prefix="/api")
app.include_router(members.router, prefix="/api")
app.include_router(tickets.router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(animateur_projects.router, prefix="/api")
app.include_router(animateur_calendar.router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup() -> None:
    await initialize_indexes()
    try:
        await asyncio.to_thread(init_storage)
    except Exception as error:
        logger.warning("Stockage de ressources indisponible au démarrage : %s", error)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
