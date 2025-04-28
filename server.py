import socket
import threading

#HEADER = 32
PORT = 5500
SERVER = "192.168.151.85"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECT"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.bind(ADDR)
   
def handle_client(conn, addr):
    print(f"[NEW CONNECTION] {addr} connected.")
    connected = True 
    while connected:
        msg = conn.recv(1024).decode(FORMAT) #1 kB recv, ograničit s nečim kasnije
        if msg.strip() == DISCONNECT_MESSAGE:
            connected = False
        print(f"[{addr}] {msg}")
        conn.send("Msg received".encode(FORMAT))
    conn.close()
        
        
def start():
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")

print("[STARTING] server is starting...")
start()

