import logging
from fastapi import WebSocket

logger = logging.getLogger("mysql_monitor.websocket")

# Lista de clientes conectados
connected_clients: list[WebSocket] = []


async def connect_client(websocket: WebSocket):
    """Acepta un nuevo cliente WebSocket."""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info(f"Cliente conectado. Total: {len(connected_clients)}")


async def disconnect_client(websocket: WebSocket):
    """Remueve un cliente."""
    if websocket in connected_clients:
        connected_clients.remove(websocket)
    logger.info(f"Cliente desconectado. Total: {len(connected_clients)}")


async def broadcast(data: dict):
    """Envía datos a todos los clientes conectados.
    Si un cliente falla, lo remueve silenciosamente."""
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