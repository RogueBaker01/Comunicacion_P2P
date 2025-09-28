import socket

host = "192.168.1.73"
port = 8080

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.connect((host, port))