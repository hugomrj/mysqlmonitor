import asyncio
import logging
from datetime import datetime

from database import load_config
from mysql_pool import create_pool, is_connected
from collectors import system, status, processlist
from services import websocket, alerts

logger = logging.getLogger("mysql_monitor.loop")

_task: asyncio.Task | None = None
_last_snapshot: dict = {}

_slow_counter = 0
SLOW_CACHE_EVERY = 15  # Cada 15 ciclos (~30s a intervalo 2s)


async def start():
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_loop())
    logger.info("Loop de métricas iniciado")


async def stop():
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("Loop de métricas detenido")


def get_last_snapshot() -> dict:
    return _last_snapshot


async def _loop():
    while True:
        try:
            config = await load_config()
            await create_pool(config.mysql)
            connected = await is_connected()
            system_data = await system.collect()
            status_data = await status.collect()
            proc_data = await processlist.collect() if connected else []
            slow_count = 0
            active_alerts = alerts.evaluate(
                system_data, status_data, config.alerts, slow_count
            )
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "system": system_data,
                "mysql_status": status_data,
                "processlist": proc_data,
                "alerts": active_alerts,
                "config": {
                    "refresh_interval": config.refresh_interval,
                },
            }
            _last_snapshot.update(snapshot)
            await websocket.broadcast(snapshot)

            # ── Cachear consultas lentas (throttled) ──
            global _slow_counter
            _slow_counter += 1
            if _slow_counter >= SLOW_CACHE_EVERY:
                _slow_counter = 0
                try:
                    from services.slow_cache import cache_slow_queries
                    await cache_slow_queries(min_time=0.5)
                except Exception as e:
                    logger.error(f"Error cacheando slow queries: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en ciclo de métricas: {e}", exc_info=True)
        try:
            cfg = await load_config()
            interval = cfg.refresh_interval
        except Exception:
            interval = 2.0
        await asyncio.sleep(interval)
