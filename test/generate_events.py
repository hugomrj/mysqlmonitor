#!/usr/bin/env python3
"""
Generador de eventos para probar Binlog
Ejecuta INSERT/UPDATE/DELETE en loop continuo
"""

import argparse
import sys
import time
import random
import signal
import pymysql
from getpass import getpass
from datetime import datetime


# Variable global para controlar Ctrl+C
running = True


def signal_handler(sig, frame):
    """Maneja Ctrl+C para detener el loop"""
    global running
    print("\n\n⏹️  Deteniendo generador de eventos...")
    running = False


def get_connection(host, port, user, password):
    """Crea conexión a MySQL"""
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="test_binlog",
            connect_timeout=5,
            autocommit=True,
        )
        return conn
    except pymysql.Error as e:
        print(f"❌ Error conectando a MySQL: {e}")
        sys.exit(1)


def random_insert_usuario(cur):
    """INSERT en tabla usuarios"""
    nombres = ["Luis", "Carmen", "Roberto", "Patricia", "Miguel", "Laura"]
    apellidos = ["Rodríguez", "Fernández", "Gómez", "Díaz", "Torres", "Ruiz"]
    
    nombre = random.choice(nombres)
    apellido = random.choice(apellidos)
    email = f"{nombre.lower()}.{apellido.lower()}{random.randint(100,999)}@example.com"
    edad = random.randint(18, 65)
    activo = random.choice([True, False])
    
    cur.execute("""
        INSERT INTO usuarios (nombre, email, edad, activo) VALUES (%s, %s, %s, %s)
    """, (f"{nombre} {apellido}", email, edad, activo))
    
    return f"INSERT usuario: {nombre} {apellido}"


def random_update_usuario(cur):
    """UPDATE en tabla usuarios"""
    cur.execute("SELECT id, nombre FROM usuarios ORDER BY RAND() LIMIT 1")
    result = cur.fetchone()
    
    if not result:
        return None
    
    user_id, nombre_actual = result
    nueva_edad = random.randint(18, 65)
    
    cur.execute("""
        UPDATE usuarios SET edad = %s WHERE id = %s
    """, (nueva_edad, user_id))
    
    return f"UPDATE usuario #{user_id} ({nombre_actual}): edad → {nueva_edad}"


def random_delete_usuario(cur):
    """DELETE en tabla usuarios"""
    cur.execute("SELECT id, nombre FROM usuarios WHERE id NOT IN (SELECT DISTINCT usuario_id FROM pedidos) ORDER BY RAND() LIMIT 1")
    result = cur.fetchone()
    
    if not result:
        return None
    
    user_id, nombre = result
    
    cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
    
    return f"DELETE usuario #{user_id} ({nombre})"


def random_insert_producto(cur):
    """INSERT en tabla productos"""
    categorias = ["Electrónica", "Accesorios", "Audio", "Gaming", "Oficina"]
    prefijos = ["Ultra", "Pro", "Max", "Plus", "Elite"]
    tipos = ["Laptop", "Tablet", "Smartphone", "Cargador", "Cable"]
    
    codigo = f"PROD{random.randint(1000, 9999)}"
    nombre = f"{random.choice(prefijos)} {random.choice(tipos)} {random.randint(100,999)}"
    precio = round(random.uniform(9.99, 999.99), 2)
    stock = random.randint(0, 100)
    categoria = random.choice(categorias)
    
    cur.execute("""
        INSERT INTO productos (codigo, nombre, precio, stock, categoria) VALUES (%s, %s, %s, %s, %s)
    """, (codigo, nombre, precio, stock, categoria))
    
    return f"INSERT producto: {nombre} (${precio})"


def random_update_producto(cur):
    """UPDATE en tabla productos"""
    cur.execute("SELECT id, nombre, stock FROM productos ORDER BY RAND() LIMIT 1")
    result = cur.fetchone()
    
    if not result:
        return None
    
    prod_id, nombre, stock_actual = result
    nuevo_stock = max(0, stock_actual + random.randint(-10, 20))
    
    cur.execute("""
        UPDATE productos SET stock = %s WHERE id = %s
    """, (nuevo_stock, prod_id))
    
    return f"UPDATE producto #{prod_id} ({nombre}): stock {stock_actual} → {nuevo_stock}"


