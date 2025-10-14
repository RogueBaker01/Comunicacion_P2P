import streamlit as st
import socket, threading, json, time, queue

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

st.title("Mensajería P2P - Demo")

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

col1, col2 = st.columns(2)

with col1:
    if not st.session_state.username:
        st.header("Login / Registro")
        uname = st.text_input("Usuario", key="ui_user")
        pw = st.text_input("Contraseña", type="password", key="ui_pw")
        if st.button("Registrar"):
            try:
                s, resp = connect_to_server(username=uname, password=pw, do_register=True)
                st.write(resp)
                s.close()
            except Exception as e:
                st.error("Error registro: " + str(e))
        if st.button("Login"):
            try:
                s, resp = connect_to_server(username=uname, password=pw, do_register=False)
                if resp.get("ok"):
                    st.session_state.server_sock = s
                    st.session_state.username = uname
                    st.success("Login OK")
                    def server_reader(sock, q):
                        recv_lines(sock, out_q=q)
                    threading.Thread(target=server_reader, args=(s, st.session_state.incoming_q), daemon=True).start()

                    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    lsock.bind(("0.0.0.0", 0)) 
                    port = lsock.getsockname()[1]
                    lsock.close()
                    st.session_state.listener_port = port
                    start_listener(port, st.session_state.incoming_q)
                    send_json(st.session_state.server_sock, {"type":"UPDATE_PRESENCE", "username": st.session_state.username, "listen_port": port})
                else:
                    st.error("Login falló")
            except Exception as e:
                st.error("Error login: " + str(e))
    else:
        st.info(f"Conectado como: {st.session_state.username}")
        if st.button("Desconectar"):
            try:
                st.session_state.server_sock.close()
            except:
                pass
            st.session_state.server_sock = None
            st.session_state.username = None

with col2:
    st.header("Usuarios")
    if st.button("Obtener lista usuarios"):
        if st.session_state.server_sock:
            send_json(st.session_state.server_sock, {"type":"GET_USERS"})
        else:
            st.warning("No estás conectado")
    while not st.session_state.incoming_q.empty():
        item = st.session_state.incoming_q.get_nowait()
        if isinstance(item, tuple) and item[0] == "p2p":
            st.session_state.messages.append(("p2p_in", item[1]))
        else:
            msg = item
            t = msg.get("type")
            if t == "USER_LIST":
                st.session_state.users = msg.get("users", [])
            elif t == "P2P_INFO":
                st.session_state.last_p2p_info = msg
            elif t == "RELAY_IN":
                st.session_state.messages.append(("relay_in", msg))
            else:
                st.session_state.messages.append(("server", msg))

    users = st.session_state.get("users", [])
    st.write(users)

    target = st.text_input("Usuario a chatear", key="target_user")
    if st.button("Solicitar P2P"):
        if not st.session_state.server_sock:
            st.warning("No conectado")
        else:
            send_json(st.session_state.server_sock, {"type":"REQUEST_P2P", "from": st.session_state.username, "to": target})
            st.info("Solicitud enviada al servidor")

    if "last_p2p_info" in st.session_state:
        st.write(st.session_state.last_p2p_info)

st.header("Mensajería")
msg_text = st.text_input("Mensaje", key="msgbox")
send_to = st.text_input("Enviar a (username)", key="sendto")
if st.button("Enviar (intentar P2P directo)"):
    if not st.session_state.server_sock:
        st.warning("No conectado")
    else:
        send_json(st.session_state.server_sock, {"type":"REQUEST_P2P", "from": st.session_state.username, "to": send_to})
        time.sleep(0.3)
        p2p_info = getattr(st.session_state, "last_p2p_info", None)
        if p2p_info and p2p_info.get("ok"):
            peer = p2p_info["peer"]
            peer_ip = peer["ip"]
            peer_port = peer["port"]
            st.write("Intentando conectar a", peer_ip, peer_port)
            try:
                psock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                psock.settimeout(2.0)
                psock.connect((peer_ip, peer_port))
                send_json(psock, {"type":"CHAT", "from": st.session_state.username, "to": send_to, "content": msg_text, "ts": time.time()})
                psock.close()
                st.success("Enviado P2P directo")
                st.session_state.messages.append(("out_p2p", {"to": send_to, "content": msg_text}))
            except Exception as e:
                st.warning("Conexión P2P falló, usando relé: " + str(e))
                send_json(st.session_state.server_sock, {"type":"RELAY", "from": st.session_state.username, "to": send_to, "content": msg_text})
        else:
            st.warning("No obtuve info P2P; enviando por relé")
            send_json(st.session_state.server_sock, {"type":"RELAY", "from": st.session_state.username, "to": send_to, "content": msg_text})

st.subheader("Mensajes recibidos / eventos")
for typ, payload in st.session_state.messages[-50:]:
    st.write(typ, payload)

if st.button("Limpiar mensajes"):
    st.session_state.messages = []
