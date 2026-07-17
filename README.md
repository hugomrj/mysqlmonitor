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

### Activar Binlog

La aplicación funciona completamente sin esta configuración.

Si deseas habilitar la pestaña **Binlog Live** para visualizar eventos
`INSERT`, `UPDATE` y `DELETE` en tiempo real, activa el Binary Log de MySQL.

En Linux (Debian/Ubuntu), edita:

```
/etc/mysql/mysql.conf.d/mysqld.cnf
```

También puede encontrarse en:

```
/etc/mysql/my.cnf
/etc/my.cnf
```

Dentro de la sección `[mysqld]`, agrega:

```
[mysqld]
server-id = 1
log_bin = mysql-bin
binlog_format = ROW
binlog_row_image = FULL

slow_query_log = 1
slow_query_log_file = /var/lib/mysql/mysql-slow.log
long_query_time = 10
```

El `Slow Query Log` registrará las consultas que tarden **10 segundos o más**.

Reinicia el servicio de MySQL:

```
sudo systemctl restart mysql
```

Después reinicia la aplicación.

Para comprobar que el Binlog está activo:

```
mysql -u root -p -e "SHOW VARIABLES LIKE 'log_bin';"
```

El resultado esperado es:

```
log_bin | ON
```

Para comprobar que el Slow Query Log está activo:

```
mysql -u root -p -e "SHOW VARIABLES LIKE 'slow_query_log';"
```

El resultado esperado es:

```
slow_query_log | ON
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