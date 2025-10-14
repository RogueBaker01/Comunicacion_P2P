import socket
import threading
import json
import queue
import datetime
import time
import sys

SERVER_HOST = '192.168.1.73'
SERVER_PORT = 8080

class P2PClient:
    def __init__(self):
        self.server_sock = None
        self.p2p_sock = None
        self.p2p_port = None
        self.username = None
        self.connected_users = []
        self.message_queue = queue.Queue()
        self.running = True
        self.p2p_connections = {}
        
    def send_json(self, sock, data):
        try:
            sock.sendall((json.dumps(data) + "\n").encode())
            return True
        except Exception as e:
            print(f"Error enviando datos: {e}")
            return False
    
    def connect_to_server(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.connect((SERVER_HOST, SERVER_PORT))
            print(f"Conectado al servidor {SERVER_HOST}:{SERVER_PORT}")
            return True
        except Exception as e:
            print(f"Error conectando al servidor: {e}")
            return False
    
    def register(self, username, password):
        if not self.server_sock:
            return False, "No conectado al servidor"
        
        msg = {"type": "REGISTER", "username": username, "password": password}
        if not self.send_json(self.server_sock, msg):
            return False, "Error enviando datos"
        
        response = self.receive_json(self.server_sock)
        if response and response.get("type") == "REGISTER_RES":
            return response.get("ok", False), response.get("reason", "Error desconocido")
        return False, "No se recibió respuesta"
    
    def login(self, username, password):
        if not self.server_sock:
            return False
        
        msg = {"type": "LOGIN", "username": username, "password": password}
        if not self.send_json(self.server_sock, msg):
            return False
        
        response = self.receive_json(self.server_sock)
        if response and response.get("type") == "LOGIN_RES":
            if response.get("ok", False):
                self.username = username
                return True
        return False
    
    def receive_json(self, sock):
        try:
            buffer = b""
            while True:
                data = sock.recv(1024)
                if not data:
                    return None
                buffer += data
                if b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    return json.loads(line.decode())
        except Exception as e:
            print(f"Error recibiendo datos: {e}")
            return None
    
    def setup_p2p_listener(self):
        try:
            self.p2p_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.p2p_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.p2p_sock.bind(('0.0.0.0', 0)) 
            self.p2p_port = self.p2p_sock.getsockname()[1]
            self.p2p_sock.listen(10)
            
            threading.Thread(target=self.accept_p2p_connections, daemon=True).start()
            
            self.update_presence()
            
            print(f"Escuchando conexiones P2P en puerto {self.p2p_port}")
            return True
        except Exception as e:
            print(f"Error configurando P2P: {e}")
            return False
    
    def update_presence(self):
        if not self.server_sock or not self.username:
            return
        
        msg = {
            "type": "UPDATE_PRESENCE",
            "username": self.username,
            "listen_port": self.p2p_port
        }
        self.send_json(self.server_sock, msg)
    
    def accept_p2p_connections(self):
        while self.running:
            try:
                conn, addr = self.p2p_sock.accept()
                threading.Thread(target=self.handle_p2p_connection, args=(conn, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    print(f"Error aceptando conexión P2P: {e}")
    
    def handle_p2p_connection(self, conn, addr):
        print(f"Nueva conexión P2P desde {addr}")
        buffer = b""
        try:
            while self.running:
                data = conn.recv(1024)
                if not data:
                    break
                
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "P2P_MESSAGE":
                            sender = msg.get("from", "Desconocido")
                            content = msg.get("content", "")
                            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"\n[{timestamp}] {sender} (P2P): {content}")
                            print("> ", end="", flush=True)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error en conexión P2P: {e}")
        finally:
            conn.close()
    
    def connect_to_peer(self, peer_ip, peer_port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((peer_ip, peer_port))
            return sock
        except Exception as e:
            print(f"Error conectando al peer {peer_ip}:{peer_port}: {e}")
            return None
    
    def send_p2p_message(self, target_user, message):
        msg = {"type": "REQUEST_P2P", "to": target_user, "from": self.username}
        if not self.send_json(self.server_sock, msg):
            return False
        
        response = self.receive_json(self.server_sock)
        if not response or response.get("type") != "P2P_INFO":
            return False
        
        if not response.get("ok", False):
            print(f"No se puede conectar con {target_user}: {response.get('reason', 'Error desconocido')}")
            return False
        
        peer_info = response.get("peer", {})
        peer_ip = peer_info.get("ip")
        peer_port = peer_info.get("port")
        
        if not peer_ip or not peer_port:
            print(f"Información del peer incompleta para {target_user}")
            return False
        
        peer_sock = self.connect_to_peer(peer_ip, peer_port)
        if not peer_sock:
            return False
        
        try:
            p2p_msg = {
                "type": "P2P_MESSAGE",
                "from": self.username,
                "content": message
            }
            self.send_json(peer_sock, p2p_msg)
            peer_sock.close()
            return True
        except Exception as e:
            print(f"Error enviando mensaje P2P: {e}")
            return False
    
    def send_relay_message(self, target_user, message):
        msg = {
            "type": "RELAY",
            "to": target_user,
            "from": self.username,
            "content": message
        }
        return self.send_json(self.server_sock, msg)
    
    def get_users(self):
        msg = {"type": "GET_USERS"}
        if not self.send_json(self.server_sock, msg):
            return []
        
        response = self.receive_json(self.server_sock)
        if response and response.get("type") == "USER_LIST":
            return response.get("users", [])
        return []
    
    def listen_server_messages(self):
        buffer = b""
        try:
            while self.running:
                data = self.server_sock.recv(1024)
                if not data:
                    break
                
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        self.handle_server_message(msg)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            if self.running:
                print(f"Error escuchando servidor: {e}")
    
    def handle_server_message(self, msg):
        msg_type = msg.get("type")
        
        if msg_type == "USER_LIST":
            self.connected_users = msg.get("users", [])
            
        elif msg_type == "RELAY_IN":
            sender = msg.get("from", "Desconocido")
            content = msg.get("content", "")
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp}] {sender} (relay): {content}")
            print("> ", end="", flush=True)
            
        elif msg_type == "RELAY_ACK":
            if not msg.get("ok", False):
                print(f"Error enviando mensaje: {msg.get('reason', 'Error desconocido')}")
    
    def show_menu(self):
        print("\n=== CLIENTE P2P ===")
        print("1. Listar usuarios conectados")
        print("2. Enviar mensaje P2P")
        print("3. Enviar mensaje via servidor (relay)")
        print("4. Salir")
        print("===================")
    
    def run(self):
        """Ejecuta el cliente"""
        print("=== CLIENTE P2P ===")
        
        if not self.connect_to_server():
            return
        
        while True:
            print("\n1. Registrarse")
            print("2. Iniciar sesión")
            print("3. Salir")
            choice = input("Seleccione una opción: ").strip()
            
            if choice == "1":
                username = input("Nombre de usuario: ").strip()
                password = input("Contraseña: ").strip()
                
                ok, reason = self.register(username, password)
                if ok:
                    print(f"Registro exitoso: {reason}")
                else:
                    print(f"Error en registro: {reason}")
                    
            elif choice == "2":
                username = input("Nombre de usuario: ").strip()
                password = input("Contraseña: ").strip()
                
                if self.login(username, password):
                    print(f"Sesión iniciada como {username}")
                    break
                else:
                    print("Error en inicio de sesión")
                    
            elif choice == "3":
                return
            else:
                print("Opción inválida")
        
        if not self.setup_p2p_listener():
            print("Error configurando P2P, continuando sin P2P...")
        
        threading.Thread(target=self.listen_server_messages, daemon=True).start()
        
        print(f"\n¡Bienvenido {self.username}!")
        print("Escriba 'help' para ver los comandos disponibles")
        
        while self.running:
            try:
                user_input = input("> ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() == "help":
                    print("Comandos disponibles:")
                    print("  users - Listar usuarios conectados")
                    print("  p2p <usuario> <mensaje> - Enviar mensaje P2P")
                    print("  relay <usuario> <mensaje> - Enviar mensaje via servidor")
                    print("  quit - Salir")
                    
                elif user_input.lower() == "users":
                    users = self.get_users()
                    print(f"Usuarios conectados: {users}")
                    
                elif user_input.lower().startswith("p2p "):
                    parts = user_input.split(" ", 2)
                    if len(parts) >= 3:
                        target = parts[1]
                        message = parts[2]
                        if self.send_p2p_message(target, message):
                            print(f"Mensaje P2P enviado a {target}")
                        else:
                            print(f"Error enviando mensaje P2P a {target}")
                    else:
                        print("Uso: p2p <usuario> <mensaje>")
                        
                elif user_input.lower().startswith("relay "):
                    parts = user_input.split(" ", 2)
                    if len(parts) >= 3:
                        target = parts[1]
                        message = parts[2]
                        if self.send_relay_message(target, message):
                            print(f"Mensaje relay enviado a {target}")
                        else:
                            print(f"Error enviando mensaje relay a {target}")
                    else:
                        print("Uso: relay <usuario> <mensaje>")
                        
                elif user_input.lower() in ["quit", "exit", "salir"]:
                    break
                    
                else:
                    print("Comando no reconocido. Escriba 'help' para ayuda.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
        
        
        self.running = False
        if self.server_sock:
            self.server_sock.close()
        if self.p2p_sock:
            self.p2p_sock.close()
        print("Cliente desconectado")

def main():
    client = P2PClient()
    client.run()

if __name__ == "__main__":
    main()