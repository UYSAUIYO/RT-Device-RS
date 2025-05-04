import asyncio
import json
import websockets
import logging
import datetime
import sys
import random
import string
import mysql.connector
from mysql.connector import pooling
from mysql.connector import Error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("websocket_server")

# Store all connected clients
clients = {}
# Store room information
rooms = {}

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'websocketdata',
    'password': 'password',  # 请替换为实际密码
    'database': 'websocketdata',
    'port': 3306
}

# Create connection pool
try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="websocket_pool",
        pool_size=5,
        **DB_CONFIG
    )
    logger.info("Database connection pool created successfully")
    
    # Initialize database tables if they don't exist
    conn = connection_pool.get_connection()
    cursor = conn.cursor()
    
    # Create tables
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
    
except Error as e:
    logger.error(f"Error creating database connection pool: {e}")
    sys.exit(1)

def generate_room_id():
    """Generate a random 8-character room ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def get_or_create_room_for_device(device_id, identity, specified_room_id=None):
    """
    Get existing room for device or create a new one if the device is connecting for the first time.
    If specified_room_id is provided, join that room instead.
    Returns room_id, is_new_device, room_status
    """
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if specified room ID exists
        if specified_room_id:
            cursor.execute("SELECT room_id FROM rooms WHERE room_id = %s", (specified_room_id,))
            existing_room = cursor.fetchone()
            
            if existing_room:
                # Room exists, join it
                room_id = specified_room_id
                
                # Check if this is a new device
                cursor.execute("SELECT device_id FROM devices WHERE device_id = %s", (device_id,))
                device = cursor.fetchone()
                
                # Update or create device record
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
                
                # Initialize room in memory if not exists
                if room_id not in rooms:
                    rooms[room_id] = {}
                
                logger.info(f"Device {device_id} joined specified room {room_id}")
                return room_id, is_new_device, "joined_existing"
            else:
                logger.warning(f"Specified room {specified_room_id} does not exist")
                return None, None, "room_not_found"
        
        # No specified room, use automatic assignment logic
        cursor.execute("SELECT last_room_id FROM devices WHERE device_id = %s", (device_id,))
        device = cursor.fetchone()
        
        if device and device['last_room_id']:
            # Device exists and has a room, check if room exists in memory
            room_id = device['last_room_id']
            if room_id not in rooms:
                rooms[room_id] = {}
            
            # Update device's last connected time and identity
            cursor.execute(
                "UPDATE devices SET last_connected_at = NOW(), last_identity = %s WHERE device_id = %s",
                (identity, device_id)
            )
            conn.commit()
            
            logger.info(f"Device {device_id} reconnected to existing room {room_id}")
            return room_id, False, "reconnected"
        else:
            # Device is new or doesn't have a room yet, create a new room
            while True:
                new_room_id = generate_room_id()
                # Check if room ID already exists
                cursor.execute("SELECT room_id FROM rooms WHERE room_id = %s", (new_room_id,))
                if not cursor.fetchone():
                    break
            
            # Create new room in database
            cursor.execute("INSERT INTO rooms (room_id) VALUES (%s)", (new_room_id,))
            
            # Create/update device record
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
            
            # Initialize room in memory
            rooms[new_room_id] = {}
            
            logger.info(f"Created new room {new_room_id} for device {device_id}")
            return new_room_id, (not device), "created_new"
            
    except Error as e:
        logger.error(f"Database error in get_or_create_room: {e}")
        return generate_room_id(), True, "error"  # Fallback to memory-only room if DB fails
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

async def log_connection(device_id, room_id, identity, client_ip):
    """Log a new connection to the database and return the connection ID"""
    try:
        conn = connection_pool.get_connection()
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
    """Log a disconnection to the database"""
    if not connection_id:
        return
        
    try:
        conn = connection_pool.get_connection()
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

async def log_message(from_device_id, to_device_id, room_id, message_content):
    """Log a message to the database"""
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO messages (from_device_id, to_device_id, room_id, message_content) VALUES (%s, %s, %s, %s)",
            (from_device_id, to_device_id, room_id, message_content)
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
    """Log a room query to the database"""
    try:
        conn = connection_pool.get_connection()
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

async def handle_client(websocket):
    # Generate unique client ID for this connection
    client_id = id(websocket)
    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
    clients[client_id] = websocket
    
    # These will be set after client identification
    device_id = None
    room_id = None
    identity = None
    connection_id = None
    
    logger.info(f"New connection established - Connection ID: {client_id}, IP: {client_ip}")
    
    try:
        # Send connection success message
        connection_msg = {"type": "connection", "message": "Connected successfully"}
        await websocket.send(json.dumps(connection_msg))
        logger.info(f"Sent connection success message to connection {client_id}")

        # Wait for client to send identity information
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
            
            # Extract device ID from the identity message
            device_id = identity_data.get("device_id")
            if not device_id:
                error_msg = {"type": "error", "message": "Missing device_id field"}
                await websocket.send(json.dumps(error_msg))
                logger.warning(f"Missing device_id field from connection {client_id}")
                return
                
            # Check if client wants to join a specific room
            specified_room_id = identity_data.get("room_id")
            
            logger.info(f"Connection {client_id} identified as device: {device_id}, identity: {identity}, specified room: {specified_room_id}")
            
            # Get room for this device (existing, new, or specified)
            room_id, is_new_device, room_status = await get_or_create_room_for_device(device_id, identity, specified_room_id)
            
            if room_status == "room_not_found":
                error_msg = {"type": "error", "message": f"Room {specified_room_id} does not exist"}
                await websocket.send(json.dumps(error_msg))
                logger.warning(f"Device {device_id} tried to join non-existent room {specified_room_id}")
                return
            
            # Log this connection
            connection_id = await log_connection(device_id, room_id, identity, client_ip)
            
            # Add client to room in memory
            if room_id not in rooms:
                rooms[room_id] = {}
                
            rooms[room_id][client_id] = {
                "websocket": websocket, 
                "identity": identity,
                "device_id": device_id
            }
            
            # Log current room state
            room_clients = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in rooms[room_id].items()]
            logger.info(f"Room {room_id} now has clients: {', '.join(room_clients)}")

            # Send room assignment message
            room_msg = {
                "type": "room", 
                "room_id": room_id,
                "status": room_status,
                "message": f"{room_status}: joined room {room_id}"
            }
            await websocket.send(json.dumps(room_msg))
            logger.info(f"Client {client_id} (device {device_id}) joined room {room_id} with status: {room_status}")

            # Process messages
            async for message in websocket:
                logger.info(f"Received message from client {client_id} (device {device_id}) in room {room_id}: {message}")
                
                try:
                    data = json.loads(message)
                    
                    # Check if this is a room query command
                    if data.get("type") == "query_room":
                        # Log the query
                        await log_room_query(device_id, room_id)
                        
                        # Get all clients in the room except the requester
                        room_info = []
                        for cid, client in rooms[room_id].items():
                            if cid != client_id:
                                room_info.append({
                                    "device_id": client["device_id"],
                                    "identity": client["identity"]
                                })
                        
                        # Send room information back to the client
                        query_response = {
                            "type": "room_info",
                            "room_id": room_id,
                            "total_clients": len(rooms[room_id]),
                            "clients": room_info
                        }
                        await websocket.send(json.dumps(query_response))
                        logger.info(f"Sent room query response to client {client_id} (device {device_id})")
                    else:
                        # Forward message to other users in the room
                        for cid, client in rooms[room_id].items():
                            if cid != client_id:
                                await client["websocket"].send(json.dumps(data))
                                # Log message in database
                                await log_message(
                                    device_id, 
                                    client["device_id"], 
                                    room_id, 
                                    message
                                )
                                logger.info(f"Forwarded message from {device_id} to {client['device_id']} in room {room_id}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from client {client_id}: {message}")
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON format"}))
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
        # Log the disconnection
        if connection_id:
            await log_disconnection(connection_id)
            
        # Clean up connection
        if client_id in clients:
            del clients[client_id]
            logger.info(f"Removed client {client_id} from clients list")
            
        # Remove from room (but don't delete room)
        if room_id and room_id in rooms and client_id in rooms[room_id]:
            del rooms[room_id][client_id]
            logger.info(f"Removed client {client_id} from room {room_id}")
            
            # Log remaining clients in the room
            if rooms[room_id]:
                remaining = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in rooms[room_id].items()]
                logger.info(f"Room {room_id} now has clients: {', '.join(remaining)}")

async def main():
    host = "0.0.0.0"
    port = 8765
    
    logger.info(f"Starting WebSocket server on {host}:{port}")
    logger.info(f"Server time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("Room setup: Devices can either be auto-assigned to rooms or specify a room ID")
    
    server = await websockets.serve(handle_client, host, port)
    logger.info(f"WebSocket server is running at ws://{host}:{port}")
    
    # Print server status periodically
    async def status_reporter():
        while True:
            await asyncio.sleep(60)  # Report every minute
            logger.info(f"Server status: {len(clients)} clients connected, {len(rooms)} active rooms")
            for rid, room in rooms.items():
                clients_in_room = [f"{cid}({client['device_id']}:{client['identity']})" for cid, client in room.items()]
                logger.info(f"Room {rid}: {', '.join(clients_in_room)}")
    
    # Start the status reporter
    asyncio.create_task(status_reporter())
    
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
