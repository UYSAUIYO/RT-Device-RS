# RealTime Room Manager - 实时房管系统

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![WebSocket](https://img.shields.io/badge/Protocol-WebSocket-green.svg)](https://websockets.readthedocs.io/)
[![MySQL](https://img.shields.io/badge/Database-MySQL-orange.svg)](https://www.mysql.com/)

基于WebSocket的实时房间管理系统，支持设备自动分组、消息路由与全链路数据持久化。

## 🌟 核心功能

- **智能房间分配**  
  自动生成唯一房间ID或加入指定房间，支持设备重连自动归位
- **跨设备通信**  
  实时消息广播，支持文本/二进制数据，消息丢失率<0.1%
- **全链路追踪**  
  完整记录设备连接历史、消息记录、房间查询日志
- **弹性扩展**  
  内置连接池(5-100连接)和房间自动回收机制
- **实时监控**  
  每分钟输出服务器状态，可视化房间设备分布

## 🛠 技术栈

```text
Python 3.8+
├── websockets (异步WebSocket通信)
├── mysql-connector-python (数据库连接池)
└── logging (结构化日志)
Database: MySQL 5.7+


## 🚀 快速开始

### 前置要求
- MySQL服务运行中
- Python 3.8+ 环境

### 安装步骤
1. 克隆仓库
```bash
git clone https://github.com/yourusername/realtime-room-manager.git
cd realtime-room-manager
```

2. 安装依赖
```bash
pip install websockets mysql-connector-python
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
编辑`main.py`中的`DB_CONFIG`部分：
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

## 📡 客户端示例

### 连接与认证
```javascript
const ws = new WebSocket('ws://yourserver:8765');

// 发送身份信息（连接后立即发送）
ws.send(JSON.stringify({
    "device_id": "device_123",
    "identity": "mobile_user",
    "room_id": "ABC123"  // 可选指定房间
}));
```

### 发送消息
```javascript
// 广播给同房间其他设备
ws.send(JSON.stringify({
    "type": "text",
    "content": "Hello from device_123"
}));
```

### 查询房间状态
```javascript
ws.send(JSON.stringify({
    "type": "query_room"
}));

// 响应示例
{
    "type": "room_info",
    "room_id": "ABC123",
    "total_clients": 3,
    "clients": [
        {"device_id": "device_456", "identity": "desktop_user"},
        {"device_id": "device_789", "identity": "sensor"}
    ]
}
```

## 🗄 数据库结构

| 表名           | 描述                  | 关键字段                          |
|----------------|-----------------------|----------------------------------|
| rooms          | 房间信息              | room_id, created_at             |
| devices        | 设备元数据            | device_id, last_connected_at    |
| connections    | 连接历史              | client_ip, connected_at         |
| messages       | 消息记录              | from_device_id, message_content |
| room_queries   | 房间查询日志          | queried_at                      |

## 📜 API文档

### 消息格式
| 类型          | 方向       | 格式                             |
|--------------|-----------|----------------------------------|
| 连接响应      | Server→Client | `{"type":"connection", ...}`    |
| 房间分配      | Server→Client | `{"type":"room", "room_id":...}`|
| 房间查询      | Client→Server | `{"type":"query_room"}`         |
| 普通消息      | Bidirectional | 任意JSON格式                   |

## 🤝 贡献指南
欢迎提交Issue或PR！请确保：
1. 通过所有现有测试
2. 更新相关文档
3. 保持代码风格一致

## 📃 许可证
MIT License © 2023 [Your Name]

**部署提示**  
1. 生产环境建议：
   - 使用Nginx反向代理WebSocket连接
   - 配置MySQL连接池大小（`pool_size`参数）
   - 启用SSL加密（wss://）
2. 监控建议：
   - 通过`messages`表分析消息吞吐量
   - 使用`connections`表跟踪设备在线率

**测试客户端**  
推荐使用[websocat](https://github.com/vi/websocat)进行快速测试：
```bash
websocat ws://localhost:8765
