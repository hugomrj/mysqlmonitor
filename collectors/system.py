import psutil
import logging

logger = logging.getLogger("mysql_monitor.collectors.system")


async def collect() -> dict:
    """Métricas del servidor: CPU, RAM, Disco.
    Fuente: psutil (no toca MySQL)."""
    try:
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": round(disk.free / (1024**3), 1),
        }
    except Exception as e:
        logger.error(f"Error leyendo métricas del sistema: {e}")
        return {}