from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from backend.database import get_connection, rows_to_list


router = APIRouter()


def redirect_to(url: str):
    return RedirectResponse(url=url, status_code=303)


def gerar_iniciais(nome: str):
    partes = nome.split()

    if not partes:
        return "?"

    iniciais = ""

    for parte in partes[:2]:
        iniciais += parte[0].upper()

    return iniciais


def somente_numeros(texto: str):
    return "".join(caractere for caractere in texto if caractere.isdigit())


def formatar_moeda(valor):
    if valor is None:
        return "Sem contrato"

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(data_texto):
    if not data_texto:
        return "Sem contrato"

    partes = data_texto.split("-")

    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"

    return data_texto


@router.get("/inquilinos")
def pagina_inquilinos(
    request: Request,
    busca: str = Query(default="")
):
    templates = request.app.state.templates

    with get_connection() as conn:
        termo = f"%{busca}%"

        if busca:
            inquilinos = rows_to_list(conn.execute("""
                SELECT
                    i.id,
                    i.nome,
                    i.telefone,
                    i.email,
                    i.cpf,
                    i.created_at,
                    ct.data_inicio,
                    ct.valor_aluguel,
                    im.nome AS imovel_nome
                FROM inquilinos i
                LEFT JOIN contratos ct
                    ON ct.inquilino_id = i.id
                    AND ct.status = 'ativo'
                LEFT JOIN imoveis im
                    ON im.id = ct.imovel_id
                WHERE
                    i.nome LIKE ?
                    OR i.telefone LIKE ?
                    OR i.email LIKE ?
                    OR i.cpf LIKE ?
                    OR im.nome LIKE ?
                ORDER BY i.nome
            """, (termo, termo, termo, termo, termo)).fetchall())
        else:
            inquilinos = rows_to_list(conn.execute("""
                SELECT
                    i.id,
                    i.nome,
                    i.telefone,
                    i.email,
                    i.cpf,
                    i.created_at,
                    ct.data_inicio,
                    ct.valor_aluguel,
                    im.nome AS imovel_nome
                FROM inquilinos i
                LEFT JOIN contratos ct
                    ON ct.inquilino_id = i.id
                    AND ct.status = 'ativo'
                LEFT JOIN imoveis im
                    ON im.id = ct.imovel_id
                ORDER BY i.nome
            """).fetchall())

        interessados = rows_to_list(conn.execute("""
            SELECT
                id,
                nome,
                telefone,
                descricao
            FROM interessados
            ORDER BY id DESC
        """).fetchall())

    for inquilino in inquilinos:
        telefone = inquilino["telefone"] or ""

        inquilino["iniciais"] = gerar_iniciais(inquilino["nome"])
        inquilino["telefone_whatsapp"] = somente_numeros(telefone)
        inquilino["data_inicio"] = formatar_data(inquilino["data_inicio"])
        inquilino["valor_aluguel"] = formatar_moeda(inquilino["valor_aluguel"])

        if not inquilino["imovel_nome"]:
            inquilino["imovel_nome"] = "Sem imóvel vinculado"

        if not inquilino["email"]:
            inquilino["email"] = "Sem e-mail"

    return templates.TemplateResponse(request, "inquilinos.html", {
        "titulo": "Inquilinos",
        "pagina": "inquilinos",
        "busca": busca,
        "inquilinos": inquilinos,
        "interessados": interessados,
    })


@router.post("/inquilinos/criar")
def criar_inquilino(
    nome: str = Form(...),
    telefone: str = Form(""),
    email: str = Form(""),
    cpf: str = Form("")
):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO inquilinos (
                nome,
                telefone,
                email,
                cpf
            )
            VALUES (?, ?, ?, ?)
        """, (
            nome,
            telefone,
            email,
            cpf,
        ))

        conn.commit()

    return redirect_to("/inquilinos")


@router.post("/interessados/criar")
def criar_interessado(
    nome: str = Form(...),
    telefone: str = Form(""),
    descricao: str = Form("")
):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO interessados (
                nome,
                telefone,
                descricao
            )
            VALUES (?, ?, ?)
        """, (
            nome,
            telefone,
            descricao,
        ))

        conn.commit()

    return redirect_to("/inquilinos")


@router.post("/inquilinos/{inquilino_id}/deletar")
def deletar_inquilino(inquilino_id: int):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM inquilinos
            WHERE id = ?
        """, (inquilino_id,))

        conn.commit()

    return redirect_to("/inquilinos")


@router.post("/interessados/{interessado_id}/deletar")
def deletar_interessado(interessado_id: int):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM interessados
            WHERE id = ?
        """, (interessado_id,))

        conn.commit()

    return redirect_to("/inquilinos")