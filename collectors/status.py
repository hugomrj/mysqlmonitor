import logging

logger = logging.getLogger("mysql_monitor.collectors.status")


async def _get_pool():
    try:
        from mysql_pool import get_pool
        return await get_pool()
    except Exception as e:
        logger.error(f"No se pudo obtener pool: {e}")
        return None


def _format_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


async def collect() -> dict:
    pool = await _get_pool()
    if pool is None:
        return {"error": "Sin conexión a MySQL", "mysql_connected": False}

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW GLOBAL STATUS")
                rows = await cur.fetchall()

                status = {row[0]: row[1] for row in rows}

                await cur.execute("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
                var_row = await cur.fetchone()
                max_conn = int(var_row[1]) if var_row else 500

                queries = int(status.get("Queries", 0))
                uptime = int(status.get("Uptime", 0))
                threads_connected = int(status.get("Threads_connected", 0))
                threads_running = int(status.get("Threads_running", 0))
                max_used = int(status.get("Max_used_connections", 0))
                connections = int(status.get("Connections", 0))
                aborted_connects = int(status.get("Aborted_connects", 0))
                aborted_clients = int(status.get("Aborted_clients", 0))
                threads_cached = int(status.get("Threads_cached", 0))

                bp_total = int(status.get("Innodb_buffer_pool_pages_total", 0))
                bp_data = int(status.get("Innodb_buffer_pool_pages_data", 0))
                bp_reads_req = int(status.get("Innodb_buffer_pool_read_requests", 0))
                bp_reads = int(status.get("Innodb_buffer_pool_reads", 0))
                pages_read = int(status.get("Innodb_pages_read", 0))
                pages_created = int(status.get("Innodb_pages_created", 0))

                qps = round(queries / uptime, 1) if uptime > 0 else 0

                hit_ratio = 0.0
                if bp_reads_req + bp_reads > 0:
                    hit_ratio = round(
                        (bp_reads_req / (bp_reads_req + bp_reads)) * 100, 1
                    )

                bp_size_gb = round((bp_total * 16384) / (1024**3), 1)
                bp_used_gb = round((bp_data * 16384) / (1024**3), 1)
                bp_used_pct = round((bp_data / bp_total) * 100, 1) if bp_total > 0 else 0

                return {
                    "uptime": uptime,
                    "uptime_human": _format_uptime(uptime),
                    "queries_total": queries,
                    "qps": qps,
                    "threads_connected": threads_connected,
                    "threads_running": threads_running,
                    "max_connections": max_conn,
                    "max_used_connections": max_used,
                    "connections_total": connections,
                    "aborted_connects": aborted_connects,
                    "aborted_clients": aborted_clients,
                    "threads_cached": threads_cached,
                    "buffer_pool_size_gb": bp_size_gb,
                    "buffer_pool_used_gb": bp_used_gb,
                    "buffer_pool_used_pct": bp_used_pct,
                    "buffer_pool_hit_ratio": hit_ratio,
                    "innodb_pages_read": pages_read,
                    "innodb_pages_created": pages_created,
                    "mysql_connected": True,
                }

    except Exception as e:
        logger.error(f"Error en SHOW GLOBAL STATUS: {e}")
        return {"error": str(e), "mysql_connected": False}