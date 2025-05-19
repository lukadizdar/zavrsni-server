import socket
import threading

active_connections_lock = threading.Lock()
active_connections = 0

# HEADER = 32
PORT = 5500
SERVER = "192.168.100.21"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(ADDR)

def handle_client(conn, addr):
    global active_connections
    with active_connections_lock:
        active_connections += 1

    print(f"[NEW CONNECTION] {addr} connected.")
    print(f"[ACTIVE CONNECTIONS] {active_connections}")

    connected = True 
    while connected:
        try:
            msg = conn.recv(1024).decode(FORMAT)  # Receive up to 1kB
            if not msg:
                # Client closed connection
                print(f"[{addr}] Connection closed by client")
                break

            if msg.strip() == DISCONNECT_MESSAGE:
                connected = False
                print(f"[{addr}] Client requested disconnect.")
                break

            print(f"[{addr}] {msg}")

            try:
                conn.send("Msg received".encode(FORMAT))
            except (BrokenPipeError, ConnectionResetError):
                print(f"[WARNING] Tried to send data, but client {addr} disconnected.")
                break

        except ConnectionResetError:
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

def start():
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

print("[STARTING] server is starting...")
start()
