# MySQL Monitor

Monitor en tiempo real para MySQL 5.7+.

## Instalación

```bash
git clone <tu-repo>
cd mysql-monitor

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## ⚠️ Configuración del Binlog Live (Opcional)

La aplicación funciona completamente sin esta configuración. Si deseas habilitar la pestaña **Binlog Live** para visualizar eventos `INSERT`, `UPDATE` y `DELETE` en tiempo real, agrega las siguientes líneas al archivo de configuración de MySQL (`/etc/mysql/my.cnf`) dentro de la sección `[mysqld]`:

```ini
[mysqld]
log_bin
binlog_format = ROW
server_id = 1
```

Reinicia el servicio:

```bash
sudo systemctl restart mysql
```

### Privilegios requeridos

El usuario que utilizará la conexión debe contar con los siguientes permisos:

```sql
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'tu_user'@'%';
```

## Ejecución

### Desarrollo (con auto-reload)

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Producción

```bash
pip install gunicorn

gunicorn main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

## Uso

Abre el navegador en:

```
http://localhost:8000
```

Desde la interfaz podrás configurar la conexión a tu servidor MySQL y comenzar a monitorear la base de datos en tiempo real.