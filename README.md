# MySQL Monitor

Monitor en tiempo real para MySQL 5.7+ con interfaz web moderna.

Visualiza métricas de rendimiento, consultas en vivo, consultas lentas, eventos de binlog y auditoría de cambios, todo desde un panel de control unificado.

## Características

- Dashboard: CPU, RAM, disco, QPS, conexiones activas
- Consultas Recientes (Live): Stream en tiempo real desde performance_schema
- Consultas Lentas: Histórico persistente con umbrales configurables
- Binlog Live: Auditoría de INSERT, UPDATE, DELETE en tiempo real
- Esquema: Explorador de bases de datos y tablas
- Sesiones: Usuarios conectados con SHOW PROCESSLIST
- Alertas: Sistema de umbrales personalizables
- Configuración en caliente: Cambia credenciales y umbrales sin reiniciar

## Instalación

    git clone <tu-repo>
    cd mysql-monitor

    python3 -m venv venv
    source venv/bin/activate

    pip install -r requirements.txt

## Requisitos de MySQL

### Funciona sin configuración (out-of-the-box)

Las siguientes funcionalidades NO requieren ninguna configuración especial en MySQL. Solo necesitas un usuario con permisos de lectura sobre tus bases de datos:

- Dashboard (métricas de servidor)
- Consultas Recientes (Live)
- Consultas Lentas
- Explorador de bases de datos y tablas
- Usuarios conectados
- Alertas

Nota: La aplicación activa automáticamente los consumers necesarios de performance_schema en cada arranque, por lo que no necesitas ejecutar ningún comando SQL manualmente.

### Configuraciones opcionales

| Funcionalidad                        | Configuración requerida                | Archivo a modificar    |
|--------------------------------------|----------------------------------------|------------------------|
| Binlog Live (auditoría de cambios)   | Activar binlog + permisos de replicación | my.cnf o mysqld.cnf   |
| Consultas Lentas                     | Ninguna manual (la app lo configura)   | —                      |

## Habilitar Binlog Live (opcional)

Si deseas visualizar los eventos INSERT, UPDATE y DELETE en tiempo real, debes activar el Binary Log de MySQL.

### Paso 1: Editar la configuración

Localiza el archivo de configuración de MySQL:

| Sistema            | Ubicación                                    |
|--------------------|----------------------------------------------|
| Debian/Ubuntu      | /etc/mysql/mysql.conf.d/mysqld.cnf           |
| RHEL/CentOS        | /etc/my.cnf                                  |
| macOS (Homebrew)   | /usr/local/etc/my.cnf                        |

Dentro de la sección [mysqld], agrega estas líneas:

    [mysqld]
    server-id = 1
    log_bin = mysql-bin
    binlog_format = ROW
    binlog_row_image = FULL
    expire_logs_days = 7
    max_binlog_size = 100M

Importante: binlog_format debe ser ROW y binlog_row_image debe ser FULL. Otros formatos (STATEMENT, MIXED, MINIMAL) no son compatibles con esta aplicación.

### Paso 2: Reiniciar MySQL

    # Debian/Ubuntu
    sudo systemctl restart mysql

    # RHEL/CentOS
    sudo systemctl restart mysqld

### Paso 3: Verificar

    mysql -u root -p -e "SHOW VARIABLES LIKE 'log_bin';"

Resultado esperado:

    +---------------+-------+
    | Variable_name | Value |
    +---------------+-------+
    | log_bin       | ON    |
    +---------------+-------+

Verifica también el formato:

    SHOW VARIABLES LIKE 'binlog_format';        -- Debe ser ROW
    SHOW VARIABLES LIKE 'binlog_row_image';     -- Debe ser FULL
    SHOW VARIABLES LIKE 'server_id';            -- Debe ser > 0

## Permisos del usuario de MySQL

### Permisos mínimos (funciones básicas)

    -- Permisos básicos para todas las funciones excepto Binlog
    GRANT SELECT ON *.* TO 'tu_usuario'@'%';
    GRANT SELECT ON performance_schema.* TO 'tu_usuario'@'%';
    FLUSH PRIVILEGES;

### Permisos completos (incluye Binlog Live)

    -- Agregar permisos de replicación para el binlog
    GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'tu_usuario'@'%';
    FLUSH PRIVILEGES;

Recomendación: Crea un usuario dedicado para el monitor con permisos limitados:

    CREATE USER 'monitor'@'%' IDENTIFIED BY 'contraseña_segura';
    GRANT SELECT, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'monitor'@'%';
    FLUSH PRIVILEGES;

## Sobre las Consultas Lentas

No necesitas configurar nada manualmente. La aplicación:

1. Activa automáticamente slow_query_log = ON
2. Configura log_output = TABLE (guarda en mysql.slow_log)
3. Ajusta long_query_time según el umbral que definas en la UI (por defecto 3 segundos)
4. Activa los consumers necesarios de performance_schema

Puedes cambiar el umbral desde la interfaz: Configuración → Consultas Lentas.

## Ejecución

### Desarrollo (con auto-reload)

    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

### Producción

    pip install gunicorn

    gunicorn main:app \
      -w 4 \
      -k uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:8000

## Uso

Abre el navegador en:

    http://localhost:8000

Desde la interfaz podrás:

1. Configurar la conexión a tu servidor MySQL (host, puerto, usuario, contraseña)
2. Definir el umbral de consultas lentas (por defecto 3 segundos)
3. Monitorear en tiempo real todas las métricas de tu servidor

Los cambios de configuración se aplican en caliente, sin necesidad de reiniciar la aplicación.

## Troubleshooting

### "Sin acceso a consultas" o error 1142

El usuario no tiene permisos sobre performance_schema. Solución:

    GRANT SELECT ON performance_schema.* TO 'tu_usuario'@'%';
    FLUSH PRIVILEGES;

### Error 1236 en Binlog (server_id duplicado)

Si ves "A slave with the same server_id has connected", simplemente espera unos segundos o reinicia la aplicación. La aplicación genera un server_id único en cada arranque.

### El Binlog no aparece activo

Verifica que editaste el archivo correcto y reiniciaste MySQL:

    sudo systemctl restart mysql
    mysql -u root -p -e "SHOW VARIABLES LIKE 'log_bin';"

### No se registran consultas lentas

La aplicación las captura desde performance_schema, no desde el slow_query_log tradicional. Asegúrate de:

1. Que el umbral esté configurado correctamente (Configuración → Consultas Lentas)
2. Que el usuario tenga permisos sobre performance_schema.*
3. Esperar al menos 10 segundos (ciclo de sincronización)