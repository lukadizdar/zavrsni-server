# server.py

import socket
import threading
from pymongo import MongoClient, database, collection
from datetime import datetime
import json
from typing import Optional

def get_local_ip() -> str:
    """
    Attempts to find the local IP address of the machine.
    Connects to a dummy external host (Google DNS) to determine the
    routing interface IP, then closes the connection.
    Falls back to '127.0.0.1' if no external connectivity or an error occurs.
    """
    s: Optional[socket.socket] = None
    ip_address = '127.0.0.1' # Default fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Use a non-routable address to prevent actual external traffic
        # or a known public DNS like 8.8.8.8 to get the outgoing interface IP
        s.connect(('8.8.8.8', 80)) # Connect to a public DNS server
        ip_address = s.getsockname()[0]
    except Exception as e:
        print(f"[IP DISCOVERY ERROR] Could not determine local IP: {e}. Falling back to {ip_address}")
    finally:
        if s:
            s.close()
    return ip_address

# --- MongoDB Configuration (make sure this matches app.py) ---
MONGO_URI: str = "mongodb://localhost:27017/" # Or your MongoDB Atlas URI
DATABASE_NAME: str = "sensor_data"
COLLECTION_NAME: str = "readings"

# Initialize MongoDB client
mongo_client: Optional[MongoClient] = None
mongo_db: Optional[database.Database] = None
mongo_collection: Optional[collection.Collection] = None

try:
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client[DATABASE_NAME]
    mongo_client.admin.command('ping') # The ping command is cheap and confirms a connection has been made
    mongo_collection = mongo_db[COLLECTION_NAME]
    print(f"[MONGO] Socket server successfully connected to MongoDB at {MONGO_URI} and database '{DATABASE_NAME}'.")
except Exception as e:
    print(f"[MONGO ERROR] Socket server could not connect to MongoDB: {e}")
    # Set them back to None if connection fails
    mongo_client = None
    mongo_db = None
    mongo_collection = None

# --- Your existing socket server setup ---
active_connections_lock = threading.Lock()
active_connections = 0

PORT = 5500
SERVER = get_local_ip() # Make sure this is the correct IP for your server
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(ADDR)

def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    """
    Handles an individual client connection, receives data, and saves it to MongoDB.
    Expects data in "temperature!humidity" or JSON format.
    """
    global active_connections
    with active_connections_lock:
        active_connections += 1

    print(f"[NEW CONNECTION] {addr} connected.")
    print(f"[ACTIVE CONNECTIONS] {active_connections}")

    connected = True
    while connected:
        try:
            # Receive up to 1kB of data
            msg_bytes = conn.recv(1024)
            if not msg_bytes:
                # Client closed connection gracefully
                print(f"[{addr}] Connection closed by client.")
                break

            msg = msg_bytes.decode(FORMAT).strip() # Decode and remove leading/trailing whitespace

            if not msg:
                print(f"[{addr}] Received empty message, ignoring.")
                continue

            if msg == DISCONNECT_MESSAGE:
                connected = False
                print(f"[{addr}] Client requested disconnect.")
                break

            print(f"[{addr}] Received: '{msg}'")

            # --- MongoDB Integration ---
            if mongo_collection is not None:
                try:
                    temperature: Optional[float] = None
                    humidity: Optional[float] = None

                    # 1. Attempt to parse as JSON first ({"temperature": X, "humidity": Y})
                    if msg.startswith('{') and msg.endswith('}'):
                        try:
                            data = json.loads(msg)
                            temperature = data.get('temperature')
                            humidity = data.get('humidity')
                            if not (isinstance(temperature, (int, float)) and isinstance(humidity, (int, float))):
                                raise ValueError("JSON message missing valid 'temperature' or 'humidity' values.")
                        except json.JSONDecodeError:
                            # Not a valid JSON, fall through to other parsing methods
                            pass
                    
                    # 2. If not parsed as JSON, attempt to parse as "temperature!humidity"
                    if temperature is None or humidity is None:
                        if '!' in msg: # Check for the '!' separator
                            parts = msg.split('!') # Split by '!'
                            if len(parts) == 2:
                                try:
                                    temperature = float(parts[0].strip())
                                    humidity = float(parts[1].strip())
                                except ValueError:
                                    raise ValueError("'!'-separated message contains non-numeric values.")
                            else:
                                raise ValueError("'!'-separated message does not have exactly two parts (temperature!humidity).")
                        # else: # If no '!' either, it means neither format was recognized
                            # This implicit 'else' now triggers the final ValueError below
                    
                    # Final check: if temperature or humidity are still None, it means no recognized format
                    if temperature is None or humidity is None:
                         raise ValueError("Unrecognized message format. Expected 'temperature!humidity' or JSON.")

                    # Document to insert into MongoDB
                    sensor_reading = {
                        "temperature": temperature,
                        "humidity": humidity,
                        "timestamp": datetime.now(), # Store the time of reading
                        "client_ip": str(addr[0]),   # Store client IP for debugging/identification
                        "client_port": addr[1]
                    }

                    mongo_collection.insert_one(sensor_reading)
                    print(f"[{addr}] Saved to DB: Temp={temperature}°C, Hum={humidity}%")
                    conn.send("Msg and data saved".encode(FORMAT)) # Confirm receipt AND save
                except ValueError as ve:
                    print(f"[ERROR] Data parsing error from {addr}: {ve} (Message: '{msg}')")
                    conn.send(f"Error: Invalid data format ({ve})".encode(FORMAT))
                except Exception as mongo_err:
                    print(f"[ERROR] MongoDB insert error for {addr}: {mongo_err} (Message: '{msg}')")
                    conn.send("Error: Database save failed".encode(FORMAT))
            else:
                conn.send("Msg received (DB not connected)".encode(FORMAT)) # Acknowledge even if DB not connected

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
    """
    Starts the socket server, listens for connections, and spawns client threads.
    """
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}:{PORT}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

print("[STARTING] server is starting...")
start()
