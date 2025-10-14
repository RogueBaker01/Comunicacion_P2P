import streamlit as st
import socket
import threading
import json
import time
from queue import Queue

SERVER_HOST = "192.168.1.73" 
SERVER_PORT = 8080


def server_listener(server_sock, message_queue):
    buffer = ""
    while st.session_state.get('logged_in', False):
        try:
            data = server_sock.recv(1024)
            if not data:
                message_queue.put({"type": "server_disconnected"})
                break
            
            buffer += data.decode()
            
            while "\n" in buffer:
                message, buffer = buffer.split("\n", 1)
                if message.strip():
                    print(f"[DEBUG CLIENT] Mensaje recibido del servidor: {message}")
                    payload = json.loads(message)
                    message_queue.put(payload)
        except Exception as e:
            print(f"[ERROR CLIENT] El listener del servidor falló: {e}")
            message_queue.put({"type": "error", "content": f"[SERVER ERROR] {e}"})
            break

def tcp_listen(tcp_port, message_queue):
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(('', tcp_port))
        server_sock.listen()
        while True:
            conn, addr = server_sock.accept()
            threading.Thread(target=handle_tcp_peer, args=(conn, message_queue), daemon=True).start()
    except Exception as e:
        message_queue.put({"type": "error", "content": f"[ERROR TCP Listen] {e}"})

def handle_tcp_peer(conn, message_queue):
    try:
        st.session_state['peer_socket'] = conn
        st.toast("Un peer se ha conectado a ti.")
        while True:
            data = conn.recv(1024)
            if not data: break
            message_queue.put({"sender": st.session_state.get('chatting_with', 'Peer'), "text": data.decode()})
    except Exception:
        pass
    finally:
        conn.close()
        if 'peer_socket' in st.session_state: del st.session_state['peer_socket']


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
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        tcp_port = st.number_input("Puerto TCP Local", 1024, 65535, 8081)
        udp_port = st.number_input("Puerto UDP Local", 1024, 65535, 9091)
        
        col1, col2 = st.columns(2)
        if col1.form_submit_button("Iniciar Sesión"):
            connect_to_server("login", username, password, tcp_port, udp_port)
        if col2.form_submit_button("Registrarse"):
            connect_to_server("register", username, password, tcp_port, udp_port)

def connect_to_server(action, username, password, tcp_port, udp_port):
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.connect((SERVER_HOST, SERVER_PORT))
        
        request = {"action": action, "username": username, "password": password, "tcp_port": tcp_port, "udp_port": udp_port}
        server_sock.sendall((json.dumps(request) + "\n").encode())
        
        response = json.loads(server_sock.recv(1024).decode().strip())

        if response.get("status") == "ok":
            if action == "login":
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.server_socket = server_sock
                
                threading.Thread(target=server_listener, args=(server_sock, st.session_state.message_queue), daemon=True).start()
                threading.Thread(target=tcp_listen, args=(tcp_port, st.session_state.message_queue), daemon=True).start()
                
                st.rerun()
            else:
                st.success(f"Usuario '{username}' registrado. Ahora puedes iniciar sesión.")
        else:
            st.error(f"Error: {response.get('msg')}")
    except Exception as e:
        st.error(f"No se pudo conectar al servidor: {e}")

def chat_page():
    st.title(f"Chat P2P - Conectado como: {st.session_state.username}")

    with st.sidebar:
        st.header("Usuarios Conectados")
        
        if st.button("Actualizar Lista"):
            req = {"action": "list_users"}
            st.session_state.server_socket.sendall((json.dumps(req) + "\n").encode())
            st.toast("Solicitando lista...")

        if not st.session_state.online_users:
            st.write("Nadie conectado. Intenta actualizar.")
        else:
            for user in st.session_state.online_users:
                if st.button(f"Chatear con {user}", key=f"connect_{user}"):
                    connect_req = {"action": "connect_to_peer", "target_username": user}
                    st.session_state.server_socket.sendall((json.dumps(connect_req) + "\n").encode())
                    st.session_state.chatting_with = user
                    st.session_state.chat_log = []
    
    if st.session_state.chatting_with:
        st.header(f"Conversación con: {st.session_state.chatting_with}")
        chat_container = st.container(height=400)
        for msg in st.session_state.chat_log:
            with chat_container.chat_message("user" if msg['sender'] == st.session_state.username else "assistant"):
                st.write(msg['text'])
        
        if prompt := st.chat_input("Escribe tu mensaje..."):
            if st.session_state.peer_socket:
                st.session_state.peer_socket.sendall(prompt.encode())
                st.session_state.chat_log.append({"sender": st.session_state.username, "text": prompt})
                st.rerun()
            else:
                st.warning("Esperando conexión directa del peer...")
    else:
        st.info("Selecciona un usuario de la barra lateral para comenzar a chatear.")

def process_message_queue():
    rerun_is_needed = False
    while not st.session_state.message_queue.empty():
        msg = st.session_state.message_queue.get()
        print(f"[DEBUG CLIENT] Procesando mensaje de la cola: {msg}") 
        action = msg.get("action")
        if action == "user_list":
            st.session_state.online_users = msg.get("users", [])
            rerun_is_needed = True 
        
        elif action == "peer_info":
            peer_username, ip, port = msg["peer_username"], msg["ip"], msg["tcp_port"]
            try:
                peer_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_sock.connect((ip, port))
                st.session_state.peer_socket = peer_sock
                st.toast(f"¡Conectado con {peer_username}!")
                rerun_is_needed = True
            except Exception as e:
                st.error(f"Fallo al conectar con {peer_username}: {e}")
        
        elif "sender" in msg:
            st.session_state.chat_log.append(msg)
            rerun_is_needed = True

    if rerun_is_needed:
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