import logging
import sys
from mysql.connector import pooling, Error
from config import DB_CONFIG

logger = logging.getLogger("websocket_server")

# 数据库连接池
connection_pool = None


def init_database():
    """初始化数据库连接池和必要的表结构"""
    global connection_pool

    try:
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="websocket_pool",
            pool_size=5,
            **DB_CONFIG
        )
        logger.info("Database connection pool created successfully")

        # 初始化数据库表
        conn = connection_pool.get_connection()
        cursor = conn.cursor()

        # 创建表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            room_id VARCHAR(8) PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            device_id VARCHAR(255) PRIMARY KEY,
            first_connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_room_id VARCHAR(8),
            last_identity VARCHAR(255)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS connections (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id VARCHAR(255),
            room_id VARCHAR(8),
            identity VARCHAR(255),
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            disconnected_at TIMESTAMP NULL,
            client_ip VARCHAR(45),
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (room_id) REFERENCES rooms(room_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            from_device_id VARCHAR(255),
            to_device_id VARCHAR(255),
            room_id VARCHAR(8),
            message_content TEXT,
            message_type ENUM('broadcast', 'direct') DEFAULT 'broadcast',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(room_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_queries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            device_id VARCHAR(255),
            room_id VARCHAR(8),
            queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (room_id) REFERENCES rooms(room_id)
        )
        ''')

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Database tables initialized successfully")
        return True

    except Error as e:
        logger.error(f"Error creating database connection pool: {e}")
        return False


def get_connection():
    """获取数据库连接"""
    if connection_pool:
        return connection_pool.get_connection()
    else:
        logger.error("Database connection pool not initialized")
        return None
