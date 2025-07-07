import socket
import threading
from pymongo import MongoClient, database, collection
from datetime import datetime
import json
from typing import Optional

def get_local_ip() -> str:
    s: Optional[socket.socket] = None
    ip_address = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_address = s.getsockname()[0]
    except Exception as e:
        print(f"[IP DISCOVERY ERROR] Could not determine local IP: {e}. Falling back to {ip_address}")
    finally:
        if s:
            s.close()
    return ip_address
#app.py mongo connect
MONGO_URI: str = "mongodb://localhost:27017/"
DATABASE_NAME: str = "sensor_data"
COLLECTION_NAME: str = "readings"
#mongodb init
mongo_client: Optional[MongoClient] = None
mongo_db: Optional[database.Database] = None
mongo_collection: Optional[collection.Collection] = None

try:
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client[DATABASE_NAME]
    mongo_client.admin.command('ping')
    mongo_collection = mongo_db[COLLECTION_NAME]
    print(f"[MONGO] Socket server successfully connected to MongoDB at {MONGO_URI} and database '{DATABASE_NAME}'.")
except Exception as e:
    print(f"[MONGO ERROR] Socket server could not connect to MongoDB: {e}")
    mongo_client = None
    mongo_db = None
    mongo_collection = None

active_connections_lock = threading.Lock()
active_connections = 0

PORT = 5500
SERVER = get_local_ip()
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(ADDR)

def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    global active_connections
    with active_connections_lock:
        active_connections += 1

    print(f"[NEW CONNECTION] {addr} connected.")
    print(f"[ACTIVE CONNECTIONS] {active_connections}")

    connected = True
    while connected:
        try:
            # 1kB max threshold
            msg_bytes = conn.recv(1024)
            if not msg_bytes:
                print(f"[{addr}] Connection closed by client.")
                break

            msg = msg_bytes.decode(FORMAT).strip()

            if not msg:
                print(f"[{addr}] Received empty message, ignoring.")
                continue

            if msg == DISCONNECT_MESSAGE:
                connected = False
                print(f"[{addr}] Client requested disconnect.")
                break

            print(f"[{addr}] Received: '{msg}'")

            if mongo_collection is not None:
                try:
                    temperature: Optional[float] = None
                    humidity: Optional[float] = None

                    # attempt to save as json first
                    if msg.startswith('{') and msg.endswith('}'):
                        try:
                            data = json.loads(msg)
                            temperature = data.get('temperature')
                            humidity = data.get('humidity')
                            if not (isinstance(temperature, (int, float)) and isinstance(humidity, (int, float))):
                                raise ValueError("JSON message missing valid 'temperature' or 'humidity' values.")
                        except json.JSONDecodeError:
                            pass

                    # parse as "temperature!humidity"
                    if temperature is None or humidity is None:
                        if '!' in msg:
                            parts = msg.split('!')
                            if len(parts) == 2:
                                try:
                                    temperature = float(parts[0].strip())
                                    humidity = float(parts[1].strip())
                                except ValueError:
                                    raise ValueError("'!'-separated message contains non-numeric values.")
                            else:
                                raise ValueError("'!'-separated message does not have exactly two parts (temperature!humidity).")
                    
                    if temperature is None or humidity is None:
                         raise ValueError("Unrecognized message format. Expected 'temperature!humidity' or JSON.")

                    sensor_reading = {
                        "temperature": temperature,
                        "humidity": humidity,
                        "timestamp": datetime.now(),
                        "client_ip": str(addr[0]),
                        "client_port": addr[1]
                    }

                    mongo_collection.insert_one(sensor_reading)
                    print(f"[{addr}] Saved to DB: Temp={temperature}°C, Hum={humidity}%")
                    conn.send("Msg and data saved".encode(FORMAT))
                except ValueError as ve:
                    print(f"[ERROR] Data parsing error from {addr}: {ve} (Message: '{msg}')")
                    conn.send(f"Error: Invalid data format ({ve})".encode(FORMAT))
                except Exception as mongo_err:
                    print(f"[ERROR] MongoDB insert error for {addr}: {mongo_err} (Message: '{msg}')")
                    conn.send("Error: Database save failed".encode(FORMAT))
            else:
                conn.send("Msg received (DB not connected)".encode(FORMAT))

        except (BrokenPipeError, ConnectionResetError):
            print(f"[WARNING] Connection reset by peer {addr}")
            break
        except Exception as e:
            print(f"[ERROR] Unexpected error with client {addr}: {e}")
            break

    conn.close()
    with active_connections_lock:
        active_connections -= 1
    print(f"[DISCONNECTED] {addr} disconnected.")
    print(f"[ACTIVE CONNECTIONS] {active_connections}")

def start() -> None:
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}:{PORT}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

print("[STARTING] server is starting...")
start()
