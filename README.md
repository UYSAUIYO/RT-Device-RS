# WebSocket Room-Ship Controller Server - 实时房间管理系统

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![WebSocket](https://img.shields.io/badge/Protocol-WebSocket-green.svg)](https://websockets.readthedocs.io/)
[![MySQL](https://img.shields.io/badge/Database-MySQL-orange.svg)](https://www.mysql.com/)

基于WebSocket的实时房间管理系统，支持设备自动分组、广播/定向消息路由与全链路数据持久化。

## 🌟 核心功能

- **智能房间分配**  
  自动生成唯一房间ID或加入指定房间，支持设备重连自动归位
- **双模式消息通信**  
  支持房间内广播消息和设备间定向消息，实时性<100ms
- **消息格式验证**  
  强制JSON格式，内置消息验证机制，确保数据完整性
- **全链路追踪**  
  完整记录设备连接历史、消息记录（含消息类型）、房间查询日志
- **模块化架构**  
  代码按功能模块拆分，便于维护和扩展
- **实时监控**  
  每分钟输出服务器状态，可视化房间设备分布

## 🛠 技术栈与架构

```text
Python 3.8+
├── websockets (异步WebSocket通信)
├── mysql-connector-python (数据库连接池)
└── asyncio (异步编程支持)

模块结构:
├── main.py              # 主程序入口
├── config.py            # 配置管理
├── db_manager.py        # 数据库连接池管理
├── room_manager.py      # 房间逻辑管理
├── connection_manager.py # 连接状态管理
├── message_handler.py   # 消息处理与路由
├── client_handler.py    # 客户端连接处理
└── requirements.txt     # 依赖管理

Database: MySQL 5.7+
```

## 🚀 快速开始

### 前置要求
- MySQL服务运行中
- Python 3.8+ 环境

### 安装步骤
1. 克隆仓库
```bash
git clone https://github.com/yourusername/websocket-room-server.git
cd websocket-room-server
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 数据库配置
```sql
-- 创建专用用户
CREATE USER 'websocketdata'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON websocketdata.* TO 'websocketdata'@'localhost';

-- 创建数据库（表结构会自动初始化）
CREATE DATABASE websocketdata;
```

4. 修改配置  
编辑`config.py`中的`DB_CONFIG`部分：
```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'websocketdata',
    'password': 'yourpassword',  # 改为实际密码
    'database': 'websocketdata',
    'port': 3306
}
```

### 启动服务器
```bash
python main.py
```

服务器将在 `ws://0.0.0.0:8765` 启动

## 📡 客户端使用指南

### 1. 连接与认证
```javascript
const ws = new WebSocket('ws://yourserver:8765');

ws.onopen = function() {
    // 连接成功后发送身份信息
    ws.send(JSON.stringify({
        "device_id": "device_123",
        "identity": "mobile_user",
        "room_id": "ABC123"  // 可选：指定房间ID，不指定则自动分配
    }));
};

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('收到消息:', data);
};
```

### 2. 发送广播消息
```javascript
// 发送给房间内所有其他设备
ws.send(JSON.stringify({
    "type": "message",
    "content": "Hello everyone in the room!",
    "timestamp": new Date().toISOString()
}));
```

### 3. 发送定向消息
```javascript
// 发送给指定设备
ws.send(JSON.stringify({
    "type": "message",
    "content": "Private message for you",
    "target_device_id": "device_456",
    "timestamp": new Date().toISOString()
}));
```

### 4. 查询房间状态
```javascript
// 查询房间内其他设备
ws.send(JSON.stringify({
    "type": "query_room"
}));

// 服务器响应示例
{
    "type": "room_info",
    "room_id": "ABC123",
    "total_clients": 3,
    "clients": [
        {"device_id": "device_456", "identity": "desktop_user"},
        {"device_id": "device_789", "identity": "sensor_node"}
    ]
}
```

### 5. 接收消息格式
```javascript
// 广播消息
{
    "type": "message",
    "content": "Hello everyone!",
    "from_device_id": "device_123",
    "message_type": "broadcast",
    "timestamp": "2024-01-20T12:34:56Z"
}

// 定向消息
{
    "type": "message",
    "content": "Private message",
    "from_device_id": "device_123",
    "message_type": "direct",
    "timestamp": "2024-01-20T12:34:56Z"
}
```

## 🗄 数据库结构

| 表名           | 描述                  | 关键字段                                    |
|----------------|-----------------------|--------------------------------------------|
| rooms          | 房间信息              | room_id(PK), created_at                   |
| devices        | 设备元数据            | device_id(PK), last_connected_at, last_room_id |
| connections    | 连接历史              | device_id, room_id, client_ip, connected_at |
| messages       | 消息记录              | from_device_id, to_device_id, message_type, message_content |
| room_queries   | 房间查询日志          | device_id, room_id, queried_at            |

### 新增字段说明
- `messages.message_type`: 枚举类型 ('broadcast', 'direct')，区分广播和定向消息
- `messages.to_device_id`: 定向消息的目标设备ID，广播消息时为NULL

## 📜 完整API文档

### 服务器→客户端消息

| 消息类型      | 格式                                           | 说明           |
|--------------|-----------------------------------------------|----------------|
| 连接确认      | `{"type":"connection", "message":"Connected successfully"}` | 连接建立成功   |
| 房间分配      | `{"type":"room", "room_id":"ABC123", "status":"created_new"}` | 房间分配结果   |
| 房间信息      | `{"type":"room_info", "room_id":"ABC123", "clients":[...]}` | 房间查询响应   |
| 错误信息      | `{"type":"error", "message":"Error description"}` | 错误提示       |
| 转发消息      | `{"type":"message", "content":"...", "from_device_id":"..."}` | 转发的用户消息 |

### 客户端→服务器消息

| 消息类型      | 必需字段                                       | 可选字段           | 说明           |
|--------------|-----------------------------------------------|-------------------|----------------|
| 身份认证      | `device_id`, `identity`                       | `room_id`         | 连接后首次发送  |
| 广播消息      | `type`, `content`                             | `timestamp`       | 房间内广播      |
| 定向消息      | `type`, `content`, `target_device_id`         | `timestamp`       | 发送给指定设备  |
| 房间查询      | `type: "query_room"`                          | -                 | 查询房间状态    |

### 房间状态说明

| 状态值              | 说明                           |
|--------------------|--------------------------------|
| `created_new`      | 创建了新房间                    |
| `joined_existing`  | 加入了指定的现有房间             |
| `reconnected`      | 重连到之前的房间                |
| `room_not_found`   | 指定的房间不存在                |

## 🔧 配置选项

### 服务器配置 (config.py)
```python
# 服务器配置
SERVER_CONFIG = {
    'host': '0.0.0.0',    # 监听地址
    'port': 8765          # 监听端口
}

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'websocketdata',
    'password': 'password',
    'database': 'websocketdata',
    'port': 3306
}
```

### 连接池配置 (db_manager.py)
```python
connection_pool = pooling.MySQLConnectionPool(
    pool_name="websocket_pool",
    pool_size=5,  # 可根据并发需求调整
    **DB_CONFIG
)
```

## 🧪 测试示例

### 使用websocat测试
```bash
# 安装websocat
cargo install websocat

# 连接服务器
websocat ws://localhost:8765

# 发送身份信息
{"device_id": "test_device", "identity": "test_user"}

# 发送广播消息
{"type": "message", "content": "Hello World"}

# 发送定向消息
{"type": "message", "content": "Private Hello", "target_device_id": "another_device"}

# 查询房间
{"type": "query_room"}
```

### Python客户端示例
```python
import asyncio
import websockets
import json

async def client_example():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        # 发送身份信息
        identity = {
            "device_id": "python_client",
            "identity": "test_script"
        }
        await websocket.send(json.dumps(identity))
        
        # 接收房间分配
        response = await websocket.recv()
        print(f"服务器响应: {response}")
        
        # 发送消息
        message = {
            "type": "message",
            "content": "Hello from Python client"
        }
        await websocket.send(json.dumps(message))
        
        # 持续接收消息
        async for message in websocket:
            data = json.loads(message)
            print(f"收到消息: {data}")

# 运行客户端
asyncio.run(client_example())
```

## 📊 监控与日志

### 日志级别
- **INFO**: 连接状态、房间分配、消息转发
- **WARNING**: 房间不存在、设备未找到
- **ERROR**: 数据库错误、消息格式错误

### 状态监控
服务器每分钟自动输出：
- 当前连接数
- 活跃房间数
- 各房间设备分布

### 数据库监控查询
```sql
-- 查看活跃连接
SELECT device_id, room_id, connected_at 
FROM connections 
WHERE disconnected_at IS NULL;

-- 消息统计
SELECT message_type, COUNT(*) as count 
FROM messages 
GROUP BY message_type;

-- 房间活跃度
SELECT room_id, COUNT(DISTINCT from_device_id) as active_devices
FROM messages 
WHERE sent_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY room_id;
```

## 🚀 部署建议

### 生产环境配置
1. **反向代理**
```nginx
location /ws {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

2. **SSL配置**
```python
# 使用wss://协议
import ssl
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain("cert.pem", "key.pem")
```

3. **系统服务**
```ini
# /etc/systemd/system/websocket-room.service
[Unit]
Description=WebSocket Room Server
After=network.target mysql.service

[Service]
Type=simple
User=websocket
WorkingDirectory=/opt/websocket-room-server
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 🤝 贡献指南

欢迎提交Issue或PR！请确保：
1. 遵循现有代码风格
2. 添加适当的错误处理
3. 更新相关文档
4. 测试新功能

### 开发环境设置
```bash
# 克隆项目
git clone https://github.com/yourusername/websocket-room-server.git

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装开发依赖
pip install -r requirements.txt
```

## 📃 许可证
MIT License © 2024 [Your Name]

---

## 🔗 相关链接
- [WebSocket协议规范](https://tools.ietf.org/html/rfc6455)
- [MySQL连接池文档](https://dev.mysql.com/doc/connector-python/en/connector-python-connection-pooling.html)
- [Python asyncio文档](https://docs.python.org/3/library/asyncio.html)
```

这个更新后的README.md文档包含了：

1. **新功能说明**：定向消息、消息验证、模块化架构
2. **完整的API文档**：包括所有消息格式和状态码
3. **详细的使用示例**：JavaScript和Python

