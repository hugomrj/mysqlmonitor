from fastapi import APIRouter, Query
import aiosqlite
from pathlib import Path

router = APIRouter(prefix="/api/audit", tags=["audit"])

DB_PATH = Path(__file__).parent.parent / "monitor.db"


@router.get("")
async def get_audit(
    operation: str = Query(default=None, description="INSERT, UPDATE, DELETE"),
    schema: str = Query(default=None),
    table: str = Query(default=None),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None),
    search: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    conditions = []
    params = []

    if operation:
        conditions.append("event_type = ?")
        params.append(operation.upper())
    if schema:
        conditions.append("schema_name = ?")
        params.append(schema)
    if table:
        conditions.append("table_name = ?")
        params.append(table)
    if date_from:
        conditions.append("date(event_time) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date(event_time) <= ?")
        params.append(date_to)
    if search:
        conditions.append("(schema_name LIKE ? OR table_name LIKE ? OR row_data LIKE ?)")
        params.extend([f"%{search}%"] * 3)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM binlog_events{where}", params
        )
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"""SELECT id, event_time, event_type, schema_name, table_name,
                       affected_rows, row_data, log_file, log_pos
                FROM binlog_events{where}
                ORDER BY event_time DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset]
        )
        rows = await cursor.fetchall()

    return {
        "total": total,
        "data": [
            {
                "id": r[0], "event_time": r[1], "event_type": r[2],
                "schema": r[3], "table": r[4], "affected_rows": r[5],
                "row_data": r[6], "log_file": r[7], "log_pos": r[8],
            }
            for r in rows
        ]
    }


@router.get("/filters")
async def get_filter_options():
    """Devuelve opciones para los dropdowns de filtros."""
    async with aiosqlite.connect(DB_PATH) as db:
        c1 = await db.execute(
            "SELECT DISTINCT schema_name FROM binlog_events "
            "WHERE schema_name IS NOT NULL ORDER BY schema_name"
        )
        schemas = [r[0] for r in await c1.fetchall()]

        c2 = await db.execute(
            "SELECT DISTINCT table_name FROM binlog_events "
            "WHERE table_name IS NOT NULL ORDER BY table_name"
        )
        tables = [r[0] for r in await c2.fetchall()]

    return {"schemas": schemas, "tables": tables}


@router.get("/summary")
async def get_audit_summary():
    """Resumen para las tarjetas: total por tipo."""
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "SELECT event_type, COUNT(*) FROM binlog_events "
            "GROUP BY event_type"
        )
        rows = await c.fetchall()
        result = {r[0]: r[1] for r in rows}
    return {
        "inserts": result.get("INSERT", 0),
        "updates": result.get("UPDATE", 0),
        "deletes": result.get("DELETE", 0),
        "total": sum(result.values()),
    }