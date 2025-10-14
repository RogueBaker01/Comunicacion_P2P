import streamlit as st
import socket, threading, json, time, queue
from datetime import datetime

SERVER_HOST = "192.168.1.73"  
SERVER_PORT = 8080

def send_json(sock, data):
    sock.sendall((json.dumps(data) + "\n").encode())

def recv_lines(sock, out_q=None):
    buf = b""
    try:
        while True:
            d = sock.recv(4096)
            if not d:
                break
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    obj = json.loads(line.decode())
                except:
                    continue
                if out_q:
                    out_q.put(obj)
    except Exception as e:
        print("recv error", e)

def connect_to_server(username=None, password=None, do_register=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_HOST, SERVER_PORT))
    if do_register:
        send_json(sock, {"type":"REGISTER", "username": username, "password": password})
        resp = json.loads(sock.recv(4096).decode().split("\n")[0])
        return sock, resp
    else:
        send_json(sock, {"type":"LOGIN", "username": username, "password": password})
        buf = b""
        while b"\n" not in buf:
            buf += sock.recv(4096)
        line, rest = buf.split(b"\n", 1)
        resp = json.loads(line.decode())
        return sock, resp

def start_listener(listen_port, incoming_q):
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("0.0.0.0", listen_port))
    lsock.listen(5)
    def accept_loop():
        while True:
            conn, addr = lsock.accept()
            threading.Thread(target=handle_incoming_p2p, args=(conn, addr, incoming_q), daemon=True).start()
    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    return lsock

def handle_incoming_p2p(conn, addr, incoming_q):
    buf = b""
    try:
        while True:
            d = conn.recv(4096)
            if not d: break
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n",1)
                try:
                    msg = json.loads(line.decode())
                    incoming_q.put(("p2p", msg))
                except:
                    pass
    except Exception as e:
        print("p2p recv err", e)
    finally:
        conn.close()

st.set_page_config(
    page_title="Mensajería P2P",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #2E86AB;
        margin-bottom: 2rem;
        padding: 1rem;
        border-bottom: 2px solid #A23B72;
    }
    
    .login-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        margin: 2rem auto;
        max-width: 400px;
    }
    
    .chat-container {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #007bff;
    }
    
    .message-sent {
        background-color: #007bff;
        color: white;
        padding: 0.8rem;
        border-radius: 15px 15px 5px 15px;
        margin: 0.3rem 0;
        margin-left: 20%;
        text-align: right;
    }
    
    .message-received {
        background-color: #e9ecef;
        color: #333;
        padding: 0.8rem;
        border-radius: 15px 15px 15px 5px;
        margin: 0.3rem 0;
        margin-right: 20%;
    }
    
    .user-list-item {
        background-color: white;
        padding: 0.8rem;
        margin: 0.3rem 0;
        border-radius: 8px;
        border: 1px solid #dee2e6;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .user-list-item:hover {
        background-color: #e3f2fd;
        border-color: #2196f3;
    }
    
    .status-connected {
        color: #28a745;
        font-weight: bold;
    }
    
    .status-disconnected {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

if "server_sock" not in st.session_state:
    st.session_state.server_sock = None
if "incoming_q" not in st.session_state:
    st.session_state.incoming_q = queue.Queue()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "username" not in st.session_state:
    st.session_state.username = None
if "listener_port" not in st.session_state:
    st.session_state.listener_port = None
if "current_chat" not in st.session_state:
    st.session_state.current_chat = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}
if "users" not in st.session_state:
    st.session_state.users = []
if "show_login" not in st.session_state:
    st.session_state.show_login = True

def process_incoming_messages():
    """Procesa mensajes entrantes y los organiza por chat"""
    while not st.session_state.incoming_q.empty():
        item = st.session_state.incoming_q.get_nowait()
        if isinstance(item, tuple) and item[0] == "p2p":
            msg = item[1]
            sender = msg.get("from", "unknown")
            add_message_to_chat(sender, msg.get("content", ""), False, "P2P")
        else:
            msg = item
            t = msg.get("type")
            if t == "USER_LIST":
                st.session_state.users = msg.get("users", [])
            elif t == "P2P_INFO":
                st.session_state.last_p2p_info = msg
            elif t == "RELAY_IN":
                sender = msg.get("from", "unknown")
                add_message_to_chat(sender, msg.get("content", ""), False, "Relay")
            else:
                st.session_state.messages.append(("server", msg))

