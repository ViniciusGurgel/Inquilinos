from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/historico")
def pagina_historico(request: Request):
    templates = request.app.state.templates

    return templates.TemplateResponse(request, "em_breve.html", {
        "titulo": "Histórico",
        "pagina": "historico",
        "recurso": "Histórico",
        "descricao": "Estamos preparando uma área para consultar alterações, pagamentos antigos, contratos encerrados e registros importantes do sistema.",
        "icone": "history",
    })


@router.get("/configuracoes")
def pagina_configuracoes(request: Request):
    templates = request.app.state.templates

    return templates.TemplateResponse(request, "em_breve.html", {
        "titulo": "Configurações",
        "pagina": "configuracoes",
        "recurso": "Configurações",
        "descricao": "Estamos preparando uma área para personalizar o sistema, ajustar preferências, dados do app e opções de funcionamento.",
        "icone": "settings",
    })