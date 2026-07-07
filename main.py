import asyncio
import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


from config import AppSettings
from routers import config as cfg_router, metrics, databases, slow, processlist, alerts, binlog, queries, audit
from services.websocket import connected_clients as metrics_clients
from services.binlog_stream import binlog_service
from database import init_db, load_config, init_binlog_tables
from mysql_pool import create_pool, close_pool
from database import init_slow_queries_table, init_queries_cache_table



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("main")


class _RawWSAdapter:
    def __init__(self, send):
        self._send = send

    async def send_json(self, data: dict):
        await self._send({"type": "websocket.send", "text": json.dumps(data, ensure_ascii=False)})


class WSBypass:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            path = scope.get("path", "")
            if path == "/ws/metrics":
                await self._ws_metrics(receive, send)
                return
            if path == "/ws/binlog":
                await self._ws_binlog(receive, send)
                return
        await self.app(scope, receive, send)

    async def _ws_metrics(self, receive, send):
        await send({"type": "websocket.accept"})
        adapter = _RawWSAdapter(send)
        metrics_clients.append(adapter)
        try:
            while True:
                msg = await receive()
                if msg["type"] == "websocket.disconnect":
                    break
        finally:
            if adapter in metrics_clients:
                metrics_clients.remove(adapter)




    async def _ws_binlog(self, receive, send):
        await send({"type": "websocket.accept"})
        binlog_service.add_client(send)

        for evt in reversed(binlog_service.get_recent_events(50)):
            row_preview = None
            try:
                import json as _json
                rows = _json.loads(evt.get("row_data", "[]"))
                if rows:
                    row_preview = rows[0]
            except Exception:
                pass

            payload = {
                "type": "binlog_event",
                "data": {
                    "event_time": evt["event_time"],
                    "event_type": evt["event_type"],
                    "schema": evt["schema"],
                    "table": evt["table"],
                    "affected_rows": evt["affected_rows"],
                    "log_file": evt["log_file"],
                    "log_pos": evt["log_pos"],
                    "row_preview": row_preview,
                },
            }
            try:
                await send({"type": "websocket.send", "text": json.dumps(payload)})
            except Exception:
                break
        try:
            while True:
                msg = await receive()
                if msg["type"] == "websocket.disconnect":
                    break
        finally:
            binlog_service.remove_client(send)








@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando MySQL Monitor...")
    await init_db()
    await init_binlog_tables()
    await init_slow_queries_table()
    await init_queries_cache_table()

    cfg = await load_config()
    await create_pool(cfg.mysql)

    from services.metrics_loop import start as start_metrics_loop
    asyncio.create_task(start_metrics_loop())

    if cfg.binlog_enabled and cfg.mysql.password:
        mysql_dict = cfg.mysql.model_dump()
        await binlog_service.start(mysql_dict)
        if not binlog_service.is_running:
            logger.info("ℹ Binlog no pudo iniciar - configura contraseña en la UI")
    else:
        logger.info("Binlog pendiente - configura conexión en la UI")

        if not binlog_service.is_running:
            logger.info("ℹ Binlog deshabilitado - el resto del monitor funciona normal")
   

    logger.info("MySQL Monitor listo")
    yield

    logger.info("Deteniendo...")
    await binlog_service.stop()
    await close_pool()


app = FastAPI(title="MySQL Monitor", lifespan=lifespan)
app.add_middleware(WSBypass)

app.include_router(cfg_router.router)
app.include_router(metrics.router)
app.include_router(databases.router)
app.include_router(slow.router)
app.include_router(processlist.router)
app.include_router(alerts.router)
app.include_router(binlog.router)
app.include_router(queries.router)
app.include_router(audit.router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)