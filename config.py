import logging
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'websocketdata',
    'password': '31c25f8f3a8fb9fe',  # 请替换为实际密码
    'database': 'websocketdata',
    'port': 3306
}

# 服务器配置
SERVER_CONFIG = {
    'host': '0.0.0.0',
    'port': 8765
}


# 日志配置
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("websocket_server")
