#!/usr/bin/env python3
"""
Setup de base de datos de prueba para Binlog
Crea BD, tablas y datos iniciales
"""

import argparse
import sys
import pymysql
from getpass import getpass


def get_connection(host, port, user, password):
    """Crea conexión a MySQL"""
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connect_timeout=5,
            autocommit=True,
        )
        return conn
    except pymysql.Error as e:
        print(f"❌ Error conectando a MySQL: {e}")
        sys.exit(1)


def setup_database(host, port, user, password):
    """Crea la base de datos y tablas de prueba"""
    print("🔌 Conectando a MySQL...")
    conn = get_connection(host, port, user, password)
    
    try:
        with conn.cursor() as cur:
            print("📦 Creando base de datos 'test_binlog'...")
            cur.execute("DROP DATABASE IF EXISTS test_binlog")
            cur.execute("CREATE DATABASE test_binlog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print("✅ Base de datos creada")
            
            print("📦 Creando tablas...")
            cur.execute("USE test_binlog")
            
            # Tabla de usuarios
            cur.execute("""
                CREATE TABLE usuarios (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    edad INT,
                    activo BOOLEAN DEFAULT TRUE,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de productos
            cur.execute("""
                CREATE TABLE productos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    codigo VARCHAR(50) UNIQUE NOT NULL,
                    nombre VARCHAR(200) NOT NULL,
                    precio DECIMAL(10,2) NOT NULL,
                    stock INT DEFAULT 0,
                    categoria VARCHAR(50),
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de pedidos
            cur.execute("""
                CREATE TABLE pedidos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    usuario_id INT NOT NULL,
                    producto_id INT NOT NULL,
                    cantidad INT NOT NULL,
                    total DECIMAL(10,2) NOT NULL,
                    estado ENUM('pendiente', 'procesado', 'enviado', 'entregado') DEFAULT 'pendiente',
                    fecha_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                    FOREIGN KEY (producto_id) REFERENCES productos(id)
                )
            """)
            
            print("✅ Tablas creadas")
            
            print("📦 Insertando datos iniciales...")
            
            # Insertar usuarios
            cur.executemany("""
                INSERT INTO usuarios (nombre, email, edad, activo) VALUES (%s, %s, %s, %s)
            """, [
                ("Juan Pérez", "juan@example.com", 30, True),
                ("María García", "maria@example.com", 25, True),
                ("Carlos López", "carlos@example.com", 35, True),
                ("Ana Martínez", "ana@example.com", 28, True),
                ("Pedro Sánchez", "pedro@example.com", 40, False),
            ])
            
            # Insertar productos
            cur.executemany("""
                INSERT INTO productos (codigo, nombre, precio, stock, categoria) VALUES (%s, %s, %s, %s, %s)
            """, [
                ("PROD001", "Laptop HP", 899.99, 10, "Electrónica"),
                ("PROD002", "Mouse Logitech", 29.99, 50, "Accesorios"),
                ("PROD003", "Teclado Mecánico", 79.99, 30, "Accesorios"),
                ("PROD004", "Monitor 24'", 199.99, 15, "Electrónica"),
                ("PROD005", "Auriculares Sony", 149.99, 20, "Audio"),
            ])
            
            # Insertar pedidos
            cur.executemany("""
                INSERT INTO pedidos (usuario_id, producto_id, cantidad, total, estado) VALUES (%s, %s, %s, %s, %s)
            """, [
                (1, 1, 1, 899.99, "entregado"),
                (2, 2, 2, 59.98, "procesado"),
                (3, 3, 1, 79.99, "pendiente"),
                (1, 5, 1, 149.99, "enviado"),
            ])
            
            print("✅ Datos iniciales insertados")
            print("\n📊 Resumen:")
            cur.execute("SELECT COUNT(*) FROM usuarios")
            print(f"   - Usuarios: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM productos")
            print(f"   - Productos: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM pedidos")
            print(f"   - Pedidos: {cur.fetchone()[0]}")
            
            print("\n✅ Setup completado. Ahora puedes ejecutar generate_events.py")
            
    except pymysql.Error as e:
        print(f"❌ Error configurando base de datos: {e}")
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Setup de BD de prueba para Binlog")
    parser.add_argument("--host", default="localhost", help="Host de MySQL (default: localhost)")
    parser.add_argument("--port", type=int, default=3306, help="Puerto de MySQL (default: 3306)")
    parser.add_argument("--user", default="root", help="Usuario de MySQL (default: root)")
    parser.add_argument("--password", default=None, help="Contraseña de MySQL")
    
    args = parser.parse_args()
    
    # Si no se pasó password, pedirlo
    password = args.password
    if password is None:
        password = getpass("Contraseña de MySQL: ")
    
    setup_database(args.host, args.port, args.user, password)


if __name__ == "__main__":
    main()