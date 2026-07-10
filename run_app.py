import threading
import time
import webbrowser
import traceback

import uvicorn

from backend.main import app


def abrir_navegador():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    try:
        threading.Thread(target=abrir_navegador, daemon=True).start()

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            reload=False,
            log_level="info"
        )

    except Exception:
        traceback.print_exc()
        input("Erro ao iniciar. Pressione ENTER para sair...")