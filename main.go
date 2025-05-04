package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	_ "github.com/go-sql-driver/mysql"
)

// 配置日志
var logger = log.New(os.Stdout, "", log.LstdFlags)

// 客户端连接映射
type Client struct {
	websocket *websocket.Conn
	identity  string
	deviceID  string
}

// 数据库配置
const (
	DBHost     = "localhost"
	DBUser     = "websocketdata"
	DBPassword = "password" // 请替换为实际密码
	DBName     = "websocketdata"
	DBPort     = 3306
)

// 全局变量
var (
	clients     = make(map[uint64]*websocket.Conn)
	rooms       = make(map[string]map[uint64]*Client)
	roomsMutex  = &sync.RWMutex{}
	clientsMutex = &sync.RWMutex{}
	db         *sql.DB
	upgrader   = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool {
			return true // 允许所有来源的连接
		},
	}
)

// 消息类型
type Message struct {
	Type       string      `json:"type"`
	Message    string      `json:"message,omitempty"`
	Identity   string      `json:"identity,omitempty"`
	DeviceID   string      `json:"device_id,omitempty"`
	RoomID     string      `json:"room_id,omitempty"`
	Status     string      `json:"status,omitempty"`
	Clients    interface{} `json:"clients,omitempty"`
	TotalClients int       `json:"total_clients,omitempty"`
}

// 初始化数据库
func initDB() error {
	var err error
	dsn := fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?parseTime=true", 
		DBUser, DBPassword, DBHost, DBPort, DBName)
	
	db, err = sql.Open("mysql", dsn)
	if err != nil {
		return err
	}

	// 设置连接池参数
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(time.Hour)

	// 测试连接
	err = db.Ping()
	if err != nil {
		return err
	}

	logger.Println("数据库连接池创建成功")

	// 初始化数据库表
	err = createTables()
	if err != nil {
		return err
	}

	logger.Println("数据库表初始化成功")
	return nil
}

// 创建数据库表
func createTables() error {
	tables := []string{
		`CREATE TABLE IF NOT EXISTS rooms (
			room_id VARCHAR(8) PRIMARY KEY,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS devices (
			device_id VARCHAR(255) PRIMARY KEY,
			first_connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			last_connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			last_room_id VARCHAR(8),
			last_identity VARCHAR(255)
		)`,
		`CREATE TABLE IF NOT EXISTS connections (
			id INT AUTO_INCREMENT PRIMARY KEY,
			device_id VARCHAR(255),
			room_id VARCHAR(8),
			identity VARCHAR(255),
			connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			disconnected_at TIMESTAMP NULL,
			client_ip VARCHAR(45),
			FOREIGN KEY (device_id) REFERENCES devices(device_id),
			FOREIGN KEY (room_id) REFERENCES rooms(room_id)
		)`,
		`CREATE TABLE IF NOT EXISTS messages (
			id INT AUTO_INCREMENT PRIMARY KEY,
			from_device_id VARCHAR(255),
			to_device_id VARCHAR(255),
			room_id VARCHAR(8),
			message_content TEXT,
			sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (room_id) REFERENCES rooms(room_id)
		)`,
		`CREATE TABLE IF NOT EXISTS room_queries (
			id INT AUTO_INCREMENT PRIMARY KEY,
			device_id VARCHAR(255),
			room_id VARCHAR(8),
			queried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (device_id) REFERENCES devices(device_id),
			FOREIGN KEY (room_id) REFERENCES rooms(room_id)
		)`,
	}

	for _, table := range tables {
		_, err := db.Exec(table)
		if err != nil {
			return err
		}
	}

	return nil
}

// 生成随机房间ID
func generateRoomID() string {
	const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	result := make([]byte, 8)
	for i := range result {
		result[i] = chars[rand.Intn(len(chars))]
	}
	return string(result)
}

