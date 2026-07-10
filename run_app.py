import os
import sys
import socket
import threading
import time
import webbrowser
import traceback
from pathlib import Path

import uvicorn

from backend.main import app


HOST = "127.0.0.1"
PORT = 8000
APP_URL = f"http://{HOST}:{PORT}"

APP_DATA_DIR = Path(os.getenv("APPDATA", ".")) / "InquilinosApp"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = APP_DATA_DIR / "erro_app.log"

ultimo_heartbeat = time.time()
navegador_conectado = False


def corrigir_console_noconsole():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")

    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")


def servidor_ja_rodando():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5):
            return True
    except OSError:
        return False


def abrir_navegador():
    time.sleep(2)
    webbrowser.open(APP_URL)


def encerrar_app():
    time.sleep(0.5)
    os._exit(0)


def monitorar_navegador():
    while True:
        time.sleep(5)

        navegador_conectado = getattr(app.state, "navegador_conectado", False)
        ultimo_heartbeat = getattr(app.state, "ultimo_heartbeat", time.time())

        if navegador_conectado:
            tempo_sem_pagina = time.time() - ultimo_heartbeat

            if tempo_sem_pagina > 30:
                os._exit(0)

if __name__ == "__main__":
    corrigir_console_noconsole()

    try:
        if servidor_ja_rodando():
            webbrowser.open(APP_URL)
            sys.exit(0)

        threading.Thread(target=monitorar_navegador, daemon=True).start()
        threading.Thread(target=abrir_navegador, daemon=True).start()

        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            reload=False,
            log_config=None,
            access_log=False,
            log_level="critical"
        )

    except Exception:
        erro = traceback.format_exc()
        LOG_FILE.write_text(erro, encoding="utf-8")