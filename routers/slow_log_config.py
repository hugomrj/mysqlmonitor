"""
Router para configurar slow_log dinámicamente desde la UI
"""
from fastapi import APIRouter
from pydantic import BaseModel
from services.slow_log_config import apply_slow_log_config, get_current_slow_log_config, ensure_performance_schema_enabled
from services import recent_queries
from database import load_config, save_config

router = APIRouter(prefix="/api/query-config", tags=["query-config"])


class SlowLogConfig(BaseModel):
    threshold: float
    enabled: bool = True
    log_no_indexes: bool = True


@router.get("/slow-log")
async def get_slow_log_config():
    """Obtiene la configuración actual de slow_log."""
    mysql_config = await get_current_slow_log_config()
    app_config = await load_config()
    return {
        "mysql": mysql_config,
        "app": {
            "threshold": app_config.slow_query_threshold,
            "enabled": app_config.slow_log_enabled,
            "log_no_indexes": app_config.log_queries_not_using_indexes,
        }
    }


@router.post("/slow-log")
async def update_slow_log_config(config: SlowLogConfig):
    """Actualiza la configuración de slow_log dinámicamente."""
    # ═══ VALIDACIÓN EN EL ROUTER (doble seguridad) ═══
    if config.threshold < 1:
        return {
            "success": False, 
            "error": "El umbral debe ser >= 1 segundo"
        }
    if config.threshold > 60:
        return {
            "success": False, 
            "error": "El umbral debe ser <= 60 segundos"
        }
    
    # 1. Aplicar en MySQL
    result = await apply_slow_log_config(
        threshold=config.threshold,
        enabled=config.enabled,
        log_no_indexes=config.log_no_indexes,
    )
    
    if not result["success"]:
        return result
    
    # 2. Guardar en SQLite (config de la app)
    app_config = await load_config()
    app_config.slow_query_threshold = result["threshold"]  # Usar el valor validado
    app_config.slow_log_enabled = config.enabled
    app_config.log_queries_not_using_indexes = config.log_no_indexes
    await save_config(app_config)
    
    return {
        "success": True,
        "message": f"✅ Umbral actualizado a {result['threshold']}s",
        "config": result,
    }


@router.get("/recent-queries/status")
async def get_recent_queries_status():
    """Estado del servicio de consultas recientes."""
    performance_schema_ok = await ensure_performance_schema_enabled()
    stats = await recent_queries.get_stats()
    return {
        "performance_schema_enabled": performance_schema_ok,
        "stats": stats,
    }