// 获取或创建房间
func getOrCreateRoomForDevice(deviceID, identity, specifiedRoomID string) (string, bool, string) {
	roomsMutex.Lock()
	defer roomsMutex.Unlock()

	// 如果指定了房间ID
	if specifiedRoomID != "" {
		// 检查指定房间是否存在
		var exists bool
		err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM rooms WHERE room_id = ?)", specifiedRoomID).Scan(&exists)
		if err != nil {
			logger.Printf("查询房间错误: %v", err)
			return generateRoomID(), true, "error"
		}

		if exists {
			// 房间存在，加入该房间
			roomID := specifiedRoomID

			// 检查这是否是一个新设备
			var deviceExists bool
			err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM devices WHERE device_id = ?)", deviceID).Scan(&deviceExists)
			if err != nil {
				logger.Printf("查询设备错误: %v", err)
				return roomID, true, "error"
			}

			// 更新或创建设备记录
			if deviceExists {
				_, err = db.Exec(
					"UPDATE devices SET last_connected_at = NOW(), last_room_id = ?, last_identity = ? WHERE device_id = ?",
					roomID, identity, deviceID,
				)
				if err != nil {
					logger.Printf("更新设备错误: %v", err)
				}
			} else {
				_, err = db.Exec(
					"INSERT INTO devices (device_id, last_room_id, last_identity) VALUES (?, ?, ?)",
					deviceID, roomID, identity,
				)
				if err != nil {
					logger.Printf("插入设备错误: %v", err)
				}
			}

			// 在内存中初始化房间（如果不存在）
			if _, ok := rooms[roomID]; !ok {
				rooms[roomID] = make(map[uint64]*Client)
			}

			logger.Printf("设备 %s 加入了指定房间 %s", deviceID, roomID)
			return roomID, !deviceExists, "joined_existing"
		} else {
			logger.Printf("指定房间 %s 不存在", specifiedRoomID)
			return "", false, "room_not_found"
		}
	}

	// 未指定房间ID，使用自动分配逻辑
	var lastRoomID sql.NullString
	err := db.QueryRow("SELECT last_room_id FROM devices WHERE device_id = ?", deviceID).Scan(&lastRoomID)
	
	if err == nil && lastRoomID.Valid {
		// 设备存在且有一个房间，检查房间是否存在于内存中
		roomID := lastRoomID.String
		
		// 初始化房间（如果不存在）
		if _, ok := rooms[roomID]; !ok {
			rooms[roomID] = make(map[uint64]*Client)
		}

		// 更新设备最后连接时间和身份
		_, err = db.Exec(
			"UPDATE devices SET last_connected_at = NOW(), last_identity = ? WHERE device_id = ?",
			identity, deviceID,
		)
		if err != nil {
			logger.Printf("更新设备错误: %v", err)
		}

		logger.Printf("设备 %s 重新连接到现有房间 %s", deviceID, roomID)
		return roomID, false, "reconnected"
	} else {
		// 设备是新的或尚未有房间，创建一个新房间
		var newRoomID string
		for {
			newRoomID = generateRoomID()
			// 检查房间ID是否已存在
			var exists bool
			err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM rooms WHERE room_id = ?)", newRoomID).Scan(&exists)
			if err != nil {
				logger.Printf("查询房间错误: %v", err)
				break
			}
			if !exists {
				break
			}
		}

		// 在数据库中创建新房间
		_, err = db.Exec("INSERT INTO rooms (room_id) VALUES (?)", newRoomID)
		if err != nil {
			logger.Printf("创建房间错误: %v", err)
		}

		// 创建/更新设备记录
		if err == sql.ErrNoRows {
			_, err = db.Exec(
				"INSERT INTO devices (device_id, last_room_id, last_identity) VALUES (?, ?, ?)",
				deviceID, newRoomID, identity,
			)
		} else {
			_, err = db.Exec(
				"UPDATE devices SET last_connected_at = NOW(), last_room_id = ?, last_identity = ? WHERE device_id = ?",
				newRoomID, identity, deviceID,
			)
		}
		if err != nil {
			logger.Printf("更新设备错误: %v", err)
		}

		// 在内存中初始化房间
		rooms[newRoomID] = make(map[uint64]*Client)

		logger.Printf("为设备 %s 创建了新房间 %s", deviceID, newRoomID)
		return newRoomID, (err == sql.ErrNoRows), "created_new"
	}
}

