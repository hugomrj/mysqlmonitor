#database.py
"""
database.py - Gestión de la base de datos SQLite local (monitor.db)

Almacena:
- config: configuración de la aplicación
- binlog_events: auditoría de eventos del binlog
- binlog_position: posición actual del binlog
- slow_queries: caché de consultas lentas (recreada en cada arranque)
- queries_cache: caché de consultas de performance_schema
"""
import logging
import aiosqlite
from pathlib import Path
from config import AppSettings

DB_PATH = Path(__file__).parent / "monitor.db"
logger = logging.getLogger("mysql_monitor.database")


# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE LA APP
# ══════════════════════════════════════════════════════════════

async def init_db():
    """Crea la tabla de configuración si no existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info(f"✅ Tabla 'config' verificada en {DB_PATH}")


async def load_config() -> AppSettings:
    """Carga la configuración desde SQLite. Si no existe, crea una por defecto."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = 'app_settings'"
        )
        row = await cursor.fetchone()

        if row is None:
            default = AppSettings()
            await db.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                ("app_settings", default.model_dump_json())
            )
            await db.commit()
            logger.info("📝 Configuración por defecto creada")
            return default

        logger.info("📖 Configuración cargada desde SQLite")
        return AppSettings.model_validate_json(row[0])


async def save_config(settings: AppSettings) -> None:
    """
    Guarda la configuración y ACTUALIZA TODOS los componentes en caliente.
    
    Flujo:
    1. Guarda en SQLite (persistente)
    2. Actualiza config_state (memoria)
    3. Recrea el pool de MySQL si cambió la conexión
    4. Re-aplica configuración de slow_log si cambió
    """
    # 1. Guardar en SQLite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("app_settings", settings.model_dump_json())
        )
        await db.commit()
    logger.info("💾 Configuración guardada en SQLite")
    
    # 2. Actualizar estado en memoria (config_state)
    from config_state import set_current_config
    set_current_config(settings)
    logger.info("🧠 config_state actualizado en memoria")
    
    # 3. Recrear pool de MySQL si cambió la conexión
    await _refresh_mysql_pool_if_needed(settings)
    
    # 4. Re-aplicar configuración de slow_log
    await _refresh_slow_log_config(settings)


async def _refresh_mysql_pool_if_needed(settings: AppSettings) -> None:
    """Recrea el pool si cambió la configuración de conexión MySQL."""
    try:
        from mysql_pool import create_pool, _pool, _current_dsn
        
        new_dsn = settings.mysql.dsn
        
        # Solo recrear si cambió la DSN
        if _pool is not None and _current_dsn == new_dsn:
            logger.debug("Pool sin cambios, no se recrea")
            return
        
        logger.info(f"🔄 Recreando pool MySQL con nueva configuración...")
        await create_pool(settings.mysql)
        logger.info(f"✅ Pool MySQL recreado: {settings.mysql.host}:{settings.mysql.port}")
        
    except Exception as e:
        logger.error(f"❌ Error recreando pool: {e}")


async def _refresh_slow_log_config(settings: AppSettings) -> None:
    """Re-aplica la configuración de slow_log si es posible."""
    try:
        from services.slow_log_config import apply_slow_log_config
        
        result = await apply_slow_log_config(
            threshold=settings.slow_query_threshold,
            enabled=settings.slow_log_enabled,
            log_no_indexes=settings.log_queries_not_using_indexes,
        )
        
        if result.get("success"):
            logger.info(f"✅ Slow log re-aplicado: {result}")
        else:
            logger.warning(f"⚠️ No se pudo re-aplicar slow_log: {result.get('error')}")
            
    except Exception as e:
        # No es crítico, puede fallar si no hay pool todavía
        logger.debug(f"No se pudo re-aplicar slow_log (normal si no hay pool): {e}")


# ══════════════════════════════════════════════════════════════
# BINLOG (Auditoría)
# ══════════════════════════════════════════════════════════════

