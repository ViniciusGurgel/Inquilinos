from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from backend.database import get_connection, rows_to_list


router = APIRouter()


def redirect_to(url: str):
    return RedirectResponse(url=url, status_code=303)


@router.get("/imoveis")
def pagina_imoveis(
    request: Request,
    busca: str = Query(default="")
):
    templates = request.app.state.templates

    with get_connection() as conn:
        termo = f"%{busca}%"

        if busca:
            imoveis = rows_to_list(conn.execute("""
                SELECT
                    i.id,
                    i.nome,
                    i.tipo,
                    i.endereco,
                    i.status,
                    i.condominio_id,
                    c.nome AS condominio_nome,
                    q.inquilino_nome
                FROM imoveis i
                LEFT JOIN condominios c ON c.id = i.condominio_id
                LEFT JOIN (
                    SELECT
                        contratos.imovel_id,
                        inquilinos.nome AS inquilino_nome
                    FROM contratos
                    INNER JOIN inquilinos ON inquilinos.id = contratos.inquilino_id
                    WHERE contratos.status = 'ativo'
                ) q ON q.imovel_id = i.id
                WHERE
                    i.nome LIKE ?
                    OR i.endereco LIKE ?
                    OR i.tipo LIKE ?
                    OR c.nome LIKE ?
                ORDER BY i.nome
            """, (termo, termo, termo, termo)).fetchall())

            condominios = rows_to_list(conn.execute("""
                SELECT
                    c.id,
                    c.nome,
                    c.cor,
                    COUNT(i.id) AS total_imoveis
                FROM condominios c
                LEFT JOIN imoveis i ON i.condominio_id = c.id
                WHERE c.nome LIKE ?
                GROUP BY c.id, c.nome, c.cor
                ORDER BY c.nome
            """, (termo,)).fetchall())

        else:
            imoveis = rows_to_list(conn.execute("""
                SELECT
                    i.id,
                    i.nome,
                    i.tipo,
                    i.endereco,
                    i.status,
                    i.condominio_id,
                    c.nome AS condominio_nome,
                    q.inquilino_nome
                FROM imoveis i
                LEFT JOIN condominios c ON c.id = i.condominio_id
                LEFT JOIN (
                    SELECT
                        contratos.imovel_id,
                        inquilinos.nome AS inquilino_nome
                    FROM contratos
                    INNER JOIN inquilinos ON inquilinos.id = contratos.inquilino_id
                    WHERE contratos.status = 'ativo'
                ) q ON q.imovel_id = i.id
                ORDER BY i.nome
            """).fetchall())

            condominios = rows_to_list(conn.execute("""
                SELECT
                    c.id,
                    c.nome,
                    c.cor,
                    COUNT(i.id) AS total_imoveis
                FROM condominios c
                LEFT JOIN imoveis i ON i.condominio_id = c.id
                GROUP BY c.id, c.nome, c.cor
                ORDER BY c.nome
            """).fetchall())

    return templates.TemplateResponse(request,"imoveis.html", {
        "request": request,
        "titulo": "Imóveis",
        "pagina": "imoveis",
        "busca": busca,
        "imoveis": imoveis,
        "condominios": condominios,
    })


@router.post("/imoveis/criar")
def criar_imovel(
    nome: str = Form(...),
    tipo: str = Form(...),
    endereco: str = Form(...),
    condominio_id: str = Form(default="")
):
    condominio_id_final = int(condominio_id) if condominio_id else None

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO imoveis (
                nome,
                tipo,
                endereco,
                status,
                condominio_id
            )
            VALUES (?, ?, ?, 'disponivel', ?)
        """, (
            nome,
            tipo,
            endereco,
            condominio_id_final,
        ))

        conn.commit()

    return redirect_to("/imoveis")


@router.post("/condominios/criar")
def criar_condominio(
    nome: str = Form(...),
    cor: str = Form("#2f7df6")
):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO condominios (
                nome,
                cor
            )
            VALUES (?, ?)
        """, (
            nome,
            cor,
        ))

        conn.commit()

    return redirect_to("/imoveis")


@router.post("/imoveis/{imovel_id}/deletar")
def deletar_imovel(imovel_id: int):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM imoveis
            WHERE id = ?
        """, (imovel_id,))

        conn.commit()

    return redirect_to("/imoveis")


@router.post("/condominios/{condominio_id}/deletar")
def deletar_condominio(condominio_id: int):
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM condominios
            WHERE id = ?
        """, (condominio_id,))

        conn.commit()

    return redirect_to("/imoveis")