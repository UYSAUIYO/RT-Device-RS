import random
import string
import logging
from mysql.connector import Error
import db_manager

logger = logging.getLogger("websocket_server")

# 存储房间信息
rooms = {}


def generate_room_id():
    """生成一个随机的8字符房间ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def get_or_create_room_for_device(device_id, identity, specified_room_id=None):
    """
    获取设备的现有房间或创建新房间（如果设备是首次连接）。
    如果提供了specified_room_id，则加入该房间。
    返回 room_id, is_new_device, room_status
    """
    try:
        conn = db_manager.get_connection()
        if not conn:
            # 数据库连接失败，使用内存中的房间作为回退
            new_room_id = generate_room_id()
            if new_room_id not in rooms:
                rooms[new_room_id] = {}
            return new_room_id, True, "created_new_fallback"

        cursor = conn.cursor(dictionary=True)

        # 检查指定的房间ID是否存在
        if specified_room_id:
            cursor.execute("SELECT room_id FROM rooms WHERE room_id = %s", (specified_room_id,))
            existing_room = cursor.fetchone()

            if existing_room:
                # 房间存在，加入它
                room_id = specified_room_id

                # 检查这是否是一个新设备
                cursor.execute("SELECT device_id FROM devices WHERE device_id = %s", (device_id,))
                device = cursor.fetchone()

                # 更新或创建设备记录
                if device:
                    cursor.execute(
                        "UPDATE devices SET last_connected_at = NOW(), last_room_id = %s, last_identity = %s WHERE device_id = %s",
                        (room_id, identity, device_id)
                    )
                    is_new_device = False
                else:
                    cursor.execute(
                        "INSERT INTO devices (device_id, last_room_id, last_identity) VALUES (%s, %s, %s)",
                        (device_id, room_id, identity)
                    )
                    is_new_device = True

                conn.commit()

                # 如果内存中不存在房间，则初始化
                if room_id not in rooms:
                    rooms[room_id] = {}

                logger.info(f"Device {device_id} joined specified room {room_id}")
                return room_id, is_new_device, "joined_existing"
            else:
                logger.warning(f"Specified room {specified_room_id} does not exist")
                return None, None, "room_not_found"

        # 没有指定房间，使用自动分配逻辑
        cursor.execute("SELECT last_room_id FROM devices WHERE device_id = %s", (device_id,))
        device = cursor.fetchone()

        if device and device['last_room_id']:
            # 设备存在并且有一个房间，检查房间是否存在于内存中
            room_id = device['last_room_id']
            if room_id not in rooms:
                rooms[room_id] = {}

            # 更新设备的最后连接时间和身份
            cursor.execute(
                "UPDATE devices SET last_connected_at = NOW(), last_identity = %s WHERE device_id = %s",
                (identity, device_id)
            )
            conn.commit()

            logger.info(f"Device {device_id} reconnected to existing room {room_id}")
            return room_id, False, "reconnected"
        else:
            # 设备是新的或者还没有房间，创建一个新房间
            while True:
                new_room_id = generate_room_id()
                # 检查房间ID是否已经存在
                cursor.execute("SELECT room_id FROM rooms WHERE room_id = %s", (new_room_id,))
                if not cursor.fetchone():
                    break

            # 在数据库中创建新房间
            cursor.execute("INSERT INTO rooms (room_id) VALUES (%s)", (new_room_id,))

            # 创建/更新设备记录
            if device:
                cursor.execute(
                    "UPDATE devices SET last_connected_at = NOW(), last_room_id = %s, last_identity = %s WHERE device_id = %s",
                    (new_room_id, identity, device_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO devices (device_id, last_room_id, last_identity) VALUES (%s, %s, %s)",
                    (device_id, new_room_id, identity)
                )

            conn.commit()

            # 在内存中初始化房间
            rooms[new_room_id] = {}

            logger.info(f"Created new room {new_room_id} for device {device_id}")
            return new_room_id, (not device), "created_new"

    except Error as e:
        logger.error(f"Database error in get_or_create_room: {e}")
        # 数据库失败时的回退到仅内存房间
        new_room_id = generate_room_id()
        if new_room_id not in rooms:
            rooms[new_room_id] = {}
        return new_room_id, True, "error"
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def get_room_clients(room_id, exclude_client_id=None):
    """获取房间中的所有客户端，可选择排除特定客户端"""
    if room_id not in rooms:
        return []

    room_info = []
    for cid, client in rooms[room_id].items():
        if exclude_client_id is None or cid != exclude_client_id:
            room_info.append({
                "device_id": client["device_id"],
                "identity": client["identity"]
            })
    return room_info


def add_client_to_room(room_id, client_id, websocket, identity, device_id):
    """将客户端添加到房间"""
    if room_id not in rooms:
        rooms[room_id] = {}

    rooms[room_id][client_id] = {
        "websocket": websocket,
        "identity": identity,
        "device_id": device_id
    }

    # 记录当前房间状态
    room_clients = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in rooms[room_id].items()]
    logger.info(f"Room {room_id} now has clients: {', '.join(room_clients)}")


def remove_client_from_room(room_id, client_id):
    """从房间中移除客户端"""
    if room_id in rooms and client_id in rooms[room_id]:
        del rooms[room_id][client_id]
        logger.info(f"Removed client {client_id} from room {room_id}")

        # 记录房间中剩余的客户端
        if rooms[room_id]:
            remaining = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in rooms[room_id].items()]
            logger.info(f"Room {room_id} now has clients: {', '.join(remaining)}")
        return True
    return False
