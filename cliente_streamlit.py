import streamlit as st
import socket
import threading
import json
import time
import base64
from queue import Queue, Empty

SERVER_HOST = "192.168.1.73"
SERVER_PORT = 8080


def server_listener(server_sock, message_queue):
    
    buffer = ""
    try:
        while True:
            try:
                data = server_sock.recv(4096)
                if not data:
                    message_queue.put({"type": "server_disconnected"})
                    break
                buffer += data.decode(errors="ignore")
                while "\n" in buffer:
                    raw, buffer = buffer.split("\n", 1)
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except Exception as e:
                        print("[DEBUG] JSON parse fail from server:", e, raw[:200])
                        continue
                    message_queue.put(payload)
            except Exception as e:
                print("[ERROR CLIENT] server_listener:", e)
                message_queue.put({"type": "error", "content": f"[SERVER ERROR] {e}"})
                break
    finally:
        message_queue.put({"type": "server_disconnected"})

def tcp_listen(tcp_port, message_queue):
    
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(('', tcp_port))
        server_sock.listen()
        print(f"[TCP LISTEN] P2P TCP listening on {tcp_port}")
        while True:
            conn, addr = server_sock.accept()
            threading.Thread(target=handle_tcp_peer, args=(conn, addr, message_queue), daemon=True).start()
    except Exception as e:
        print("[ERROR] tcp_listen:", e)
        message_queue.put({"type": "error", "content": f"[ERROR TCP Listen] {e}"})

def handle_tcp_peer(conn, addr, message_queue):
    
    buffer = ""
    peer_username = None
    try:
        conn.settimeout(0.5)
        while True:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except Exception:
                break

            if not data:
                break
            buffer += data.decode(errors="ignore")
            while "\n" in buffer:
                raw, buffer = buffer.split("\n", 1)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                    payload["_from_addr"] = addr
                    message_queue.put(payload)
                    if payload.get("type") in ("text", "image") and "from" in payload:
                        peer_username = payload["from"]
                        with _peers_lock:
                            if peer_username and peer_username not in st.session_state.peers:
                                st.session_state.peers[peer_username] = {"tcp_sock": conn, "addr": addr}
                except Exception as e:
                    message_queue.put({"type": "text", "from": st.session_state.get("chatting_with", "Peer"), "text": raw})
    finally:
        try:
            conn.close()
        except:
            pass
        with _peers_lock:
            to_delete = []
            for uname, info in st.session_state.peers.items():
                sock = info.get("tcp_sock")
                if sock is conn:
                    to_delete.append(uname)
            for u in to_delete:
                del st.session_state.peers[u]
        message_queue.put({"type": "peer_disconnected", "addr": addr, "username": peer_username})


_peers_lock = threading.Lock()

