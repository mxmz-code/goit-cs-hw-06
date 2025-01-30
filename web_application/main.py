import asyncio
import logging
import html
import gzip
import io
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from multiprocessing import Process
import websockets
from datetime import datetime
import json
from pymongo import MongoClient

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Отримання параметрів підключення до MongoDB з оточення
MONGO_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "root")
MONGO_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "example")
MONGO_HOST = "mongodb"

# Підключення до бази даних MongoDB
client = MongoClient(f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:27017/")
db = client["chat_app"]
messages_collection = db["messages"]

# Очікування готовності MongoDB
MAX_RETRIES = 5
for attempt in range(MAX_RETRIES):
    try:
        client.admin.command('ping')
        logging.info("MongoDB готовий до роботи")
        break
    except Exception as e:
        logging.warning(f"MongoDB ще не готовий, спроба {attempt + 1}...")
        time.sleep(5)
else:
    logging.error("MongoDB не запустився після 5 спроб")
    exit(1)

MAX_MESSAGE_LENGTH = 500  # Обмеження довжини повідомлення

def save_message_to_db(username, message):
    """Збереження повідомлення в базу даних"""
    messages_collection.insert_one({"username": username, "message": message, "timestamp": datetime.utcnow()})

def sanitize_input(value):
    """Екранування небезпечних символів (захист від XSS)"""
    return html.escape(value)

def compress_response(response_data):
    """Стиснення відповіді Gzip"""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gzip_file:
        gzip_file.write(response_data)
    return buffer.getvalue()

class HttpHandler(BaseHTTPRequestHandler):
    def log_request(self):
        """Логування запитів"""
        logging.info(f"{self.command} {self.path} від {self.client_address[0]}")

    def do_GET(self):
        """Обробка GET-запитів"""
        self.log_request()
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/":
            self.send_html_file("index.html")
        elif parsed_url.path == "/message.html":
            self.send_html_file("message.html")
        elif parsed_url.path.startswith("/static/"):
            self.send_static_file(parsed_url.path[1:])
        else:
            self.send_error_page(404, "Сторінку не знайдено")

    def do_POST(self):
        """Обробка POST-запитів"""
        self.log_request()
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        parsed_data = parse_qs(post_data.decode("utf-8"))
        username = sanitize_input(parsed_data.get("username")[0])
        message = sanitize_input(parsed_data.get("message")[0])
        
        if len(message) > MAX_MESSAGE_LENGTH:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Повідомлення занадто довге!")
            return
        
        save_message_to_db(username, message)  # Збереження в базу даних
        
        message_data = json.dumps({"username": username, "message": message})

        async def send_message():
            uri = "ws://localhost:6000"
            try:
                async with websockets.connect(uri) as websocket:
                    await websocket.send(message_data)
            except Exception as e:
                logging.error(f"Помилка при відправці через WebSocket: {e}")
        
        loop = asyncio.get_event_loop()
        loop.create_task(send_message())

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Повідомлення надіслано!")  # "Повідомлення надіслано!"

    def send_html_file(self, filename, status=200):
        """Відправка HTML-файлів"""
        try:
            with open(filename, "rb") as file:
                compressed_data = compress_response(file.read())
                self.send_response(status)
                self.send_header("Content-type", "text/html")
                self.send_header("Content-Encoding", "gzip")
                self.end_headers()
                self.wfile.write(compressed_data)
        except FileNotFoundError:
            self.send_error_page(404, "Сторінку не знайдено")

    def send_error_page(self, status, message="Помилка"):
        """Відправка сторінки помилки"""
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(f"<h1>{status} - {message}</h1>".encode("utf-8"))

if __name__ == "__main__":
    server = HTTPServer(("", 8000), HttpHandler)
    logging.info("Сервер запущено на порту 8000...")
    server.serve_forever()
