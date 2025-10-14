import socket
import threading
import json
import time

SERVER_HOST = "192.168.1.73"
SERVER_PORT = 8080


LOCAL_TCP_PORT = 8081
LOCAL_UDP_PORT = 9090

peers = {}  # peer_username -> {"tcp_sock": socket, "udp_addr": (ip, port)}
lock = threading.Lock()

def tcp_listen():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(('', LOCAL_TCP_PORT))
    server_sock.listen()
    print(f"[TCP] Listening for P2P messages on port {LOCAL_TCP_PORT}")
    while True:
        conn, addr = server_sock.accept()
        threading.Thread(target=handle_tcp_peer, args=(conn, addr), daemon=True).start()

def handle_tcp_peer(conn, addr):
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            print(f"\n[MSG RECEIVED] {data.decode().strip()}\nEnter command: ", end="")
    except:
        pass
    finally:
        conn.close()

def udp_listen():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('', LOCAL_UDP_PORT))
    print(f"[UDP] Listening for P2P multimedia on port {LOCAL_UDP_PORT}")
    while True:
        data, addr = udp_sock.recvfrom(4096)
        print(f"\n[UDP RECEIVED] {len(data)} bytes from {addr}\nEnter command: ", end="")


def connect_to_peer(peer_username, peer_ip, peer_tcp_port, peer_udp_port):
    
    if peer_username in peers:
        print(f"[TCP] Already connected to {peer_username}")
        return
        
    while True:
        try:
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_sock.connect((peer_ip, peer_tcp_port))
            with lock:
                peers[peer_username] = {"tcp_sock": tcp_sock, "udp_addr": (peer_ip, peer_udp_port)}
            print(f"\n[TCP] Connected to {peer_username}. You can now send messages.")
            break
        except Exception as e:
            print(f"[TCP] Could not connect to {peer_username}: {e}, retrying in 5s")
            time.sleep(5)


def main():
    username = input("Username: ")
    password = input("Password: ")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.connect((SERVER_HOST, SERVER_PORT))
        login_msg = {
            "action": "login", "username": username, "password": password,
            "tcp_port": LOCAL_TCP_PORT, "udp_port": LOCAL_UDP_PORT
        }
        server_socket.sendall((json.dumps(login_msg) + "\n").encode())
        print("[SERVER] Connected and attempting to log in...")
    except Exception as e:
        print(f"[SERVER] Cannot connect: {e}")
        return

    threading.Thread(target=tcp_listen, daemon=True).start()
    threading.Thread(target=udp_listen, daemon=True).start()

    def server_listener():
        nonlocal server_socket
        while True:
            try:
                data = server_socket.recv(1024)
                if not data:
                    print("[SERVER] Disconnected.")
                    break
                
                messages = data.decode().split("\n")
                for msg in messages:
                    if not msg.strip():
                        continue
                    payload = json.loads(msg)
                    
                    action = payload.get("action")
                    if action == "peer_info":
                        peer_username = payload["peer_username"]
                        peer_ip = payload["ip"]
                        peer_tcp_port = payload["tcp_port"]
                        peer_udp_port = payload["udp_port"]
                        print(f"\n[PEER INFO] Received data for {peer_username} at {peer_ip} TCP:{peer_tcp_port}")
                        threading.Thread(target=connect_to_peer, args=(peer_username, peer_ip, peer_tcp_port, peer_udp_port), daemon=True).start()
                    
                    elif action == "user_list":
                        print("\n[ONLINE USERS]:")
                        if payload["users"]:
                            for user in payload["users"]:
                                print(f"- {user}")
                        else:
                            print("No other users are online.")
                    
                    elif payload.get("status") == "error":
                        print(f"\n[SERVER ERROR] {payload.get('msg')}")

            except Exception as e:
                print(f"[SERVER] Error: {e}")
                break

    threading.Thread(target=server_listener, daemon=True).start()
    
    time.sleep(1) 
    
    print("\n--- Commands ---")
    print("list              - See online users")
    print("connect <user>    - Connect to a user")
    print("<user>: <message> - Send a message to a connected user")
    print("exit              - Close the application")
    print("------------------")

    while True:
        cmd = input("Enter command: ")
        if cmd.lower() == 'exit':
            break

        if cmd.lower() == 'list':
            list_req = {"action": "list_users"}
            server_socket.sendall((json.dumps(list_req) + "\n").encode())

        elif cmd.lower().startswith('connect '):
            parts = cmd.split(' ', 1)
            if len(parts) > 1:
                target_user = parts[1].strip()
                connect_req = {"action": "connect_to_peer", "target_username": target_user}
                server_socket.sendall((json.dumps(connect_req) + "\n").encode())
            else:
                print("[ERROR] Please specify a user to connect to. Usage: connect <username>")
        
        elif ":" in cmd:
            peer_name, message = cmd.split(":", 1)
            peer_name = peer_name.strip()
            message = message.strip()
            with lock:
                if peer_name in peers:
                    try:
                        peers[peer_name]["tcp_sock"].sendall(message.encode())
                    except Exception as e:
                        print(f"[TCP] Error sending to {peer_name}: {e}")
                else:
                    print(f"[ERROR] No TCP connection to {peer_name}. Use 'connect {peer_name}' first.")
        else:
            if cmd:
                print("[ERROR] Invalid command format.")

    server_socket.close()
    print("Application closed.")

if __name__ == "__main__":
    main()