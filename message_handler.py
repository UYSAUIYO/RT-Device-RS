import json
import logging
from mysql.connector import Error
import db_manager
import room_manager

logger = logging.getLogger("websocket_server")


async def log_message(from_device_id, to_device_id, room_id, message_content, message_type="broadcast"):
    """将消息记录到数据库"""
    try:
        conn = db_manager.get_connection()
        if not conn:
            logger.error("Failed to get database connection for logging message")
            return

        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO messages (from_device_id, to_device_id, room_id, message_content, message_type) VALUES (%s, %s, %s, %s, %s)",
            (from_device_id, to_device_id, room_id, message_content, message_type)
        )

        conn.commit()

    except Error as e:
        logger.error(f"Database error in log_message: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


async def log_room_query(device_id, room_id):
    """将房间查询记录到数据库"""
    try:
        conn = db_manager.get_connection()
        if not conn:
            logger.error("Failed to get database connection for logging room query")
            return

        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO room_queries (device_id, room_id) VALUES (%s, %s)",
            (device_id, room_id)
        )

        conn.commit()

    except Error as e:
        logger.error(f"Database error in log_room_query: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


async def validate_message(data):
    """验证消息格式"""
    required_fields = ["type", "content"]
    if not all(field in data for field in required_fields):
        return False, "Missing required fields (type, content)"

    if not isinstance(data["content"], (str, dict)):
        return False, "Invalid content format"

    return True, None


async def forward_message(message_data, room_id, sender_client_id, sender_device_id):
    """将消息转发给房间中的指定用户或所有用户"""
    if room_id not in room_manager.rooms:
        logger.warning(f"Attempt to forward message to non-existent room {room_id}")
        return False, "Room not found"

    try:
        # 验证消息格式
        is_valid, error_msg = await validate_message(message_data)
        if not is_valid:
            return False, error_msg

        # 解析消息
        target_device_id = message_data.get("target_device_id")
        message_type = "direct" if target_device_id else "broadcast"

        # 准备发送的消息
        outgoing_message = {
            "type": message_data["type"],
            "content": message_data["content"],
            "from_device_id": sender_device_id,
            "message_type": message_type,
            "timestamp": message_data.get("timestamp", "")
        }

        # 发送消息
        if target_device_id:
            # 定向消息
            sent = False
            for cid, client in room_manager.rooms[room_id].items():
                if client["device_id"] == target_device_id:
                    try:
                        await client["websocket"].send(json.dumps(outgoing_message))
                        await log_message(
                            sender_device_id,
                            target_device_id,
                            room_id,
                            json.dumps(message_data),
                            "direct"
                        )
                        logger.info(
                            f"Sent direct message from {sender_device_id} to {target_device_id} in room {room_id}")
                        sent = True
                        break
                    except Exception as e:
                        logger.error(f"Error sending direct message: {str(e)}")
                        return False, f"Error sending direct message: {str(e)}"

            if not sent:
                return False, f"Target device {target_device_id} not found in room"
        else:
            # 广播消息
            for cid, client in room_manager.rooms[room_id].items():
                if cid != sender_client_id:
                    try:
                        await client["websocket"].send(json.dumps(outgoing_message))
                    except Exception as e:
                        logger.error(f"Error broadcasting message to client {cid}: {str(e)}")
                        continue

            # 记录广播消息
            await log_message(
                sender_device_id,
                None,
                room_id,
                json.dumps(message_data),
                "broadcast"
            )
            logger.info(f"Broadcast message from {sender_device_id} in room {room_id}")

        return True, "Message sent successfully"

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return False, f"Error processing message: {str(e)}"


async def handle_room_query(websocket, client_id, device_id, room_id):
    """处理房间查询请求"""
    # 记录查询
    await log_room_query(device_id, room_id)

    # 获取房间中除了请求者之外的所有客户端
    room_info = room_manager.get_room_clients(room_id, client_id)

    # 将房间信息发送回客户端
    query_response = {
        "type": "room_info",
        "room_id": room_id,
        "total_clients": len(room_manager.rooms.get(room_id, {})),
        "clients": room_info
    }
    await websocket.send(json.dumps(query_response))
    logger.info(f"Sent room query response to client {client_id} (device {device_id})")
