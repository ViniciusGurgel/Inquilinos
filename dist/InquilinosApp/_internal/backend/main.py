import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.database import init_db
from backend.routes import dashboard, imoveis, inquilinos, pagamentos, contratos


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def resource_path(relative_path: str):
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path

    return PROJECT_DIR / relative_path


TEMPLATES_DIR = resource_path("templates")
STATIC_DIR = resource_path("static")

app = FastAPI(title="Sistema de Imóveis")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.state.templates = templates


@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def inicio():
    return RedirectResponse(url="/dashboard", status_code=303)

app.include_router(dashboard.router)
app.include_router(imoveis.router)
app.include_router(inquilinos.router)
app.include_router(pagamentos.router)
app.include_router(contratos.router)