from fastapi import APIRouter, Query
from typing import Optional
import json

import aiosqlite

from services.binlog_stream import binlog_service, DB_PATH

router = APIRouter(prefix="/api/binlog", tags=["binlog"])



@router.get("/status")
async def binlog_status():
    """Devuelve si el binlog está activo o no y por qué."""
    stats = binlog_service.stats
    return {
        "enabled": binlog_service.is_running,
        "error": stats.get("error"),
        "message": (
            "Binlog activo" if binlog_service.is_running
            else stats.get("error") or "Binlog no disponible en este servidor"
        ),
    }



@router.get("/events")
async def get_events(
    limit: int = Query(50, ge=1, le=500),
    event_type: Optional[str] = Query(None, pattern="^(INSERT|UPDATE|DELETE)$"),
    schema: Optional[str] = None,
    table: Optional[str] = None,
    include_data: bool = Query(False),
):
    """Eventos históricos desde SQLite con filtros."""
    conds, params = [], []
    if event_type:
        conds.append("event_type = ?")
        params.append(event_type)
    if schema:
        conds.append("schema_name = ?")
        params.append(schema)
    if table:
        conds.append("table_name = ?")
        params.append(table)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    cols = "id,event_time,event_type,schema_name,table_name,affected_rows,log_file,log_pos"
    if include_data:
        cols += ",row_data"

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute(
            f"SELECT {cols} FROM binlog_events {where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        )
        result = [dict(r) for r in await rows.fetchall()]

    for e in result:
        if include_data and e.get("row_data"):
            try:
                e["row_data"] = json.loads(e["row_data"])
            except Exception:
                pass
        else:
            e.pop("row_data", None)
    return result


@router.get("/stats")
async def get_stats():
    """Estadísticas agregadas: por tipo, top tablas, por minuto."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        by_type_rows = await db.execute(
            "SELECT event_type, COUNT(*) as cnt FROM binlog_events GROUP BY event_type"
        )
        by_type = {r["event_type"]: r["cnt"] for r in await by_type_rows.fetchall()}

        top_rows = await db.execute(
            """SELECT schema_name, table_name, COUNT(*) as cnt
               FROM binlog_events
               GROUP BY schema_name, table_name
               ORDER BY cnt DESC LIMIT 20"""
        )
        top_tables = [dict(r) for r in await top_rows.fetchall()]

        min_rows = await db.execute(
            """SELECT strftime('%Y-%m-%d %H:%M', event_time) as minute,
                      COUNT(*) as cnt
               FROM binlog_events
               WHERE event_time > datetime('now', '-1 hour')
               GROUP BY minute ORDER BY minute"""
        )
        per_minute = [dict(r) for r in await min_rows.fetchall()]

    return {
        "by_type": by_type,
        "top_tables": top_tables,
        "per_minute": per_minute,
    }


@router.delete("/events")
async def clear_events():
    """Limpia todo el historial de eventos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM binlog_events")
        await db.commit()
    binlog_service._recent_events.clear()
    with binlog_service._lock:
        for k in ("total_events", "insert_count", "update_count",
                   "delete_count", "other_count"):
            binlog_service._stats[k] = 0
        binlog_service._stats["tables_hot"] = {}
    return {"ok": True}


@router.post("/restart")
async def restart_streamer():
    """Reinicia el streamer (útil tras cambiar config)."""
    from database import load_config

    cfg = await load_config()
    mysql_cfg = cfg.mysql.model_dump()
    await binlog_service.restart(mysql_cfg)
    return {"ok": True}