def initialize_session_state():
    defaults = {
        "logged_in": False,
        "username": "",
        "server_socket": None,
        "chat_log": {},         
        "online_users": [],    
        "chatting_with": None, 
        "peer_socket": None,   
        "peers": {},            
        "message_queue": Queue(),
        "local_tcp_port": 8081,
        "local_udp_port": 9090,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def login_page():
    st.header("Bienvenido al Doki Chat (P2P)")

    with st.form("login_form"):
        username = st.text_input("Usuario", value=st.session_state.get("username",""))
        password = st.text_input("Contraseña", type="password")
        tcp_port = st.number_input("Puerto TCP Local", 1024, 65535, value=st.session_state.local_tcp_port)
        udp_port = st.number_input("Puerto UDP Local (informativo)", 1024, 65535, value=st.session_state.local_udp_port)
        col1, col2 = st.columns(2)
        if col1.form_submit_button("Iniciar Sesión"):
            connect_to_server("login", username, password, int(tcp_port), int(udp_port))
        if col2.form_submit_button("Registrarse"):
            connect_to_server("register", username, password, int(tcp_port), int(udp_port))


def connect_to_server(action, username, password, tcp_port, udp_port):
    try:
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.settimeout(5)
        server_sock.connect((SERVER_HOST, SERVER_PORT))
        server_sock.settimeout(None)
        request = {"action": action, "username": username, "password": password, "tcp_port": tcp_port, "udp_port": udp_port}
        server_sock.sendall((json.dumps(request) + "\n").encode())

        resp = server_sock.recv(4096).decode().strip()
        try:
            response = json.loads(resp.split("\n")[0])
        except:
            st.error("Respuesta inválida del servidor.")
            server_sock.close()
            return

        if response.get("status") == "ok":
            if action == "login":
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.server_socket = server_sock
                st.session_state.local_tcp_port = tcp_port
                st.session_state.local_udp_port = udp_port
                t1 = threading.Thread(target=server_listener, args=(server_sock, st.session_state.message_queue), daemon=True)
                t1.start()
                t2 = threading.Thread(target=tcp_listen, args=(tcp_port, st.session_state.message_queue), daemon=True)
                t2.start()
                st.success(f"Conectado como {username}")
                time.sleep(0.2)
                st.rerun()
            else:
                st.success(f"Usuario '{username}' registrado. Ahora puedes iniciar sesión.")
                server_sock.close()
        else:
            st.error(f"Error: {response.get('msg')}")
            server_sock.close()
    except Exception as e:
        st.error(f"No se pudo conectar al servidor: {e}")


def chat_page():
    st.title(f"Chat P2P - Conectado como: {st.session_state.username}")

    with st.sidebar:
        st.header("Usuarios Conectados (servidor)")
        if st.button("Actualizar Lista"):
            try:
                req = {"action": "list_users"}
                st.session_state.server_socket.sendall((json.dumps(req) + "\n").encode())
                st.toast("Solicitando lista...")
            except Exception as e:
                st.error("No se puede pedir lista al servidor: " + str(e))
        st.markdown("---")
        if not st.session_state.online_users:
            st.write("Nadie conectado (o no hay respuesta). Intenta actualizar.")
        else:
            for user in st.session_state.online_users:
                if user == st.session_state.username:
                    continue
                if st.button(f"Chatear con {user}", key=f"connect_{user}"):
                    try:
                        connect_req = {"action": "connect_to_peer", "target_username": user}
                        st.session_state.server_socket.sendall((json.dumps(connect_req) + "\n").encode())
                        st.session_state.chatting_with = user
                        if user not in st.session_state.chat_log:
                            st.session_state.chat_log[user] = []
                    except Exception as e:
                        st.error("Fallo al solicitar conexión: " + str(e))

        st.markdown("---")
        st.header("Peers conectados (P2P)")
        if not st.session_state.peers:
            st.write("No hay peers conectados directamente.")
        else:
            for p in st.session_state.peers:
                info = st.session_state.peers[p]
                addr = info.get("addr")
                st.write(f"- {p} @ {addr}")

        st.markdown("---")
        if st.button("Cerrar sesión"):
            logout()
            st.rerun()

    chatting = st.session_state.chatting_with
    if not chatting:
        st.info("Selecciona un usuario desde la barra lateral para comenzar a chatear.")
        return

    st.header(f"Conversación con: {chatting}")
    if chatting not in st.session_state.chat_log:
        st.session_state.chat_log[chatting] = []

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_log[chatting]:
            sender = msg.get("sender")
            mtype = msg.get("type", "text")
            if mtype == "text":
                if sender == st.session_state.username:
                    with st.chat_message("user"):
                        st.write(msg.get("text"))
                else:
                    with st.chat_message("assistant"):
                        st.write(msg.get("text"))
            elif mtype == "image":
                caption = msg.get("caption", "")
                img_bytes = msg.get("image_bytes")
                if img_bytes:
                    if sender == st.session_state.username:
                        with st.chat_message("user"):
                            st.image(img_bytes, caption=caption)
                    else:
                        with st.chat_message("assistant"):
                            st.image(img_bytes, caption=caption)
                else:
                    if sender == st.session_state.username:
                        with st.chat_message("user"):
                            st.write("[Imagen (no disponible)] " + caption)
                    else:
                        with st.chat_message("assistant"):
                            st.write("[Imagen recibida] " + caption)

    col_text, col_file = st.columns([4,1])
    with col_text:
        prompt = st.chat_input("Escribe tu mensaje...")
        if prompt:
            send_text_message(chatting, prompt)
            st.rerun()

    with col_file:
        uploaded = st.file_uploader("📎", type=["png","jpg","jpeg","gif"], key=f"uploader_{chatting}")
        if uploaded is not None:
            caption = st.text_input("Pie de imagen (opcional)", key=f"cap_{chatting}")
            if st.button("Enviar imagen", key=f"send_img_{chatting}"):
                send_image(chatting, uploaded.read(), caption)
                st.rerun()


def send_text_message(target_username, text):
   
    payload = {"type": "text", "from": st.session_state.username, "text": text, "ts": time.time()}
    st.session_state.chat_log.setdefault(target_username, []).append({"sender": st.session_state.username, "type": "text", "text": text, "ts": time.time()})

    with _peers_lock:
        peer_info = st.session_state.peers.get(target_username)
        sock = peer_info.get("tcp_sock") if peer_info else None

    if sock:
        try:
            sock.sendall((json.dumps(payload) + "\n").encode())
            return True
        except Exception as e:
            st.error(f"Error enviando mensaje a {target_username}: {e}")
            with _peers_lock:
                if target_username in st.session_state.peers:
                    try:
                        st.session_state.peers[target_username]["tcp_sock"].close()
                    except:
                        pass
                    del st.session_state.peers[target_username]
    else:
        st.warning("Aún no hay conexión TCP directa con el peer. Intenta conectar desde la barra lateral.")
        return False

def send_image(target_username, image_bytes, caption=""):
    
    b64 = base64.b64encode(image_bytes).decode()
    payload = {"type": "image", "from": st.session_state.username, "image_b64": b64, "caption": caption, "ts": time.time()}
    st.session_state.chat_log.setdefault(target_username, []).append({"sender": st.session_state.username, "type": "image", "image_bytes": image_bytes, "caption": caption, "ts": time.time()})

    with _peers_lock:
        peer_info = st.session_state.peers.get(target_username)
        sock = peer_info.get("tcp_sock") if peer_info else None

    if sock:
        try:
            sock.sendall((json.dumps(payload) + "\n").encode())
            return True
        except Exception as e:
            st.error(f"Error enviando imagen a {target_username}: {e}")
            with _peers_lock:
                if target_username in st.session_state.peers:
                    try:
                        st.session_state.peers[target_username]["tcp_sock"].close()
                    except:
                        pass
                    del st.session_state.peers[target_username]
            return False
    else:
        st.warning("Aún no hay conexión TCP directa con el peer. Intenta conectar desde la barra lateral.")
        return False


def process_message_queue():
    rerun_needed = False
    mq = st.session_state.message_queue
    while True:
        try:
            msg = mq.get_nowait()
        except Empty:
            break

        print("[DEBUG CLIENT] Procesando mensaje de la cola:", msg)

        action = msg.get("action") or msg.get("type")
        if action == "user_list":
            st.session_state.online_users = msg.get("users", [])
            rerun_needed = True

        elif action == "peer_info":
            peer_username = msg.get("peer_username")
            ip = msg.get("ip")
            tcp_port = msg.get("tcp_port")
            try:
                peer_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_sock.settimeout(5)
                peer_sock.connect((ip, tcp_port))
                peer_sock.settimeout(None)
                with _peers_lock:
                    st.session_state.peers[peer_username] = {"tcp_sock": peer_sock, "addr": (ip, tcp_port)}
                st.toast(f"Conectado TCP a {peer_username}")
                intro = {"type": "text", "from": st.session_state.username, "text": f"[conexion directa establecida]", "ts": time.time()}
                peer_sock.sendall((json.dumps(intro) + "\n").encode())
                rerun_needed = True
            except Exception as e:
                st.error(f"Fallo al conectar a peer {peer_username} ({ip}:{tcp_port}): {e}")

        elif action == "server_disconnected":
            st.warning("Servidor central desconectado. Seguirás en modo P2P con peers ya conectados.")
            

        elif action == "error":
            st.error(msg.get("content") or msg.get("msg"))

        elif action == "peer_disconnected":
            uname = msg.get("username")
            if uname and uname in st.session_state.peers:
                with _peers_lock:
                    try:
                        st.session_state.peers[uname]["tcp_sock"].close()
                    except:
                        pass
                    del st.session_state.peers[uname]
                st.toast(f"Peer {uname} se desconectó")
                rerun_needed = True

        elif msg.get("type") in ("text", "image"):
            sender = msg.get("from") or msg.get("sender") or "Peer"
            mtype = msg.get("type")
            if mtype == "text":
                text = msg.get("text", "")
                st.session_state.chat_log.setdefault(sender, []).append({"sender": sender, "type": "text", "text": text, "ts": msg.get("ts", time.time())})
            elif mtype == "image":
                b64 = msg.get("image_b64")
                caption = msg.get("caption", "")
                try:
                    img_bytes = base64.b64decode(b64) if b64 else None
                except Exception:
                    img_bytes = None
                st.session_state.chat_log.setdefault(sender, []).append({"sender": sender, "type": "image", "image_bytes": img_bytes, "caption": caption, "ts": msg.get("ts", time.time())})
            rerun_needed = True

        else:
            if "sender" in msg and ("text" in msg or "image_bytes" in msg):
                sender = msg.get("sender")
                if msg.get("text"):
                    st.session_state.chat_log.setdefault(sender, []).append({"sender": sender, "type": "text", "text": msg.get("text"), "ts": time.time()})
                elif msg.get("image_bytes"):
                    st.session_state.chat_log.setdefault(sender, []).append({"sender": sender, "type": "image", "image_bytes": msg.get("image_bytes"), "caption": msg.get("caption",""), "ts": time.time()})
                rerun_needed = True

    if rerun_needed:
        try:
            st.rerun()
        except Exception:
            pass


def logout():
    try:
        if st.session_state.server_socket:
            st.session_state.server_socket.close()
    except:
        pass
    with _peers_lock:
        for p in list(st.session_state.peers.keys()):
            try:
                st.session_state.peers[p]["tcp_sock"].close()
            except:
                pass
            del st.session_state.peers[p]
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.server_socket = None
    st.session_state.chatting_with = None
    st.session_state.online_users = []


def main():
    initialize_session_state()
    st.set_page_config(page_title="Doki Chat P2P", layout="wide")

    if st.session_state.logged_in:
        process_message_queue()
        chat_page()

        time.sleep(0.5)
        st.rerun()

    else:
        login_page()


if __name__ == "__main__":
    main()