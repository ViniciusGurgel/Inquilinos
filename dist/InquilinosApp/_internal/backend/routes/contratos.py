from pathlib import Path
import shutil
import re

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from backend.database import (
    get_connection,
    rows_to_list,
    gerar_fatura_contrato,
    CONTRATOS_DIR,
)

UPLOAD_DIR = CONTRATOS_DIR
router = APIRouter()


def redirect_to(url: str):
    return RedirectResponse(url=url, status_code=303)


def formatar_moeda(valor):
    if valor is None:
        valor = 0

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(data_texto):
    if not data_texto:
        return "-"

    partes = data_texto.split("-")

    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"

    return data_texto


def limpar_nome_arquivo(nome):
    nome = nome.replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "", nome)


@router.get("/contratos")
def pagina_contratos(request: Request, busca: str = ""):
    templates = request.app.state.templates
    termo = f"%{busca}%"

    with get_connection() as conn:
        if busca:
            contratos = rows_to_list(conn.execute("""
                SELECT
                    c.id,
                    c.valor_aluguel,
                    c.dia_vencimento,
                    c.data_inicio,
                    c.data_fim,
                    c.status,
                    c.caminho_pdf,
                    c.observacao,
                    i.nome AS inquilino_nome,
                    im.nome AS imovel_nome
                FROM contratos c
                INNER JOIN inquilinos i ON i.id = c.inquilino_id
                INNER JOIN imoveis im ON im.id = c.imovel_id
                WHERE
                    i.nome LIKE ?
                    OR im.nome LIKE ?
                    OR c.status LIKE ?
                ORDER BY c.id DESC
            """, (termo, termo, termo)).fetchall())
        else:
            contratos = rows_to_list(conn.execute("""
                SELECT
                    c.id,
                    c.valor_aluguel,
                    c.dia_vencimento,
                    c.data_inicio,
                    c.data_fim,
                    c.status,
                    c.caminho_pdf,
                    c.observacao,
                    i.nome AS inquilino_nome,
                    im.nome AS imovel_nome
                FROM contratos c
                INNER JOIN inquilinos i ON i.id = c.inquilino_id
                INNER JOIN imoveis im ON im.id = c.imovel_id
                ORDER BY c.id DESC
            """).fetchall())

        inquilinos = rows_to_list(conn.execute("""
            SELECT id, nome
            FROM inquilinos
            ORDER BY nome
        """).fetchall())

        imoveis = rows_to_list(conn.execute("""
            SELECT
                im.id,
                im.nome,
                c.nome AS condominio_nome
            FROM imoveis im
            LEFT JOIN condominios c ON c.id = im.condominio_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM contratos ct
                WHERE ct.imovel_id = im.id
                AND ct.status = 'ativo'
            )
            ORDER BY im.nome
        """).fetchall())

    for contrato in contratos:
        contrato["valor_aluguel"] = formatar_moeda(contrato["valor_aluguel"])
        contrato["data_inicio"] = formatar_data(contrato["data_inicio"])
        contrato["data_fim"] = formatar_data(contrato["data_fim"])
        contrato["tem_pdf"] = bool(contrato["caminho_pdf"])

    return templates.TemplateResponse(request, "contratos.html", {
        "titulo": "Contratos",
        "pagina": "contratos",
        "busca": busca,
        "contratos": contratos,
        "inquilinos": inquilinos,
        "imoveis": imoveis,
    })


@router.post("/contratos/criar")
def criar_contrato(
    inquilino_id: int = Form(...),
    imovel_id: int = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(""),
    valor_aluguel: float = Form(...),
    dia_vencimento: int = Form(...),
    observacao: str = Form(""),
    arquivo_pdf: UploadFile | None = File(None),
):
    caminho_pdf = None

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO contratos (
                imovel_id,
                inquilino_id,
                valor_aluguel,
                dia_vencimento,
                data_inicio,
                data_fim,
                status,
                caminho_pdf,
                observacao
            )
            VALUES (?, ?, ?, ?, ?, ?, 'ativo', NULL, ?)
        """, (
            imovel_id,
            inquilino_id,
            valor_aluguel,
            dia_vencimento,
            data_inicio,
            data_fim,
            observacao,
        ))

        contrato_id = cursor.lastrowid

        if arquivo_pdf and arquivo_pdf.filename:
            nome_limpo = limpar_nome_arquivo(arquivo_pdf.filename)
            nome_final = f"contrato_{contrato_id}_{nome_limpo}"
            destino = UPLOAD_DIR / nome_final

            with destino.open("wb") as buffer:
                shutil.copyfileobj(arquivo_pdf.file, buffer)

            caminho_pdf = nome_final

            conn.execute("""
                UPDATE contratos
                SET caminho_pdf = ?
                WHERE id = ?
            """, (
                caminho_pdf,
                contrato_id,
            ))

        conn.commit()

    ano, mes, _ = map(int, data_inicio.split("-"))
    gerar_fatura_contrato(contrato_id, ano, mes)

    return redirect_to("/contratos")


@router.get("/contratos/{contrato_id}/arquivo")
def abrir_arquivo_contrato(contrato_id: int):
    with get_connection() as conn:
        contrato = conn.execute("""
            SELECT caminho_pdf
            FROM contratos
            WHERE id = ?
        """, (contrato_id,)).fetchone()

    if not contrato or not contrato["caminho_pdf"]:
        return redirect_to("/contratos")

    caminho = UPLOAD_DIR / contrato["caminho_pdf"]

    if not caminho.exists():
        return redirect_to("/contratos")

    return FileResponse(
        path=caminho,
        media_type="application/pdf",
        filename=caminho.name
    )


@router.post("/contratos/{contrato_id}/encerrar")
def encerrar_contrato(contrato_id: int):
    with get_connection() as conn:
        conn.execute("""
            UPDATE contratos
            SET status = 'encerrado'
            WHERE id = ?
        """, (contrato_id,))

        conn.commit()

    return redirect_to("/contratos")


@router.post("/contratos/{contrato_id}/deletar")
def deletar_contrato(contrato_id: int):
    with get_connection() as conn:
        contrato = conn.execute("""
            SELECT caminho_pdf
            FROM contratos
            WHERE id = ?
        """, (contrato_id,)).fetchone()

        conn.execute("""
            DELETE FROM contratos
            WHERE id = ?
        """, (contrato_id,))

        conn.commit()

    if contrato and contrato["caminho_pdf"]:
        caminho = UPLOAD_DIR / contrato["caminho_pdf"]

        if caminho.exists():
            caminho.unlink()

    return redirect_to("/contratos")