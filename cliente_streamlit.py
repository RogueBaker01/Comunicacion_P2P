import streamlit as st
import socket
import threading
import json
import time
from queue import Queue 

SERVER_HOST = "192.168.1.73" 
SERVER_PORT = 8080


def tcp_listen(tcp_port, message_queue):
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(('', tcp_port))
        server_sock.listen()
        
        while True:
            conn, addr = server_sock.accept()
            threading.Thread(target=handle_tcp_peer, args=(conn, message_queue), daemon=True).start()
    except Exception as e:
        message_queue.put(f"[ERROR TCP Listen] {e}")

def handle_tcp_peer(conn, message_queue):
    """Maneja una conexión P2P individual."""
    peer_username = "Peer" 
    try:
       
        st.session_state['peer_socket'] = conn
        
        while True:
            data = conn.recv(1024)
            if not data:
                break
            message_queue.put({"sender": st.session_state.get('chatting_with', 'Peer'), "text": data.decode()})
    except Exception as e:
        message_queue.put(f"[ERROR Peer] {e}")
    finally:
        conn.close()
        if 'peer_socket' in st.session_state:
            del st.session_state['peer_socket']

def server_listener(server_sock, message_queue):
    while st.session_state.get('logged_in', False):
        try:
            data = server_sock.recv(1024)
            if not data:
                message_queue.put({"type": "server_disconnected"})
                break
            
            messages = data.decode().split("\n")
            for msg in messages:
                if not msg.strip():
                    continue
                payload = json.loads(msg)
                message_queue.put(payload) 
        except Exception as e:
            message_queue.put({"type": "error", "content": f"[SERVER ERROR] {e}"})
            break


def initialize_session_state():
    defaults = {
        "logged_in": False, "username": "", "server_socket": None,
        "chat_log": [], "online_users": [], "chatting_with": None,
        "peer_socket": None, "message_queue": Queue()
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def login_page():
    st.header("Bienvenido al Doki Chat")
    
    with st.form("login_form"):
        username = st.text_input("Usuario", key="login_user")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        tcp_port = st.number_input("Puerto TCP Local", min_value=1024, max_value=65535, value=8081)
        udp_port = st.number_input("Puerto UDP Local", min_value=1024, max_value=65535, value=9091)
        
        col1, col2 = st.columns(2)
        with col1:
            login_button = st.form_submit_button("Iniciar Sesión")
        with col2:
            register_button = st.form_submit_button("Registrarse")

        if login_button:
            connect_to_server("login", username, password, tcp_port, udp_port)
        if register_button:
            connect_to_server("register", username, password, tcp_port, udp_port)

def connect_to_server(action, username, password, tcp_port, udp_port):
    """Conecta al servidor y realiza la acción de login o registro."""
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((SERVER_HOST, SERVER_PORT))
        
        request = {
            "action": action, "username": username, "password": password,
            "tcp_port": tcp_port, "udp_port": udp_port
        }
        server_sock.sendall((json.dumps(request) + "\n").encode())
        
        response_data = server_sock.recv(1024)
        response = json.loads(response_data.decode().strip())

        if response.get("status") == "ok":
            if action == "login":
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.server_socket = server_sock
                st.session_state.tcp_port = tcp_port
                
                threading.Thread(target=server_listener, args=(server_sock, st.session_state.message_queue), daemon=True).start()
                threading.Thread(target=tcp_listen, args=(tcp_port, st.session_state.message_queue), daemon=True).start()
                
                st.rerun() 
            else:
                st.success(f"Usuario '{username}' registrado exitosamente. Ahora puedes iniciar sesión.")
        else:
            st.error(f"Error: {response.get('msg')}")

    except Exception as e:
        st.error(f"No se pudo conectar al servidor: {e}")

def chat_page():
    st.title(f"Doki Chat - Conectado como: {st.session_state.username}")

    with st.sidebar:
        st.header("Usuarios Conectados")
        
        if st.button("Actualizar Lista"):
            req = {"action": "list_users"}
            st.session_state.server_socket.sendall((json.dumps(req) + "\n").encode())
        
        if not st.session_state.online_users:
            st.write("Nadie conectado o presiona 'Actualizar'.")
        else:
            for user in st.session_state.online_users:
                if st.button(f"Chatear con {user}", key=f"connect_{user}"):
                    connect_req = {"action": "connect_to_peer", "target_username": user}
                    st.session_state.server_socket.sendall((json.dumps(connect_req) + "\n").encode())
                    st.session_state.chatting_with = user
                    st.session_state.chat_log = []
    
    if st.session_state.chatting_with:
        st.header(f"Conversación con: {st.session_state.chatting_with}")
        
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_log:
                with st.chat_message("user" if msg['sender'] == st.session_state.username else "assistant"):
                    st.write(msg['text'])
        
        prompt = st.chat_input("Escribe tu mensaje...")
        if prompt:
            if st.session_state.peer_socket:
                try:
                    st.session_state.peer_socket.sendall(prompt.encode())
                    st.session_state.chat_log.append({"sender": st.session_state.username, "text": prompt})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al enviar mensaje: {e}")
            else:
                st.warning("Aún no estás conectado directamente con el peer. Esperando conexión...")
    else:
        st.info("Selecciona un usuario de la barra lateral para comenzar a chatear.")

def process_message_queue():
    while not st.session_state.message_queue.empty():
        msg = st.session_state.message_queue.get()
        
        if isinstance(msg, dict):
            action = msg.get("action")
            if action == "user_list":
                st.session_state.online_users = msg.get("users", [])
                st.rerun()
            elif action == "peer_info":
                peer_ip = msg["ip"]
                peer_tcp_port = msg["tcp_port"]
                try:
                    peer_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    peer_sock.connect((peer_ip, peer_tcp_port))
                    st.session_state.peer_socket = peer_sock
                    st.toast(f"¡Conexión P2P con {msg['peer_username']} establecida!")
                except Exception as e:
                    st.error(f"Fallo al conectar con peer: {e}")
            
            elif "sender" in msg:
                st.session_state.chat_log.append(msg)
                st.rerun()

def main():
    initialize_session_state()
    
    if st.session_state.logged_in:
        process_message_queue()
        chat_page()
    else:
        login_page()

if __name__ == "__main__":
    main()