// 记录连接
func logConnection(deviceID, roomID, identity, clientIP string) int64 {
	result, err := db.Exec(
		"INSERT INTO connections (device_id, room_id, identity, client_ip) VALUES (?, ?, ?, ?)",
		deviceID, roomID, identity, clientIP,
	)
	if err != nil {
		logger.Printf("记录连接错误: %v", err)
		return 0
	}

	connectionID, err := result.LastInsertId()
	if err != nil {
		logger.Printf("获取连接ID错误: %v", err)
		return 0
	}

	logger.Printf("记录了设备 %s 在房间 %s 的连接 %d", deviceID, roomID, connectionID)
	return connectionID
}

// 记录断开连接
func logDisconnection(connectionID int64) {
	if connectionID == 0 {
		return
	}

	_, err := db.Exec(
		"UPDATE connections SET disconnected_at = NOW() WHERE id = ?",
		connectionID,
	)
	if err != nil {
		logger.Printf("记录断开连接错误: %v", err)
		return
	}

	logger.Printf("记录了连接 %d 的断开", connectionID)
}

// 记录消息
func logMessage(fromDeviceID, toDeviceID, roomID, messageContent string) {
	_, err := db.Exec(
		"INSERT INTO messages (from_device_id, to_device_id, room_id, message_content) VALUES (?, ?, ?, ?)",
		fromDeviceID, toDeviceID, roomID, messageContent,
	)
	if err != nil {
		logger.Printf("记录消息错误: %v", err)
	}
}

// 记录房间查询
func logRoomQuery(deviceID, roomID string) {
	_, err := db.Exec(
		"INSERT INTO room_queries (device_id, room_id) VALUES (?, ?)",
		deviceID, roomID,
	)
	if err != nil {
		logger.Printf("记录房间查询错误: %v", err)
	}
}

