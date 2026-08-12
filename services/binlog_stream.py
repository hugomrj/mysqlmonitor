#services/binlog_stream.py
"""
Binlog Stream Service
=====================
Lee el binlog de MySQL 5.7 como esclavo silencioso usando python-mysql-replication.
Corre en un thread separado (la lib es síncrona/blocking) y puentea eventos
al event loop async vía Queue. Los eventos se:
  - Guardan en SQLite (auditoría)
  - Broadcastean por WebSocket /ws/binlog
  - Mantienen en memoria un buffer circular para clientes nuevos
"""
import asyncio
import json
import logging
import queue
import sqlite3
import threading
import time
import random
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Set

import aiosqlite


import logging
logging.getLogger("pymysqlreplication").setLevel(logging.ERROR)


logger = logging.getLogger("binlog_stream")

DB_PATH = "monitor.db"
MAX_STORED_EVENTS = 10000
MAX_ROW_DATA_ROWS = 5
MAX_STRING_LENGTH = 200


def _get_replication_module():
    """Import tardío — no falla si no está instalado."""
    try:
        from pymysqlreplication import BinLogStreamReader
        from pymysqlreplication.row_event import (
            DeleteRowsEvent,
            UpdateRowsEvent,
            WriteRowsEvent,
            TableMapEvent,  
        )
        return BinLogStreamReader, WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent, TableMapEvent
    except ImportError:
        logger.error(
            "pymysql-replication no instalado. Ejecuta: pip install pymysql-replication"
        )
        return None, None, None, None, None


