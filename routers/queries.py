#routers/queries.py
from fastapi import APIRouter, Query
from services.queries_cache import (
    get_cached_queries,
    get_query_users,
    get_query_databases,
    clear_cached_queries,
)

router = APIRouter(prefix="/api/queries", tags=["queries"])


@router.get("")
async def get_queries(
    user: str = Query(default=None),
    db: str = Query(default=None),
    date_from: str = Query(default=None),
    min_time: float = Query(default=None),
    max_time: float = Query(default=None),
    search: str = Query(default=None),
    sql_type: str = Query(default="SELECT"), # <--- NUEVO: Por defecto solo SELECT
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await get_cached_queries(
        user=user, db_name=db, date_from=date_from,
        min_time=min_time, max_time=max_time,
        search=search, sql_type=sql_type, # <--- NUEVO
        limit=limit, offset=offset,
    )


@router.get("/users")
async def list_users():
    return await get_query_users()


@router.get("/databases")
async def list_databases():
    return await get_query_databases()


@router.delete("")
async def delete_cache():
    deleted = await clear_cached_queries()
    return {"deleted": deleted}