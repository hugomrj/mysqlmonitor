import psutil
import os
import logging

logger = logging.getLogger("mysql_monitor.collectors.system")


async def collect() -> dict:
    """Métricas del servidor: CPU, RAM, Disco."""
    try:
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        cpu_cores = psutil.cpu_count() or 1

        # os.getloadavg() disponible en Linux/macOS
        try:
            load1, load5, load15 = os.getloadavg()
        except (OSError, AttributeError):
            load1 = load5 = load15 = 0.0

        ram_free_gb = round((mem.total - mem.used) / (1024**3), 1)
        disk_free_gb = round(disk.free / (1024**3), 1)

        return {
            "cpu_percent": cpu,
            "cpu_cores": cpu_cores,
            "load_avg_1m": round(load1, 2),
            "load_avg_5m": round(load5, 2),
            "load_avg_15m": round(load15, 2),
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "ram_free_gb": ram_free_gb,
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_free_gb": disk_free_gb,
        }
    except Exception as e:
        logger.error(f"Error leyendo métricas del sistema: {e}")
        return {}