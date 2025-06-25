import logging
from mysql.connector import Error
import db_manager

logger = logging.getLogger("websocket_server")

# 存储所有连接的客户端
clients = {}


async def log_connection(device_id, room_id, identity, client_ip):
    """将新连接记录到数据库并返回连接ID"""
    try:
        conn = db_manager.get_connection()
        if not conn:
            logger.error("Failed to get database connection for logging connection")
            return None

        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO connections (device_id, room_id, identity, client_ip) VALUES (%s, %s, %s, %s)",
            (device_id, room_id, identity, client_ip)
        )

        connection_id = cursor.lastrowid
        conn.commit()

        logger.info(f"Logged connection {connection_id} for device {device_id} in room {room_id}")
        return connection_id

    except Error as e:
        logger.error(f"Database error in log_connection: {e}")
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


async def log_disconnection(connection_id):
    """将断开连接记录到数据库"""
    if not connection_id:
        return

    try:
        conn = db_manager.get_connection()
        if not conn:
            logger.error("Failed to get database connection for logging disconnection")
            return

        cursor = conn.cursor()

        cursor.execute(
            "UPDATE connections SET disconnected_at = NOW() WHERE id = %s",
            (connection_id,)
        )

        conn.commit()
        logger.info(f"Logged disconnection for connection {connection_id}")

    except Error as e:
        logger.error(f"Database error in log_disconnection: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def add_client(client_id, websocket):
    """添加客户端到全局客户端列表"""
    clients[client_id] = websocket
    return len(clients)


def remove_client(client_id):
    """从全局客户端列表中移除客户端"""
    if client_id in clients:
        del clients[client_id]
        logger.info(f"Removed client {client_id} from clients list")
        return True
    return False


def get_client_count():
    """获取当前连接的客户端数量"""
    return len(clients)
