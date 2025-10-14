import socket
import threading
import json
import sqlite3
import time

HOST = "192.168.1.73"
PORT = 8080
DB_PATH = "Users.db"
clients_lock = threading.Lock()
clients = {} # username -> { "sock": socket, "addr": (ip,port), "last_seen": ts }

def init_bd():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)

    try:
        cur = conn.cursor()
        cur.execute('''INSERT INTO users (username, password, last_seen) VALUES (?, ?, ?)''',
                    (username, password, int(time.time())))
        conn.commit()
        return True, "Registered"
    except Exception as e:
        print(f"Error registering user: {str(e)}")
        return False, "Username exists"
    finally:
        conn.close()

def login(username, password):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    result = cur.fetchone()
    conn.close()
    if not result:
        return False
    return result[0] == password

def send_json(sock,data):
    sock.sendall((json.dumps(data)+"\n").encode())

def broadcast_user_list():
    with clients_lock:
        users_list = list(clients.keys())
        for u,info in list(clients.items()):
            send_json(info["sock"], {"type": "user_list", "users": users_list})

def handle_client(conn, addr):
    """
    Cada cliente envía JSON newline-terminated.
    Mensajes soportados: REGISTER, LOGIN, UPDATE_PRESENCE, GET_USERS, REQUEST_P2P, RELAY
    """
    buf = b""
    username = None
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode())
                except:
                    continue
                mtype = msg.get("type")

                if mtype == "REGISTER":
                    ok, reason = register(msg["username"], msg["password"])
                    send_json(conn, {"type":"REGISTER_RES", "ok": ok, "reason": reason})

                elif mtype == "LOGIN":
                    ok = login(msg["username"], msg["password"])
                    send_json(conn, {"type":"LOGIN_RES", "ok": ok})
                    if ok:
                        username = msg["username"]
                        with clients_lock:
                            clients[username] = {"sock": conn, "addr": addr, "last_seen": int(time.time()), "listen_port": None}
                        broadcast_user_list()

                elif mtype == "UPDATE_PRESENCE":
                    username = msg["username"]
                    listen_port = msg.get("listen_port")
                    with clients_lock:
                        if username in clients:
                            clients[username].update({"listen_port": listen_port, "addr": addr, "last_seen": int(time.time())})
                    send_json(conn, {"type":"UPDATE_ACK"})

                elif mtype == "GET_USERS":
                    with clients_lock:
                        user_list = list(clients.keys())
                    send_json(conn, {"type":"USER_LIST", "users": user_list})

                elif mtype == "REQUEST_P2P":
                    target = msg.get("to")
                    requester = msg.get("from")
                    with clients_lock:
                        if target in clients:
                            tgt = clients[target]
                            host = tgt["addr"][0]
                            port = tgt.get("listen_port")
                            send_json(conn, {"type":"P2P_INFO", "ok": True, "peer": {"username": target, "ip": host, "port": port}})
                        else:
                            send_json(conn, {"type":"P2P_INFO", "ok": False, "reason": "User not online"})

                elif mtype == "RELAY":
                    to = msg.get("to")
                    with clients_lock:
                        if to in clients:
                            dest_sock = clients[to]["sock"]
                            send_json(dest_sock, {"type":"RELAY_IN", "from": msg.get("from"), "content": msg.get("content")})
                            send_json(conn, {"type":"RELAY_ACK", "ok": True})
                        else:
                            send_json(conn, {"type":"RELAY_ACK", "ok": False, "reason": "recipient offline"})

                else:
                    send_json(conn, {"type":"ERROR", "reason":"unknown message type"})
    except Exception as e:
        print("client handler error", e)
    finally:
        if username:
            with clients_lock:
                if username in clients and clients[username]["sock"] is conn:
                    del clients[username]
            broadcast_user_list()
        conn.close()
        print("Conn closed", addr)

def main():
    init_bd()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(100)
    print("Server listening on", HOST, PORT)
    try:
        while True:
            conn, addr = s.accept()
            print("New conn", addr)
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    finally:
        s.close()   

if __name__ == "__main__":
    main()