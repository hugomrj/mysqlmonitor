import logging
from datetime import datetime
from config import AlertThresholds

logger = logging.getLogger("mysql_monitor.alerts")

# Alertas activas (en memoria, se recalculan cada ciclo)
_active_alerts: list[dict] = []


def evaluate(
    system: dict,
    status: dict,
    thresholds: AlertThresholds,
    slow_count: int,
) -> list[dict]:
    """Evalúa métricas contra umbrales.
    Devuelve la lista de alertas activas."""
    global _active_alerts
    new_alerts = []

    # Solo evaluar si hay datos
    if not system or "error" in status:
        return new_alerts

    # Disco
    if system.get("disk_percent", 0) >= thresholds.disk_percent:
        new_alerts.append({
            "type": "critical",
            "icon": "bi-hdd-fill",
            "title": f"Disco al {system['disk_percent']}%",
            "desc": f"Quedan {system.get('disk_free_gb', 0)} GB libres de {system.get('disk_total_gb', 0)} GB.",
            "source": "psutil.disk_usage()",
            "time": datetime.now().isoformat(),
        })

    # CPU
    if system.get("cpu_percent", 0) >= thresholds.cpu_percent:
        new_alerts.append({
            "type": "critical",
            "icon": "bi-cpu-fill",
            "title": f"CPU al {system['cpu_percent']}%",
            "desc": "El procesador está al límite. Revisa procesos pesados.",
            "source": "psutil.cpu_percent()",
            "time": datetime.now().isoformat(),
        })

    # RAM
    if system.get("ram_percent", 0) >= thresholds.ram_percent:
        new_alerts.append({
            "type": "critical",
            "icon": "bi-memory",
            "title": f"RAM al {system['ram_percent']}%",
            "desc": f"Usando {system.get('ram_used_gb', 0)} GB de {system.get('ram_total_gb', 0)} GB.",
            "source": "psutil.virtual_memory()",
            "time": datetime.now().isoformat(),
        })

    # Conexiones
    if status.get("mysql_connected"):
        max_conn = status.get("max_connections", 500)
        current = status.get("threads_connected", 0)
        pct = (current / max_conn * 100) if max_conn > 0 else 0

        if pct >= thresholds.connections_percent:
            new_alerts.append({
                "type": "warning",
                "icon": "bi-people-fill",
                "title": f"Conexiones al {pct:.0f}% del límite",
                "desc": f"{current} conexiones activas de {max_conn} permitidas. Máx histórico: {status.get('max_used_connections', 0)}.",
                "source": "SHOW GLOBAL STATUS",
                "time": datetime.now().isoformat(),
            })

    # Consultas lentas
    if slow_count >= thresholds.max_slow_per_hour:
        new_alerts.append({
            "type": "warning",
            "icon": "bi-hourglass-split",
            "title": f"{slow_count} consultas lentas recientes",
            "desc": f"Se superó el umbral de {thresholds.max_slow_per_hour}. Revisa el Slow Query Log.",
            "source": "mysql.slow_log",
            "time": datetime.now().isoformat(),
        })

    _active_alerts = new_alerts
    return new_alerts


def get_active() -> list[dict]:
    """Devuelve las alertas actuales sin reevaluar."""
    return _active_alerts