from fastapi import APIRouter, Query
from collectors.schema import collect_databases, collect_tables, collect_top_tables

router = APIRouter(prefix="/api/databases", tags=["databases"])


@router.get("")
async def get_databases():
    """Lista de bases de datos con tamaño."""
    return await collect_databases()


@router.get("/top-tables")
async def get_top_tables(limit: int = Query(default=8, ge=1, le=50)):
    """Top N tablas más grandes del servidor."""
    return await collect_top_tables(limit)


@router.get("/{schema}/tables")
async def get_tables(schema: str):
    """Tablas de una base de datos específica."""
    return await collect_tables(schema)