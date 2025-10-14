# 🚀 Plataforma de Mensajería P2P

Una plataforma de mensajería híbrida que utiliza un servidor central para autenticación y un sistema peer-to-peer (P2P) para el intercambio directo de mensajes.

## 📋 Características

- **Autenticación centralizada**: Registro e inicio de sesión a través de servidor central
- **Base de datos SQLite**: Almacenamiento persistente de usuarios
- **Comunicación P2P**: Chat directo entre usuarios sin intermediarios
- **Multi-threaded**: Soporte para múltiples conexiones simultáneas
- **Interfaz de consola**: Menús intuitivos y fáciles de usar

## 🏗️ Arquitectura del Sistema

### 1. Servidor Central (`server.py`)
- **Función**: Maneja autenticación, registro y facilitación de conexiones P2P
- **Puerto**: 8080
- **Responsabilidades**:
  - Registro de nuevos usuarios
  - Validación de credenciales de login
  - Mantenimiento de lista de usuarios conectados
  - Facilitación de información P2P entre clientes

### 2. Cliente P2P (`cliente.py`)
- **Función**: Aplicación cliente que se conecta al servidor y permite chat P2P
- **Puertos P2P**: 9000+ (se asigna automáticamente)
- **Responsabilidades**:
  - Interfaz de usuario para login/registro
  - Establecimiento de conexiones P2P
  - Intercambio directo de mensajes

## 🔄 Flujo de Funcionamiento

```
1. Cliente → Servidor: Login/Registro
2. Servidor → Base de datos: Verificación de credenciales
3. Cliente → Servidor: Solicitar lista de usuarios conectados
4. Cliente A → Servidor: Solicitar información P2P de Cliente B
5. Servidor → Cliente A: IP y puerto P2P de Cliente B
6. Cliente A ←→ Cliente B: Conexión directa P2P
7. Cliente A ←→ Cliente B: Intercambio de mensajes (sin servidor)
```

## 📡 Protocolo de Comunicación

### Mensajes Cliente → Servidor

#### Registro
```json
{
    "action": "register",
    "username": "usuario123",
    "password": "mi_password",
    "email": "usuario@email.com"
}
```

#### Login
```json
{
    "action": "login",
    "username": "usuario123",
    "password": "mi_password",
    "p2p_port": 9001
}
```

#### Solicitar usuarios conectados
```json
{
    "action": "get_users"
}
```

#### Solicitar información P2P
```json
{
    "action": "request_p2p",
    "target_user": "usuario456"
}
```

### Respuestas Servidor → Cliente

#### Respuesta de registro
```json
{
    "action": "register_response",
    "success": true,
    "message": "Usuario registrado exitosamente"
}
```

#### Respuesta de login
```json
{
    "action": "login_response",
    "success": true,
    "message": "Login exitoso",
    "username": "usuario123"
}
```

#### Lista de usuarios
```json
{
    "action": "users_list",
    "users": [
        {
            "username": "usuario456",
            "ip": "192.168.1.74",
            "p2p_port": 9002
        }
    ]
}
```

#### Información P2P
```json
{
    "action": "p2p_info",
    "target_user": "usuario456",
    "target_ip": "192.168.1.74",
    "target_port": 9002
}
```

### Mensajes P2P Entre Clientes

#### Mensaje de chat
```json
{
    "message": "Hola, ¿cómo estás?"
}
```

## 🚀 Instalación y Uso

### Prerrequisitos
- Python 3.6 o superior
- Módulos estándar de Python (socket, sqlite3, json, threading)

### Pasos de instalación

1. **Clonar o descargar el proyecto**
```bash
git clone [url-del-repositorio]
cd Comunicacion_P2P
```

2. **Configurar la IP del servidor**
   - Editar `server.py` línea 8: `HOST = "TU_IP_AQUI"`
   - Editar `cliente.py` línea 9: `self.server_host = "TU_IP_AQUI"`

### Ejecutar el Sistema

#### 1. Iniciar el Servidor
```bash
python server.py
```

Verás el mensaje:
```
Base de datos inicializada correctamente
Servidor iniciado en 192.168.1.73:8080
Esperando conexiones...
```

#### 2. Ejecutar Clientes
Abre nuevas terminales y ejecuta:
```bash
python cliente.py
```

### Usar la Aplicación

#### Primera vez - Registro
1. Ejecutar cliente
2. Seleccionar opción "2. Registrarse"
3. Ingresar: nombre de usuario, contraseña y email
4. Iniciar sesión con las credenciales creadas

#### Chat P2P
1. Iniciar sesión
2. Seleccionar "1. Ver usuarios conectados y chatear"
3. Elegir un usuario de la lista
4. ¡Comenzar a chatear!
5. Escribir "exit" para salir del chat

## 🔧 Configuración Técnica

### Puertos Utilizados
- **Servidor central**: 8080
- **P2P clientes**: 9000-9099 (asignación automática)

### Base de Datos
- **Archivo**: `users.db` (SQLite)
- **Tabla**: `users` (id, username, password, email, created_at)

### Manejo de Errores
- Usuarios duplicados en registro
- Credenciales incorrectas en login
- Usuarios ya conectados desde otra sesión
- Puertos P2P no disponibles
- Fallos de conexión P2P

## 🔒 Seguridad

⚠️ **IMPORTANTE**: Este es un proyecto educativo. Para uso en producción, implementar:
- Encriptación de contraseñas (hash + salt)
- Conexiones SSL/TLS
- Validación de entrada más robusta
- Manejo de sesiones seguro

## 🐛 Solución de Problemas

### Error: "No se puede conectar al servidor"
- Verificar que el servidor esté ejecutándose
- Comprobar la IP configurada en cliente.py
- Verificar firewall y puertos

### Error: "Puerto P2P no disponible"
- El sistema busca automáticamente puertos libres
- Si persiste, reiniciar cliente

### Error: "Usuario ya conectado"
- Solo una sesión por usuario simultáneamente
- Cerrar otras sesiones del mismo usuario

## 📝 Estructura de Archivos

```
Comunicacion_P2P/
├── server.py          # Servidor central
├── cliente.py         # Cliente P2P
├── users.db          # Base de datos SQLite (se crea automáticamente)
├── README.md         # Este archivo
└── LICENSE           # Licencia del proyecto
```

## 🤝 Contribuir

1. Fork del proyecto
2. Crear rama para nueva funcionalidad
3. Commit de los cambios
4. Push a la rama
5. Crear Pull Request

## 📄 Licencia

Este proyecto está bajo la licencia especificada en el archivo `LICENSE`.

---
**Desarrollado para el curso de Sistemas Distribuidos**