class BinlogStreamService:
    def __init__(self):
        self._queue: queue.Queue = queue.Queue(maxsize=50000)
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._recent_events: deque = deque(maxlen=500)
        self._clients: Set = set()
        self._lock = threading.Lock()
        self._eps_counter: int = 0
        self._eps_last_time: float = time.time()
        
        # NUEVO: Caché para resolver los nombres de columnas en MySQL 5.7
        self._columns_cache: dict = {} 
        
        self._stats: dict = {
            "total_events": 0,
            "insert_count": 0,
            "update_count": 0,
            "delete_count": 0,
            "other_count": 0,
            "events_per_second": 0.0,
            "started_at": None,
            "last_event_at": None,
            "current_log_file": None,
            "current_log_pos": 0,
            "streamer_running": False,
            "error": None,
            "tables_hot": {},
        }

    # ── Propiedades públicas ──────────────────────────────────────

    @property
    def stats(self) -> dict:
        with self._lock:
            s = {**self._stats}
            s["tables_hot"] = dict(s["tables_hot"])
            return s

    @property
    def is_running(self) -> bool:
        return self._running

    def add_client(self, ws_send):
        self._clients.add(ws_send)

    def remove_client(self, ws_send):
        self._clients.discard(ws_send)

    def get_recent_events(self, limit: int = 50) -> list:
        return list(self._recent_events)[-limit:]

    # ── Verificar si binlog está disponible ───────────────────────

    async def check_binlog_available(self, mysql_config: dict) -> bool:
        """Verifica si el servidor MySQL tiene binlog habilitado."""
        try:
            import aiomysql
            conn = await aiomysql.connect(
                host=mysql_config.get("host", "localhost"),
                port=int(mysql_config.get("port", 3306)),
                user=mysql_config.get("user", "root"),
                password=mysql_config.get("password", ""),      
                connect_timeout=5,
            )
            try:
                async with conn.cursor() as cur:
                    await cur.execute("SHOW VARIABLES LIKE 'log_bin'")
                    row = await cur.fetchone()
                    if not row or row[1] != "ON":
                        logger.warning("Binlog NO habilitado en el servidor MySQL")
                        with self._lock:
                            self._stats["error"] = "Binlog no habilitado en el servidor"
                            self._stats["streamer_running"] = False
                        return False

                    await cur.execute("SHOW VARIABLES LIKE 'binlog_format'")
                    row = await cur.fetchone()
                    if not row or row[1] != "ROW":
                        logger.warning("Binlog format no es ROW")
                        with self._lock:
                            self._stats["error"] = "Binlog format debe ser ROW"
                        return False

                logger.info("Binlog disponible y habilitado ✓")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error verificando binlog: {e}")
            with self._lock:
                self._stats["error"] = str(e)
            return False

    # ── Control de ciclo de vida ──────────────────────────────────

    async def start(self, mysql_config: dict):
        if self._running:
            logger.warning("Binlog streamer ya está corriendo")
            return

        available = await self.check_binlog_available(mysql_config)
        if not available:
            logger.info("Binlog no disponible, funcionalidad deshabilitada")
            return

        self._running = True
        with self._lock:
            self._stats["started_at"] = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(
            target=self._run_streamer,
            args=(mysql_config,),
            daemon=True,
            name="binlog-streamer",
        )
        self._thread.start()
        logger.info("Binlog streamer iniciado")
        asyncio.create_task(self._consume_loop())
        asyncio.create_task(self._eps_calculator())

    async def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            self._stats["streamer_running"] = False
        logger.info("Binlog streamer detenido")

    async def restart(self, mysql_config: dict):
        await self.stop()
        await asyncio.sleep(0.5)
        await self.start(mysql_config)

    # ── NUEVO: Resolver nombres de columnas para MySQL 5.7 ───────

    def _fetch_columns_sync(self, schema: str, table: str, mysql_config: dict):
        """Consulta information_schema para obtener los nombres reales de las columnas."""
        key = f"{schema}.{table}"
        if key in self._columns_cache:
            return self._columns_cache[key]
        
        try:
            import pymysql # pymysql-replication lo usa, así que existe
            conn = pymysql.connect(
                host=mysql_config.get("host", "localhost"),
                port=int(mysql_config.get("port", 3306)),
                user=mysql_config.get("user", "root"),
                password=mysql_config.get("passwd") or mysql_config.get("password", ""),
                connect_timeout=5,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                        (schema, table)
                    )
                    rows = cur.fetchall()
                    cols = [r[0] for r in rows]
                    self._columns_cache[key] = cols
                    return cols
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error obteniendo columnas para {key}: {e}")
            return None

    @staticmethod
    def _map_columns(row_dict: dict, col_names: list) -> dict:
        """Reemplaza claves UNKNOWN_COL0, 0, 1... por los nombres reales."""
        if not col_names:
            return row_dict
            
        mapped = {}
        for i, name in enumerate(col_names):
            # pymysql-replication puede mandar la clave como entero o como UNKNOWN_COLx
            if i in row_dict:
                mapped[name] = row_dict[i]
            elif f"UNKNOWN_COL{i}" in row_dict:
                mapped[name] = row_dict[f"UNKNOWN_COL{i}"]
            elif name in row_dict:
                mapped[name] = row_dict[name]
        return mapped

    # ── Thread: lector síncrono del binlog ────────────────────────

    def _run_streamer(self, mysql_config: dict):
        BinLogStreamReader, WriteEvt, UpdateEvt, DeleteEvt, TableMapEvt = _get_replication_module()
        if BinLogStreamReader is None:
            with self._lock:
                self._stats["error"] = "pymysql-replication no instalado"
            return

        saved_pos = self._load_position()

        while self._running:
            try:
                # ── RECARGAR CONFIG DE MEMORIA EN CADA CICLO ──
                try:
                    from config_state import get_mysql_config_dict
                    mysql_config = get_mysql_config_dict()
                    logger.debug(f"Config recargada: host={mysql_config.get('host')}")
                except Exception as e:
                    logger.warning(f"No se pudo recargar config, usando original: {e}")

                with self._lock:
                    self._stats["streamer_running"] = True
                    self._stats["error"] = None

                stream = BinLogStreamReader(
                    connection_settings={
                        "host": mysql_config.get("host", "localhost"),
                        "port": int(mysql_config.get("port", 3306)),
                        "user": mysql_config.get("user", "root"),
                        "passwd": mysql_config.get("passwd") or mysql_config.get("password", ""),
                        "connect_timeout": 10,
                        "read_timeout": 30,
                    },
                    server_id=random.randint(100000, 999999),
                    blocking=True,
                    only_events=[TableMapEvt, WriteEvt, UpdateEvt, DeleteEvt],
                    resume_stream=True,
                    log_file=saved_pos.get("log_file") if saved_pos else None,
                    log_pos=saved_pos.get("log_pos") if saved_pos else None,
                )
                
                logger.info(
                    f"Binlog conectado, posición: {saved_pos or 'inicio'}"
                )




                try:
                    for binlog_event in stream:
                         
                        logger.info(f"🔥 BINLOG EVENT RECIBIDO: {type(binlog_event).__name__}")

                        if not self._running:
                            break
                            
                        # NUEVO: Interceptamos el TableMap para precargar columnas
                        if isinstance(binlog_event, TableMapEvt):
                            self._fetch_columns_sync(binlog_event.schema, binlog_event.table, mysql_config)
                            continue

                            


                        event_data = self._extract_event(
                            binlog_event, WriteEvt, UpdateEvt, DeleteEvt, mysql_config
                        )
                        if event_data:
                            # ── FIX: Obtener posición REAL del stream (no del evento) ──
                            try:
                                event_data["log_file"] = stream.log_file
                                event_data["log_pos"] = stream.log_pos
                            except AttributeError:
                                # Fallback por si la versión de pymysql-replication es diferente
                                event_data["log_file"] = getattr(stream, 'log_file', 'unknown')
                                event_data["log_pos"] = getattr(stream, 'log_pos', 0)
                            
                            try:
                                self._queue.put_nowait(event_data)
                            except queue.Full:
                                logger.warning("Queue llena, descartando evento")


                finally:
                    stream.close()

            except Exception as e:
                err = str(e)
                logger.error(f"Error en binlog streamer: {err}")
                with self._lock:
                    self._stats["streamer_running"] = False
                    self._stats["error"] = err
                for _ in range(30):
                    if not self._running:
                        return
                    time.sleep(1)

    # ── Extracción segura de datos del evento ─────────────────────

    def _extract_event(self, event, WriteEvt, UpdateEvt, DeleteEvt, mysql_config) -> Optional[dict]:
        try:
            if isinstance(event, WriteEvt):
                etype = "INSERT"
            elif isinstance(event, UpdateEvt):
                etype = "UPDATE"
            elif isinstance(event, DeleteEvt):
                etype = "DELETE"
            else:
                return None

            # NUEVO: Obtener nombres reales de columnas del caché
            key = f"{event.schema}.{event.table}"
            col_names = self._columns_cache.get(key)

            rows_data = []
            for row in event.rows[:MAX_ROW_DATA_ROWS]:
                if etype == "INSERT":
                    vals = self._clean(row.get("values", {}))
                    if col_names: vals = self._map_columns(vals, col_names)
                    rows_data.append(vals)
                elif etype == "DELETE":
                    vals = self._clean(row.get("values", {}))
                    if col_names: vals = self._map_columns(vals, col_names)
                    rows_data.append(vals)
                elif etype == "UPDATE":
                    before = self._clean(row.get("before_values", {}))
                    after = self._clean(row.get("after_values", {}))
                    if col_names:
                        before = self._map_columns(before, col_names)
                        after = self._map_columns(after, col_names)
                    rows_data.append({"before": before, "after": after})
                    

            # Obtener log_file y log_pos del packet (donde pymysql-replication los guarda)
            log_file = None
            log_pos = 0

            if hasattr(event, 'packet') and event.packet:
                log_file = getattr(event.packet, 'log_file', None)
                log_pos = getattr(event.packet, 'log_pos', 0)

            # Fallback si no están en packet
            if not log_file:
                log_file = getattr(event, 'log_file', None)
            if not log_pos:
                log_pos = getattr(event, 'log_pos', 0)

            # Último fallback
            if not log_file:
                log_file = 'unknown'
            if not log_pos:
                log_pos = 0




            return {
                "event_time": datetime.now(timezone.utc).isoformat(),
                "event_type": etype,
                "schema": event.schema,
                "table": event.table,
                "affected_rows": len(event.rows),
                "row_data": json.dumps(rows_data, default=str, ensure_ascii=False),
                "log_file": log_file,
                "log_pos": log_pos,
            }
        except Exception as e:
            logger.error(f"Error extrayendo evento: {e}")
            return None

    @staticmethod
    def _clean(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if isinstance(v, (bytes, bytearray)):
                try:
                    v = v.decode("utf-8", errors="replace")
                except Exception:
                    v = "<binary>"
            if isinstance(v, str) and len(v) > MAX_STRING_LENGTH:
                v = v[:MAX_STRING_LENGTH] + "…"
            out[k] = v
        return out

    # ── Persistencia de posición (sync, desde el thread) ──────────

    def _load_position(self) -> Optional[dict]:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT log_file, log_pos FROM binlog_position WHERE id=1"
            ).fetchone()
            conn.close()
            if row and row["log_file"] not in (None, "unknown", ""):
                return {"log_file": row["log_file"], "log_pos": row["log_pos"]}
        except Exception:
            pass
        return None


    def _save_position(self, log_file: str, log_pos: int):
        # AGREGA ESTE LOG:
        logger.info(f"💾 Guardando posición: log_file={log_file}, log_pos={log_pos}")
        
        if not log_file or log_file == "unknown":
            logger.warning(f"⚠️ Posición inválida, no se guarda: {log_file}")
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                """INSERT INTO binlog_position (id,log_file,log_pos,updated_at)
                VALUES(1,?,?,datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    log_file=excluded.log_file,
                    log_pos=excluded.log_pos,
                    updated_at=excluded.updated_at""",
                (log_file, log_pos),
            )
            conn.commit()
            conn.close()
            logger.info(f"✅ Posición guardada: {log_file}:{log_pos}")
        except Exception as e:
            logger.error(f"Error guardando posición: {e}")



    # ── Loop async: consume de la queue ───────────────────────────

    async def _consume_loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                evt = await loop.run_in_executor(
                    None, self._queue.get, True, 1.0
                )
            except queue.Empty:
                continue

            with self._lock:
                self._stats["total_events"] += 1
                self._stats["last_event_at"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self._eps_counter += 1
                t = evt["event_type"]
                if t == "INSERT":
                    self._stats["insert_count"] += 1
                elif t == "UPDATE":
                    self._stats["update_count"] += 1
                elif t == "DELETE":
                    self._stats["delete_count"] += 1
                else:
                    self._stats["other_count"] += 1
                key = f"{evt['schema']}.{evt['table']}"
                self._stats["tables_hot"][key] = (
                    self._stats["tables_hot"].get(key, 0) + 1
                )

            await self._store_event(evt)

            loop.run_in_executor(
                None, self._save_position, evt["log_file"], evt["log_pos"]
            )

            self._recent_events.append(evt)

            row_preview = None
            try:
                rows = json.loads(evt.get("row_data", "[]"))
                if rows:
                    row_preview = rows[0]
            except Exception:
                pass

            ws_payload = {
                "type": "binlog_event",
                "data": {
                    "event_time": evt["event_time"],
                    "event_type": evt["event_type"],
                    "schema": evt["schema"],
                    "table": evt["table"],
                    "affected_rows": evt["affected_rows"],
                    "log_file": evt["log_file"],
                    "log_pos": evt["log_pos"],
                    "row_preview": row_preview,
                },
            }
            await self._broadcast(ws_payload)

    async def _store_event(self, evt: dict):
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT INTO binlog_events
                       (event_time,event_type,schema_name,table_name,
                        affected_rows,row_data,log_file,log_pos)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        evt["event_time"],
                        evt["event_type"],
                        evt["schema"],
                        evt["table"],
                        evt["affected_rows"],
                        evt["row_data"],
                        evt["log_file"],
                        evt["log_pos"],
                    ),
                )
                await db.execute(
                    "DELETE FROM binlog_events WHERE id NOT IN "
                    "(SELECT id FROM binlog_events ORDER BY id DESC LIMIT ?)",
                    (MAX_STORED_EVENTS,),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error guardando evento: {e}")

    async def _broadcast(self, payload: dict):
        if not self._clients:
            return
        dead = set()
        msg = json.dumps(payload, ensure_ascii=False)
        for ws in self._clients:
            try:
                await ws({"type": "websocket.send", "text": msg})
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def _eps_calculator(self):
        while self._running:
            await asyncio.sleep(1)
            now = time.time()
            elapsed = now - self._eps_last_time
            if elapsed > 0:
                with self._lock:
                    self._stats["events_per_second"] = round(
                        self._eps_counter / elapsed, 1
                    )
                    self._eps_counter = 0
                    self._eps_last_time = now


# ── Singleton ────────────────────────────────────────────────────
binlog_service = BinlogStreamService()