def random_delete_producto(cur):
    """DELETE en tabla productos"""
    cur.execute("""
        SELECT id, nombre FROM productos 
        WHERE id NOT IN (SELECT DISTINCT producto_id FROM pedidos) 
        ORDER BY RAND() LIMIT 1
    """)
    result = cur.fetchone()
    
    if not result:
        return None
    
    prod_id, nombre = result
    
    cur.execute("DELETE FROM productos WHERE id = %s", (prod_id,))
    
    return f"DELETE producto #{prod_id} ({nombre})"


def random_insert_pedido(cur):
    """INSERT en tabla pedidos"""
    cur.execute("SELECT id FROM usuarios WHERE activo = TRUE ORDER BY RAND() LIMIT 1")
    usuario = cur.fetchone()
    
    cur.execute("SELECT id, precio FROM productos ORDER BY RAND() LIMIT 1")
    producto = cur.fetchone()
    
    if not usuario or not producto:
        return None
    
    usuario_id = usuario[0]
    producto_id, precio = producto
    cantidad = random.randint(1, 5)
    total = round(precio * cantidad, 2)
    estado = random.choice(["pendiente", "procesado", "enviado"])
    
    cur.execute("""
        INSERT INTO pedidos (usuario_id, producto_id, cantidad, total, estado) 
        VALUES (%s, %s, %s, %s, %s)
    """, (usuario_id, producto_id, cantidad, total, estado))
    
    return f"INSERT pedido: Usuario #{usuario_id} compró {cantidad}x Producto #{producto_id} (${total})"


def generate_events(host, port, user, password, interval, operations):
    """Genera eventos en loop continuo"""
    print("🔌 Conectando a MySQL...")
    conn = get_connection(host, port, user, password)
    
    print("✅ Conectado a test_binlog")
    print(f"⏱️  Intervalo entre eventos: {interval} segundos")
    print(f"📊 Operaciones disponibles: {', '.join(operations)}")
    print("\n🚀 Generando eventos... (Ctrl+C para detener)\n")
    
    event_count = 0
    
    # Mapeo de operaciones a funciones
    operations_map = {
        "insert_usuario": random_insert_usuario,
        "update_usuario": random_update_usuario,
        "delete_usuario": random_delete_usuario,
        "insert_producto": random_insert_producto,
        "update_producto": random_update_producto,
        "delete_producto": random_delete_producto,
        "insert_pedido": random_insert_pedido,
    }
    
    try:
        with conn.cursor() as cur:
            while running:
                # Elegir operación aleatoria
                op = random.choice(operations)
                func = operations_map[op]
                
                try:
                    result = func(cur)
                    if result:
                        event_count += 1
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] #{event_count:04d} | {result}")
                
                except pymysql.Error as e:
                    if "Duplicate entry" in str(e):
                        # Email o código duplicado, ignorar
                        pass
                    else:
                        print(f"❌ Error en {op}: {e}")
                
                # Esperar antes del siguiente evento
                time.sleep(interval)
    
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        print(f"\n📊 Total de eventos generados: {event_count}")


def main():
    parser = argparse.ArgumentParser(description="Generador de eventos para Binlog")
    parser.add_argument("--host", default="localhost", help="Host de MySQL (default: localhost)")
    parser.add_argument("--port", type=int, default=3306, help="Puerto de MySQL (default: 3306)")
    parser.add_argument("--user", default="root", help="Usuario de MySQL (default: root)")
    parser.add_argument("--password", default=None, help="Contraseña de MySQL")
    parser.add_argument("--interval", type=float, default=2.0, help="Segundos entre eventos (default: 2.0)")
    parser.add_argument(
        "--operations",
        nargs="+",
        default=["insert_usuario", "update_usuario", "delete_usuario",
                 "insert_producto", "update_producto", "delete_producto",
                 "insert_pedido"],
        help="Operaciones a ejecutar (default: todas)"
    )
    
    args = parser.parse_args()
    
    # Si no se pasó password, pedirlo
    password = args.password
    if password is None:
        password = getpass("Contraseña de MySQL: ")
    
    # Configurar handler para Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    generate_events(args.host, args.port, args.user, password, args.interval, args.operations)


if __name__ == "__main__":
    main()