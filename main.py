import asyncio
import datetime
import websockets
import logging
import sys
from config import setup_logging, SERVER_CONFIG
import db_manager
import room_manager
import connection_manager
import client_handler

# 配置日志
logger = setup_logging()


async def status_reporter():
    """定期报告服务器状态"""
    while True:
        await asyncio.sleep(60)  # 每分钟报告一次
        client_count = connection_manager.get_client_count()
        room_count = len(room_manager.rooms)
        logger.info(f"Server status: {client_count} clients connected, {room_count} active rooms")

        for rid, room in room_manager.rooms.items():
            clients_in_room = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in room.items()]
            if clients_in_room:
                logger.info(f"Room {rid}: {', '.join(clients_in_room)}")


async def main():
    """主程序入口点"""
    host = SERVER_CONFIG['host']
    port = SERVER_CONFIG['port']

    # 初始化数据库
    if not db_manager.init_database():
        logger.error("Failed to initialize database. Exiting...")
        return

    logger.info(f"Starting WebSocket server on {host}:{port}")
    logger.info(f"Server time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("Room setup: Devices can either be auto-assigned to rooms or specify a room ID")

    # 启动WebSocket服务器
    server = await websockets.serve(client_handler.handle_client, host, port)
    logger.info(f"WebSocket server is running at ws://{host}:{port}")

    # 启动状态报告器
    asyncio.create_task(status_reporter())

    # 等待服务器关闭
    await server.wait_closed()


if __name__ == "__main__":
    try:
        logger.info("WebSocket Room-Ship Controller Server starting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested via KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
    finally:
        logger.info("Server shutdown complete")