def add_message_to_chat(user, content, is_sent=False, method=""):
    """Añade un mensaje al historial de chat"""
    if user not in st.session_state.chat_history:
        st.session_state.chat_history[user] = []
    
    message = {
        "content": content,
        "timestamp": datetime.now().strftime("%H:%M"),
        "is_sent": is_sent,
        "method": method
    }
    st.session_state.chat_history[user].append(message)

def send_message_to_user(recipient, message_content):
    """Envía un mensaje a un usuario específico"""
    if not st.session_state.server_sock:
        st.error("No estás conectado al servidor")
        return False
    
    send_json(st.session_state.server_sock, {
        "type": "REQUEST_P2P", 
        "from": st.session_state.username, 
        "to": recipient
    })
    
    time.sleep(0.3)
    
    p2p_info = getattr(st.session_state, "last_p2p_info", None)
    if p2p_info and p2p_info.get("ok"):
        peer = p2p_info["peer"]
        try:
            psock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            psock.settimeout(2.0)
            psock.connect((peer["ip"], peer["port"]))
            send_json(psock, {
                "type": "CHAT",
                "from": st.session_state.username,
                "to": recipient,
                "content": message_content,
                "ts": time.time()
            })
            psock.close()
            add_message_to_chat(recipient, message_content, True, "P2P")
            return True
        except Exception:
            pass
    
    try:
        send_json(st.session_state.server_sock, {
            "type": "RELAY",
            "from": st.session_state.username,
            "to": recipient,
            "content": message_content
        })
        add_message_to_chat(recipient, message_content, True, "Relay")
        return True
    except Exception as e:
        st.error(f"Error enviando mensaje: {e}")
        return False

