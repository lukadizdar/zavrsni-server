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

print(get_local_ip())