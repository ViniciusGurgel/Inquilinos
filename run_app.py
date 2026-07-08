import threading
import time
import webbrowser

import uvicorn


def abrir_navegador():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


def iniciar_servidor():
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )


if __name__ == "__main__":
    threading.Thread(target=abrir_navegador, daemon=True).start()
    iniciar_servidor()