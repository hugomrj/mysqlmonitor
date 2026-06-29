import asyncio
import logging
from datetime import datetime

from database import load_config
from mysql_pool import create_pool, is_connected
from collectors import system, status, processlist
from services import websocket, alerts

logger = logging.getLogger("mysql_monitor.loop")

# Tarea de fondo
_task: asyncio.Task | None = None

# Último snapshot de métricas (para enviar a nuevos clientes WS)
_last_snapshot: dict = {}


async def start():
    """Inicia el loop de recolección de métricas."""
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_loop())
    logger.info("Loop de métricas iniciado")


async def stop():
    """Detiene el loop."""
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
    """Devuelve el último snapshot para clientes que se conectan."""
    return _last_snapshot


async def _loop():
    """Loop principal. Lee config, conecta, recolecta, evalúa, envía."""
    while True:
        try:
            # Leer config actual (puede haber cambiado vía API)
            config = await load_config()

            # Asegurar conexión a MySQL
            await create_pool(config.mysql)
            connected = await is_connected()

            # Recolectar en paralelo lo que se puede
            system_data = await system.collect()
            status_data = await status.collect()

            # Processlist (solo si hay conexión)
            proc_data = await processlist.collect() if connected else []

            # Evaluar alertas
            slow_count = 0  # Se calcula en el endpoint de slow queries
            active_alerts = alerts.evaluate(
                system_data, status_data, config.alerts, slow_count
            )

            # Armar snapshot
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

            # Guardar para nuevos clientes
            _last_snapshot.update(snapshot)

            # Enviar a todos los conectados por WebSocket
            await websocket.broadcast(snapshot)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en ciclo de métricas: {e}", exc_info=True)

        # Esperar el intervalo configurado
        # Leer de nuevo por si cambió en caliente
        try:
            cfg = await load_config()
            interval = cfg.refresh_interval
        except Exception:
            interval = 2.0

        await asyncio.sleep(interval)