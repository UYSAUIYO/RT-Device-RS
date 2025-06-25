import json
import logging
import websockets
import connection_manager
import room_manager
import message_handler

logger = logging.getLogger("websocket_server")

async def handle_client(websocket):
    """处理客户端连接"""
    # 为此连接生成唯一的客户端ID
    client_id = id(websocket)
    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
    connection_manager.add_client(client_id, websocket)

    # 这些将在客户端识别后设置
    device_id = None
    room_id = None
    identity = None
    connection_id = None

    logger.info(f"New connection established - Connection ID: {client_id}, IP: {client_ip}")

    try:
        # 发送连接成功消息
        connection_msg = {"type": "connection", "message": "Connected successfully"}
        await websocket.send(json.dumps(connection_msg))
        logger.info(f"Sent connection success message to connection {client_id}")

        # 等待客户端发送身份信息
        identity_msg = await websocket.recv()
        logger.info(f"Received from connection {client_id}: {identity_msg}")

        try:
            identity_data = json.loads(identity_msg)
            identity = identity_data.get("identity")

            if not identity:
                error_msg = {"type": "error", "message": "Missing identity field"}
                await websocket.send(json.dumps(error_msg))
                logger.warning(f"Missing identity field from connection {client_id}")
                return

            # 从身份消息中提取设备ID
            device_id = identity_data.get("device_id")
            if not device_id:
                error_msg = {"type": "error", "message": "Missing device_id field"}
                await websocket.send(json.dumps(error_msg))
                logger.warning(f"Missing device_id field from connection {client_id}")
                return

            # 检查客户端是否想加入特定房间
            specified_room_id = identity_data.get("room_id")

            logger.info(
                f"Connection {client_id} identified as device: {device_id}, identity: {identity}, specified room: {specified_room_id}")

            # 获取此设备的房间（现有、新的或指定的）
            room_id, is_new_device, room_status = await room_manager.get_or_create_room_for_device(
                device_id, identity, specified_room_id
            )

            if room_status == "room_not_found":
                error_msg = {"type": "error", "message": f"Room {specified_room_id} does not exist"}
                await websocket.send(json.dumps(error_msg))
                logger.warning(f"Device {device_id} tried to join non-existent room {specified_room_id}")
                return

            # 记录此连接
            connection_id = await connection_manager.log_connection(device_id, room_id, identity, client_ip)

            # 将客户端添加到内存中的房间
            room_manager.add_client_to_room(room_id, client_id, websocket, identity, device_id)

            # 发送房间分配消息
            room_msg = {
                "type": "room",
                "room_id": room_id,
                "status": room_status,
                "message": f"{room_status}: joined room {room_id}"
            }
            await websocket.send(json.dumps(room_msg))
            logger.info(f"Client {client_id} (device {device_id}) joined room {room_id} with status: {room_status}")

            # 处理消息
            # 在 handle_client 函数中的消息处理循环部分
            async for message in websocket:
                logger.info(
                    f"Received message from client {client_id} (device {device_id}) in room {room_id}: {message}")

                try:
                    data = json.loads(message)

                    # 检查这是否是房间查询命令
                    if data.get("type") == "query_room":
                        await message_handler.handle_room_query(websocket, client_id, device_id, room_id)
                    else:
                        # 转发消息
                        success, msg = await message_handler.forward_message(data, room_id, client_id, device_id)
                        if not success:
                            error_response = {
                                "type": "error",
                                "message": msg
                            }
                            await websocket.send(json.dumps(error_response))

                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from client {client_id}: {message}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }))
                except Exception as e:
                    logger.error(f"Error processing message from client {client_id}: {str(e)}")


        except json.JSONDecodeError:
            logger.error(f"Invalid JSON for identity from client {client_id}: {identity_msg}")
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON format for identity"}))
        except Exception as e:
            logger.error(f"Error processing identity for client {client_id}: {str(e)}")

    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"Connection closed with client {client_id}: code={e.code}, reason='{e.reason}'")
    except Exception as e:
        logger.error(f"Unexpected error with client {client_id}: {str(e)}")
    finally:
        # 记录断开连接
        if connection_id:
            await connection_manager.log_disconnection(connection_id)

        # 清理连接
        connection_manager.remove_client(client_id)

        # 从房间中移除（但不删除房间）
        if room_id:
            room_manager.remove_client_from_room(room_id, client_id)