def show_login_page():
    """Muestra la página de login/registro"""
    st.markdown('<h1 class="main-header"> Mensajería P2P</h1>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs([" Iniciar Sesión", " Registrarse"])
        
        with tab1:
            st.markdown("### Bienvenido de vuelta")
            username = st.text_input(" Usuario", key="login_user", placeholder="Ingresa tu usuario")
            password = st.text_input(" Contraseña", type="password", key="login_pass", placeholder="Ingresa tu contraseña")
            
            if st.button("🚀 Iniciar Sesión", type="primary", use_container_width=True):
                if username and password:
                    try:
                        s, resp = connect_to_server(username=username, password=password, do_register=False)
                        if resp.get("ok"):
                            st.session_state.server_sock = s
                            st.session_state.username = username
                            st.session_state.show_login = False
                            
                            def server_reader(sock, q):
                                recv_lines(sock, out_q=q)
                            threading.Thread(target=server_reader, args=(s, st.session_state.incoming_q), daemon=True).start()

                            lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            lsock.bind(("0.0.0.0", 0)) 
                            port = lsock.getsockname()[1]
                            lsock.close()
                            st.session_state.listener_port = port
                            start_listener(port, st.session_state.incoming_q)
                            send_json(st.session_state.server_sock, {
                                "type": "UPDATE_PRESENCE", 
                                "username": st.session_state.username, 
                                "listen_port": port
                            })
                            
                            st.success("¡Conexión exitosa!")
                            st.rerun()
                        else:
                            st.error(" Usuario o contraseña incorrectos")
                    except Exception as e:
                        st.error(f" Error de conexión: {str(e)}")
                else:
                    st.warning(" Por favor completa todos los campos")
        
        with tab2:
            st.markdown("### Crear nueva cuenta")
            new_username = st.text_input(" Nuevo Usuario", key="reg_user", placeholder="Elige un nombre de usuario")
            new_password = st.text_input(" Nueva Contraseña", type="password", key="reg_pass", placeholder="Crea una contraseña segura")
            confirm_password = st.text_input("Confirmar Contraseña", type="password", key="reg_confirm", placeholder="Confirma tu contraseña")
            
            if st.button("✨ Crear Cuenta", type="primary", use_container_width=True):
                if new_username and new_password and confirm_password:
                    if new_password == confirm_password:
                        try:
                            s, resp = connect_to_server(username=new_username, password=new_password, do_register=True)
                            if resp.get("ok"):
                                st.success("¡Cuenta creada exitosamente! Ahora puedes iniciar sesión.")
                            else:
                                st.error(" Error al crear la cuenta. El usuario puede ya existir.")
                            s.close()
                        except Exception as e:
                            st.error(f" Error de registro: {str(e)}")
                    else:
                        st.error(" Las contraseñas no coinciden")
                else:
                    st.warning("Por favor completa todos los campos")
        
        st.markdown('</div>', unsafe_allow_html=True)

def show_chat_page():
    """Muestra la página principal de chat"""
    process_incoming_messages()
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f'<h2 class="main-header">💬 Chats - {st.session_state.username}</h2>', unsafe_allow_html=True)
    with col2:
        if st.button("🔄 Actualizar usuarios", type="secondary"):
            send_json(st.session_state.server_sock, {"type": "GET_USERS"})
    with col3:
        if st.button("🚪 Cerrar Sesión", type="secondary"):
            try:
                st.session_state.server_sock.close()
            except:
                pass
            st.session_state.server_sock = None
            st.session_state.username = None
            st.session_state.show_login = True
            st.session_state.current_chat = None
            st.rerun()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Usuarios conectados")
        
        if st.session_state.server_sock:
            send_json(st.session_state.server_sock, {"type": "GET_USERS"})
        
        for user in st.session_state.users:
            if user != st.session_state.username:
                has_messages = user in st.session_state.chat_history
                
                col_user, col_btn = st.columns([3, 1])
                with col_user:
                    if has_messages:
                        st.markdown(f"**💬 {user}**")
                    else:
                        st.markdown(f"👤 {user}")
                
                with col_btn:
                    if st.button("💬", key=f"chat_{user}", help=f"Chatear con {user}"):
                        st.session_state.current_chat = user
                        st.rerun()
        
        if not st.session_state.users:
            st.info("No hay usuarios conectados")
        
        st.markdown("### 📝 Chats recientes")
        for chat_user in st.session_state.chat_history:
            if chat_user not in st.session_state.users:  
                col_user, col_btn = st.columns([3, 1])
                with col_user:
                    st.markdown(f"⚪ {chat_user} (offline)")
                with col_btn:
                    if st.button("📖", key=f"history_{chat_user}", help=f"Ver historial con {chat_user}"):
                        st.session_state.current_chat = chat_user
                        st.rerun()
    
    with col2:
        if st.session_state.current_chat:
            st.markdown(f"### Chat con {st.session_state.current_chat}")
            
            chat_container = st.container()
            with chat_container:
                if st.session_state.current_chat in st.session_state.chat_history:
                    messages = st.session_state.chat_history[st.session_state.current_chat]
                    
                    for msg in messages[-20:]: 
                        if msg["is_sent"]:
                            st.markdown(f"""
                            <div class="message-sent">
                                <strong>Tú ({msg['method']})</strong> - {msg['timestamp']}<br>
                                {msg['content']}
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"""
                            <div class="message-received">
                                <strong>{st.session_state.current_chat} ({msg['method']})</strong> - {msg['timestamp']}<br>
                                {msg['content']}
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.info("No hay mensajes en este chat. ¡Envía el primero!")
            
            
            st.markdown("---")
            with st.form("message_form", clear_on_submit=True):
                new_message = st.text_area("Escribe tu mensaje...", height=100, key="new_msg")
                submitted = st.form_submit_button("📤 Enviar", type="primary", use_container_width=True)
                
                if submitted and new_message.strip():
                    if send_message_to_user(st.session_state.current_chat, new_message.strip()):
                        st.rerun()
        else:
            st.markdown("### Selecciona un usuario para comenzar a chatear")
            st.info("Elige un usuario de la lista de la izquierda para iniciar una conversación")

if st.session_state.username and not st.session_state.show_login:
    show_chat_page()
else:
    show_login_page()
