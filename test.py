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

print(get_local_ip())