import logging

logger = logging.getLogger("mysql_monitor.websocket")

connected_clients: list = []


async def broadcast(data: dict):
    dead = []
    for client in connected_clients:
        try:
            await client.send_json(data)
        except Exception:
            dead.append(client)
    for d in dead:
        connected_clients.remove(d)
    if dead:
        logger.info(f"{len(dead)} cliente(s) removido(s) por error")