async def init_binlog_tables(db_path: str = "monitor.db"):
    """Crea tablas para auditoría de eventos del binlog."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS binlog_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                event_type TEXT NOT NULL,
                schema_name TEXT,
                table_name TEXT,
                affected_rows INTEGER DEFAULT 1,
                row_data TEXT,
                log_file TEXT,
                log_pos INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bl_ev_time ON binlog_events(event_time);
            CREATE INDEX IF NOT EXISTS idx_bl_ev_st ON binlog_events(schema_name, table_name);
            CREATE INDEX IF NOT EXISTS idx_bl_ev_type ON binlog_events(event_type);

            CREATE TABLE IF NOT EXISTS binlog_position (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                log_file TEXT NOT NULL,
                log_pos INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        await db.commit()
    logger.info("✅ Tablas de binlog verificadas")


# ══════════════════════════════════════════════════════════════
# CONSULTAS LENTAS (Caché)
# ══════════════════════════════════════════════════════════════

async def init_slow_queries_table(db_path: str = "monitor.db"):
    """
    Crea la tabla de consultas lentas desde cero en cada arranque.
    
    Es un caché de monitoreo, no datos críticos:
    - Se recrea en cada inicio para garantizar esquema consistente
    - El bucle de sincronización la vuelve a llenar rápidamente
    - Esto evita migraciones complejas y código con fallbacks
    """
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            DROP TABLE IF EXISTS slow_queries;
            
            CREATE TABLE slow_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT 'unknown',
                client_ip TEXT NOT NULL DEFAULT 'unknown',
                query_time REAL NOT NULL,
                lock_time REAL NOT NULL DEFAULT 0.0,
                rows_sent INTEGER NOT NULL DEFAULT 0,
                rows_examined INTEGER NOT NULL DEFAULT 0,
                db TEXT,
                sql_text TEXT NOT NULL,
                sql_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE INDEX idx_sq_time ON slow_queries(start_time);
            CREATE INDEX idx_sq_username ON slow_queries(username);
            CREATE INDEX idx_sq_client_ip ON slow_queries(client_ip);
            CREATE INDEX idx_sq_db ON slow_queries(db);
            CREATE INDEX idx_sq_query_time ON slow_queries(query_time);
            CREATE UNIQUE INDEX idx_sq_hash ON slow_queries(sql_hash);
        """)
        await db.commit()
    logger.info("✅ Tabla 'slow_queries' recreada (esquema limpio)")


# ══════════════════════════════════════════════════════════════
# CACHÉ DE CONSULTAS GENERALES
# ══════════════════════════════════════════════════════════════

async def init_queries_cache_table(db_path: str = "monitor.db"):
    """Crea tabla para cachear consultas (performance_schema)."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS queries_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                user_host TEXT,
                user_name TEXT,
                command_type TEXT,
                db TEXT,
                sql_text TEXT,
                sql_hash TEXT UNIQUE,
                query_time REAL DEFAULT 0,
                lock_time REAL DEFAULT 0,
                rows_examined INTEGER DEFAULT 0,
                rows_sent INTEGER DEFAULT 0,
                exec_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_qc_time ON queries_cache(event_time);
            CREATE INDEX IF NOT EXISTS idx_qc_user ON queries_cache(user_name);
            CREATE INDEX IF NOT EXISTS idx_qc_db ON queries_cache(db);
        """)
        await db.commit()
    logger.info("✅ Tabla 'queries_cache' verificada")


# ══════════════════════════════════════════════════════════════
# DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════

async def get_db_stats() -> dict:
    """Retorna estadísticas de todas las tablas del monitor."""
    stats = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for table in ['config', 'binlog_events', 'slow_queries', 'queries_cache']:
                try:
                    cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[table] = (await cursor.fetchone())[0]
                except Exception:
                    stats[table] = 0
    except Exception as e:
        logger.error(f"Error obteniendo stats: {e}")
    return stats