// 处理WebSocket连接
func handleWebSocket(w http.ResponseWriter, r *http.Request) {
	// 升级HTTP连接为WebSocket
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		logger.Printf("升级连接错误: %v", err)
		return
	}
	
	// 生成唯一客户端ID
	clientID := uint64(time.Now().UnixNano())
	clientIP := r.RemoteAddr
	if ip := r.Header.Get("X-Real-IP"); ip != "" {
		clientIP = ip
	} else if ip = r.Header.Get("X-Forwarded-For"); ip != "" {
		clientIP = strings.Split(ip, ",")[0]
	}
	
	clientsMutex.Lock()
	clients[clientID] = conn
	clientsMutex.Unlock()
	
	var deviceID, roomID, identity string
	var connectionID int64
	
	logger.Printf("新连接已建立 - 连接ID: %d, IP: %s", clientID, clientIP)
	
	// 发送连接成功消息
	connectionMsg := Message{
		Type:    "connection",
		Message: "Connected successfully",
	}
	err = conn.WriteJSON(connectionMsg)
	if err != nil {
		logger.Printf("发送消息错误: %v", err)
		conn.Close()
		return
	}
	logger.Printf("向连接 %d 发送了连接成功消息", clientID)
	
	// 处理客户端连接
	defer func() {
		// 记录断开连接
		if connectionID > 0 {
			logDisconnection(connectionID)
		}
		
		// 清理连接
		clientsMutex.Lock()
		delete(clients, clientID)
		clientsMutex.Unlock()
		logger.Printf("从客户端列表中移除了客户端 %d", clientID)
		
		// 从房间中移除（但不删除房间）
		if roomID != "" {
			roomsMutex.Lock()
			if room, ok := rooms[roomID]; ok {
				delete(room, clientID)
				
				// 记录房间中剩余的客户端
				if len(room) > 0 {
					var remaining []string
					for cid, client := range room {
						remaining = append(remaining, fmt.Sprintf("%d(%s:%s)", cid, client.deviceID, client.identity))
					}
					logger.Printf("房间 %s 现在的客户端: %s", roomID, strings.Join(remaining, ", "))
				}
			}
			roomsMutex.Unlock()
			logger.Printf("从房间 %s 中移除了客户端 %d", roomID, clientID)
		}
		
		conn.Close()
	}()
	
	// 等待客户端发送身份信息
	_, identityMsg, err := conn.ReadMessage()
	if err != nil {
		logger.Printf("读取消息错误: %v", err)
		return
	}
	logger.Printf("从连接 %d 接收: %s", clientID, string(identityMsg))
	
	var identityData Message
	err = json.Unmarshal(identityMsg, &identityData)
	if err != nil {
		errorMsg := Message{
			Type:    "error",
			Message: "Invalid JSON format for identity",
		}
		conn.WriteJSON(errorMsg)
		logger.Printf("从客户端 %d 接收到无效的JSON身份信息: %v", clientID, err)
		return
	}
	
	identity = identityData.Identity
	if identity == "" {
		errorMsg := Message{
			Type:    "error",
			Message: "Missing identity field",
		}
		conn.WriteJSON(errorMsg)
		logger.Printf("来自连接 %d 的身份字段缺失", clientID)
		return
	}
	
	deviceID = identityData.DeviceID
	if deviceID == "" {
		errorMsg := Message{
			Type:    "error",
			Message: "Missing device_id field",
		}
		conn.WriteJSON(errorMsg)
		logger.Printf("来自连接 %d 的设备ID字段缺失", clientID)
		return
	}
	
	// 检查客户端是否想加入特定房间
	specifiedRoomID := identityData.RoomID
	
	logger.Printf("连接 %d 标识为设备: %s, 身份: %s, 指定房间: %s", clientID, deviceID, identity, specifiedRoomID)
	
	// 获取这个设备的房间（现有的、新的或指定的）
	roomID, isNewDevice, roomStatus := getOrCreateRoomForDevice(deviceID, identity, specifiedRoomID)
	
	if roomStatus == "room_not_found" {
		errorMsg := Message{
			Type:    "error",
			Message: fmt.Sprintf("Room %s does not exist", specifiedRoomID),
		}
		conn.WriteJSON(errorMsg)
		logger.Printf("设备 %s 尝试加入不存在的房间 %s", deviceID, specifiedRoomID)
		return
	}
	
	// 记录这个连接
	connectionID = logConnection(deviceID, roomID, identity, clientIP)
	
	// 将客户端添加到内存中的房间
	roomsMutex.Lock()
	if _, ok := rooms[roomID]; !ok {
		rooms[roomID] = make(map[uint64]*Client)
	}
	
	rooms[roomID][clientID] = &Client{
		websocket: conn,
		identity:  identity,
		deviceID:  deviceID,
	}
	
	// 记录当前房间状态
	var roomClients []string
	for cid, client := range rooms[roomID] {
		roomClients = append(roomClients, fmt.Sprintf("%d(%s:%s)", cid, client.deviceID, client.identity))
	}
	logger.Printf("房间 %s 现在的客户端: %s", roomID, strings.Join(roomClients, ", "))
	roomsMutex.Unlock()
	
	// 发送房间分配消息
	roomMsg := Message{
		Type:    "room",
		RoomID:  roomID,
		Status:  roomStatus,
		Message: fmt.Sprintf("%s: joined room %s", roomStatus, roomID),
	}
	err = conn.WriteJSON(roomMsg)
	if err != nil {
		logger.Printf("发送房间消息错误: %v", err)
		return
	}
	logger.Printf("客户端 %d (设备 %s) 加入房间 %s 状态: %s", clientID, deviceID, roomID, roomStatus)
	
	// 处理消息
	for {
		_, message, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				logger.Printf("读取消息错误: %v", err)
			}
			break
		}
		logger.Printf("从客户端 %d (设备 %s) 在房间 %s 收到消息: %s", clientID, deviceID, roomID, string(message))
		
		var data Message
		err = json.Unmarshal(message, &data)
		if err != nil {
			errorMsg := Message{
				Type:    "error",
				Message: "Invalid JSON format",
			}
			conn.WriteJSON(errorMsg)
			logger.Printf("从客户端 %d 收到无效的JSON: %s", clientID, string(message))
			continue
		}
		
		// 检查这是否是房间查询命令
		if data.Type == "query_room" {
			// 记录查询
			logRoomQuery(deviceID, roomID)
			
			// 获取房间中除请求者外的所有客户端
			roomsMutex.RLock()
			var roomInfo []map[string]string
			
			if room, ok := rooms[roomID]; ok {
				for cid, client := range room {
					if cid != clientID {
						roomInfo = append(roomInfo, map[string]string{
							"device_id": client.deviceID,
							"identity":  client.identity,
						})
					}
				}
			}
			totalClients := len(rooms[roomID])
			roomsMutex.RUnlock()
			
			// 向客户端发送房间信息
			queryResponse := Message{
				Type:         "room_info",
				RoomID:       roomID,
				TotalClients: totalClients,
				Clients:      roomInfo,
			}
			err = conn.WriteJSON(queryResponse)
			if err != nil {
				logger.Printf("发送房间查询响应错误: %v", err)
				continue
			}
			logger.Printf("向客户端 %d (设备 %s) 发送了房间查询响应", clientID, deviceID)
		} else {
			// 将消息转发给房间中的其他用户
			roomsMutex.RLock()
			if room, ok := rooms[roomID]; ok {
				for cid, client := range room {
					if cid != clientID {
						err = client.websocket.WriteJSON(data)
						if err != nil {
							logger.Printf("发送消息到客户端 %d 错误: %v", cid, err)
							continue
						}
						
						// 记录消息到数据库
						messageStr, _ := json.Marshal(data)
						logMessage(deviceID, client.deviceID, roomID, string(messageStr))
						
						logger.Printf("转发消息从 %s 到 %s 在房间 %s", deviceID, client.deviceID, roomID)
					}
				}
			}
			roomsMutex.RUnlock()
		}
	}
}

