import socket
import sqlite3
import streamlit as st

host = "192.168.1.73"
port = 8080
conn = sqlite3.connect('login.db')
cursor = conn.cursor()
flag = False

def verificar_usuario():
    command_sql = 'SELECT '
    return

def register():
    return

def login():
    return

def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.listen(10)
    verificar_usuario()

    client_socket.accept()

