# config.py
from pydantic import BaseModel, Field
from typing import Optional


class MySQLConnectionConfig(BaseModel):
    """Configuración de conexión a MySQL 5.7."""
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    charset: str = "utf8mb4"

    @property
    def dsn(self) -> str:
        return f"{self.user}:{self.password}@{self.host}:{self.port}"


class AlertThresholds(BaseModel):
    """Umbrales para generar alertas. Se evalúan cada ciclo."""
    disk_percent: float = Field(default=80.0, ge=0, le=100)
    cpu_percent: float = Field(default=90.0, ge=0, le=100)
    ram_percent: float = Field(default=90.0, ge=0, le=100)
    connections_percent: float = Field(default=80.0, ge=0, le=100)
    slow_query_time: float = Field(default=2.0, ge=0.1)
    max_slow_per_hour: int = Field(default=50, ge=1)


class AppSettings(BaseModel):
    """Configuración completa de la aplicación.
    Se guarda en SQLite y se puede cambiar en caliente."""
    mysql: MySQLConnectionConfig = Field(default_factory=MySQLConnectionConfig)
    refresh_interval: float = Field(default=2.0, ge=0.5, le=60.0)
    alerts: AlertThresholds = Field(default_factory=AlertThresholds)
    binlog_enabled: bool = True