// 状态报告器
func statusReporter() {
	for {
		time.Sleep(60 * time.Second) // 每分钟报告一次
		
		clientsMutex.RLock()
		numClients := len(clients)
		clientsMutex.RUnlock()
		
		roomsMutex.RLock()
		numRooms := len(rooms)
		logger.Printf("服务器状态: %d 个客户端连接, %d 个活跃房间", numClients, numRooms)
		
		for rid, room := range rooms {
			var clientsInRoom []string
			for cid, client := range room {
				clientsInRoom = append(clientsInRoom, fmt.Sprintf("%d(%s:%s)", cid, client.deviceID, client.identity))
			}
			logger.Printf("房间 %s: %s", rid, strings.Join(clientsInRoom, ", "))
		}
		roomsMutex.RUnlock()
	}
}

func main() {
	// 初始化随机数生成器
	rand.Seed(time.Now().UnixNano())
	
	// 初始化数据库
	err := initDB()
	if err != nil {
		logger.Fatalf("初始化数据库错误: %v", err)
	}
	
	// 设置WebSocket处理程序
	http.HandleFunc("/", handleWebSocket)
	
	// 启动状态报告器
	go statusReporter()
	
	// 启动服务器
	host := "0.0.0.0"
	port := 8765
	addr := fmt.Sprintf("%s:%d", host, port)
	
	logger.Printf("开始WebSocket服务器，监听 %s", addr)
	logger.Printf("服务器时间: %s", time.Now().Format("2006-01-02 15:04:05"))
	logger.Println("房间设置: 设备可以自动分配到房间或指定房间ID")
	
	logger.Println("WebSocket房间传输控制服务器启动中...")
	err = http.ListenAndServe(addr, nil)
	if err != nil {
		logger.Fatalf("服务器错误: %v", err)
	}
}
