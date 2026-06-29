import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db
from mysql_pool import create_pool, close_pool
from database import load_config
from services.metrics_loop import start as start_loop, stop as stop_loop
from services.websocket import connect_client, disconnect_client

from routers import config, metrics, databases, slow, processlist as pl, alerts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mysql_monitor")


class WSOriginFix:
    """Elimina el header Origin de las peticiones WebSocket
    para evitar el 403 de Starlette."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            scope["headers"] = [
                (k, v) for k, v in scope.get("headers", [])
                if k.lower() != b"origin"
            ]
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app):
    logger.info("Iniciando MySQL Monitor...")
    await init_db()
    settings = await load_config()
    await create_pool(settings.mysql)
    await start_loop()
    logger.info("MySQL Monitor listo")
    yield
    logger.info("Deteniendo MySQL Monitor...")
    await stop_loop()
    await close_pool()
    logger.info("MySQL Monitor detenido")


app = FastAPI(
    title="MySQL Monitor",
    description="Monitoreo en tiempo real para MySQL 5.7",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(config.router)
app.include_router(metrics.router)
app.include_router(databases.router)
app.include_router(slow.router)
app.include_router(pl.router)
app.include_router(alerts.router)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket):
    await connect_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await disconnect_client(websocket)


@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")


# ESTA ES LA LÍNEA QUE CAMBIA: envolver la app directamente
app = WSOriginFix(app)