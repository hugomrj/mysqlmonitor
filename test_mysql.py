import asyncio
import aiomysql
from config_state import get_mysql_config_dict

async def test():
    cfg = get_mysql_config_dict()
    print(f"🔌 Conectando a: {cfg.get('host')}:{cfg.get('port')}")
    
    conn = await aiomysql.connect(
        host=cfg.get("host", "localhost"),
        port=int(cfg.get("port", 3306)),
        user=cfg.get("user", "root"),
        password=cfg.get("passwd") or cfg.get("password", ""),
    )
    
    async with conn.cursor() as cur:
        # Información del servidor
        await cur.execute("SELECT @@hostname, @@server_id, @@port, @@datadir")
        info = await cur.fetchone()
        print(f"📡 Servidor: hostname={info[0]}, server_id={info[1]}, port={info[2]}")
        print(f"📁 Datadir: {info[3]}")
        
        # Verificar umbral ACTUAL
        await cur.execute("SHOW VARIABLES LIKE 'long_query_time'")
        row = await cur.fetchone()
        print(f"⏱️  long_query_time ANTES: {row[1]}")
        
        # Intentar cambiarlo
        await cur.execute("SET GLOBAL long_query_time = 3")
        print("✅ SET ejecutado")
        
        # Verificar DESPUÉS
        await cur.execute("SHOW VARIABLES LIKE 'long_query_time'")
        row = await cur.fetchone()
        print(f"⏱️  long_query_time DESPUÉS: {row[1]}")
        
        # Verificar permisos
        await cur.execute("SHOW GRANTS FOR CURRENT_USER()")
        grants = await cur.fetchall()
        print("\n🔐 Permisos del usuario:")
        for g in grants:
            print(f"   {g[0]}")
    
    conn.close()

asyncio.run(test())