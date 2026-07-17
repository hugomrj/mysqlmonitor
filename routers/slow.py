#routers/slow.py
from fastapi import APIRouter, Query
from services.slow_cache import (
    get_cached_queries,
    get_slow_databases,
    get_slow_users,
    clear_cached_queries,
    cache_slow_queries,
)

router = APIRouter(prefix="/api/slow-queries", tags=["slow-queries"])


@router.get("")
async def get_slow_queries(
    min_time: float = Query(default=None),
    max_time: float = Query(default=None),
    db: str = Query(default=None),
    user: str = Query(default=None),
    date_from: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await get_cached_queries(
        min_time=min_time,
        max_time=max_time,
        db_name=db,
        user=user,
        date_from=date_from,
        limit=limit,
        offset=offset,
    )


@router.get("/databases")
async def list_slow_databases():
    return await get_slow_databases()


@router.get("/users")
async def list_slow_users():
    return await get_slow_users()


@router.delete("")
async def delete_slow_cache():
    deleted = await clear_cached_queries()
    return {"deleted": deleted}


@router.post("/force-cache")
async def force_cache():
    count = await cache_slow_queries(min_time=0.5)
    return {"cached": count}