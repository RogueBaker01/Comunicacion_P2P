import socket
import threading
import json
import sqlite3
import time

HOST = "192.168.1.73"
PORT = 8080
DB_PATH = "Users.db"

clients_lock = threading.Lock()
clients = {}

def init_bd():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        last_seen INTEGER NOT NULL
    )''')
    conn.commit()
    conn.close()

def register(username, password):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO users (username, password, last_seen) VALUES (?, ?, ?)',
                    (username, password, int(time.time())))
        conn.commit()
        return True, "Registered"
    except Exception as e:
        return False, "Username exists"
    finally:
        conn.close()

def login(username, password):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    result = cur.fetchone()
    conn.close()
    if not result:
        return False
    return result[0] == password

def update_last_seen(username):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_seen=? WHERE username=?", (int(time.time()), username))
    conn.commit()
    conn.close()

def handle_client(conn, addr):
    current_user = None
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            messages = data.decode().split("\n")
            for msg in messages:
                if not msg.strip():
                    continue
                try:
                    payload = json.loads(msg)
                except json.JSONDecodeError:
                    print(f"[SERVER][ERROR] Invalid JSON from {addr}")
                    continue

                action = payload.get("action")
                
                if action == "register":
                    username = payload.get("username")
                    password = payload.get("password")
                    success, msg_resp = register(username, password)
                    conn.sendall(json.dumps({"status": "ok" if success else "error", "msg": msg_resp}).encode() + b"\n")
                
                elif action == "login":
                    username = payload.get("username")
                    password = payload.get("password")
                    if login(username, password):
                        with clients_lock:
                            clients[username] = {
                                "sock": conn, "addr": addr,
                                "tcp_port": payload.get("tcp_port"),
                                "udp_port": payload.get("udp_port"),
                                "last_seen": int(time.time())
                            }
                        current_user = username
                        update_last_seen(username)
                        conn.sendall(json.dumps({"status": "ok", "msg": "Logged in"}).encode() + b"\n")
                        print(f"[LOGIN] {username} - {addr} | Total clients: {len(clients)}")
                    else:
                        conn.sendall(json.dumps({"status": "error", "msg": "Invalid credentials"}).encode() + b"\n")

                elif action == "list_users":
                    print(f"\n[DEBUG] Recibida solicitud 'list_users' de '{current_user}'.")
                    with clients_lock:
                        user_list = [user for user in clients if user != current_user]
                        print(f"[DEBUG] Usuarios en línea (excluyendo a {current_user}): {user_list}")

                    response = {"action": "user_list", "users": user_list}
                    conn.sendall((json.dumps(response) + "\n").encode())
                    print(f"[DEBUG] Enviada lista de usuarios a {current_user}.\n")

                elif action == "connect_to_peer":
                    target_username = payload.get("target_username")
                    with clients_lock:
                        if target_username in clients and current_user in clients:
                            peer1 = clients[current_user]
                            peer2 = clients[target_username]
                            info_for_peer1 = {"action": "peer_info", "peer_username": target_username, "ip": peer2["addr"][0], "tcp_port": peer2["tcp_port"], "udp_port": peer2["udp_port"]}
                            info_for_peer2 = {"action": "peer_info", "peer_username": current_user, "ip": peer1["addr"][0], "tcp_port": peer1["tcp_port"], "udp_port": peer1["udp_port"]}
                            peer1["sock"].sendall((json.dumps(info_for_peer1) + "\n").encode())
                            peer2["sock"].sendall((json.dumps(info_for_peer2) + "\n").encode())
                        else:
                            error_msg = {"status": "error", "msg": f"User '{target_username}' not found or is offline."}
                            conn.sendall((json.dumps(error_msg) + "\n").encode())
    except Exception as e:
        print(f"[SERVER][ERROR] Conexión perdida con {addr}: {e}")
    finally:
        with clients_lock:
            if current_user and current_user in clients:
                print(f"[DISCONNECT] {current_user} | Total clients: {len(clients)-1}")
                del clients[current_user]
        conn.close()

def start_server():
    init_bd()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[SERVER] Listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()