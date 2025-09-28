import socket
import sqlite3
import streamlit as st

host = "192.168.1.73"
port = 8080
conn = sqlite3.connect('login.db')
cursor = conn.cursor()
flag = False

def register():
    st.write("Ingresa tu usuario:")
    username = st.text_input("Usuario")
    st.write("Ingresa tu contraseña:")
    password = st.text_input("Contraseña", type="password")
    if st.button("Registrar"):
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()

def login(flag):
    st.write("Ingresa tu usuario:")
    username = st.text_input("Usuario")
    st.write("Ingresa tu contraseña:")
    password = st.text_input("Contraseña", type="password")
    if st.button("Login"):
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        if cursor.fetchone():
            st.success("Login exitoso")
            flag = True
        else:
            st.error("Login fallido usuario o contraseña incorrectos")
            flag = False
    conn.close()
    return flag

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(10)
    