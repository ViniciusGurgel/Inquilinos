from datetime import date
from pathlib import Path
import shutil
import re

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from backend.database import (
    get_connection,
    rows_to_list,
    marcar_pagamento_como_pago,
    COMPROVANTES_DIR,
)


router = APIRouter()

def limpar_nome_arquivo(nome):
    nome = nome.replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "", nome)

def redirect_to(url: str):
    return RedirectResponse(url=url, status_code=303)


def formatar_moeda(valor):
    if valor is None:
        valor = 0

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(data_texto):
    if not data_texto:
        return ""

    partes = data_texto.split("-")

    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"

    return data_texto


def formatar_mes_referencia(mes_referencia):
    if not mes_referencia:
        return ""

    partes = mes_referencia.split("-")

    if len(partes) == 2:
        return f"{partes[1]}/{partes[0]}"

    return mes_referencia


def calcular_status_pagamento(pagamento):
    if pagamento["status"] == "pago":
        return "pago"

    if pagamento["data_vencimento"]:
        try:
            vencimento = date.fromisoformat(pagamento["data_vencimento"])

            if vencimento < date.today():
                return "atrasado"
        except ValueError:
            return "pendente"

    return "pendente"


@router.get("/pagamentos")
def pagina_pagamentos(
    request: Request,
    editar_id: int | None = Query(default=None)
):
    templates = request.app.state.templates

    with get_connection() as conn:
        pagamentos = rows_to_list(conn.execute("""
            SELECT
                p.id,
                p.contrato_id,
                p.imovel_id,
                p.inquilino_id,
                p.mes_referencia,
                p.valor_cobrado,
                p.valor_pago,
                p.data_vencimento,
                p.data_pagamento,
                p.status,
                p.comprovante_arquivo,
                p.observacao,
                i.nome AS inquilino_nome,
                im.nome AS imovel_nome
            FROM pagamentos p
            LEFT JOIN inquilinos i ON i.id = p.inquilino_id
            LEFT JOIN imoveis im ON im.id = p.imovel_id
            ORDER BY
                p.status = 'pago',
                p.data_vencimento ASC,
                p.id DESC
        """).fetchall())

        contratos = rows_to_list(conn.execute("""
            SELECT
                c.id,
                c.valor_aluguel,
                c.dia_vencimento,
                c.data_inicio,
                i.nome AS inquilino_nome,
                im.nome AS imovel_nome
            FROM contratos c
            INNER JOIN inquilinos i ON i.id = c.inquilino_id
            INNER JOIN imoveis im ON im.id = c.imovel_id
            WHERE c.status = 'ativo'
            ORDER BY i.nome, im.nome
        """).fetchall())

        pagamento_edicao = None

        if editar_id:
            pagamento_edicao = conn.execute("""
                SELECT
                    p.id,
                    p.contrato_id,
                    p.imovel_id,
                    p.inquilino_id,
                    p.mes_referencia,
                    p.valor_cobrado,
                    p.valor_pago,
                    p.data_vencimento,
                    p.data_pagamento,
                    p.status,
                    p.comprovante_arquivo,
                    p.observacao
                FROM pagamentos p
                WHERE p.id = ?
            """, (editar_id,)).fetchone()

            if pagamento_edicao:
                pagamento_edicao = dict(pagamento_edicao)

    total_recebido = 0
    total_pendente = 0
    total_atrasado = 0

    for pagamento in pagamentos:
        valor_cobrado = float(pagamento["valor_cobrado"] or 0)
        valor_pago = float(pagamento["valor_pago"] or 0)

        status_calculado = calcular_status_pagamento(pagamento)

        pagamento["status"] = status_calculado
        pagamento["tem_comprovante"] = bool(pagamento["comprovante_arquivo"])
        pagamento["mes_referencia"] = formatar_mes_referencia(pagamento["mes_referencia"])
        pagamento["data_vencimento"] = formatar_data(pagamento["data_vencimento"])
        pagamento["valor_cobrado"] = formatar_moeda(valor_cobrado)
        pagamento["valor_pago"] = formatar_moeda(valor_pago)
        pagamento["total"] = formatar_moeda(valor_cobrado)

        if not pagamento["inquilino_nome"]:
            pagamento["inquilino_nome"] = "Sem inquilino"

        if not pagamento["imovel_nome"]:
            pagamento["imovel_nome"] = "Sem imóvel"

        if status_calculado == "pago":
            total_recebido += valor_pago

        elif status_calculado == "atrasado":
            total_atrasado += valor_cobrado

        else:
            total_pendente += valor_cobrado

    return templates.TemplateResponse(request, "pagamentos.html", {
        "titulo": "Pagamentos",
        "pagina": "pagamentos",
        "pagamentos": pagamentos,
        "contratos": contratos,
        "pagamento_edicao": pagamento_edicao,
        "total_recebido": formatar_moeda(total_recebido),
        "total_pendente": formatar_moeda(total_pendente),
        "total_atrasado": formatar_moeda(total_atrasado),
    })


@router.post("/pagamentos/criar")
def criar_pagamento(
    contrato_id: int = Form(...),
    mes_referencia: str = Form(...),
    valor_cobrado: float = Form(...),
    data_vencimento: str = Form(...),
    observacao: str = Form(""),
    comprovante: UploadFile | None = File(None)
):
    with get_connection() as conn:
        contrato = conn.execute("""
            SELECT
                id,
                imovel_id,
                inquilino_id
            FROM contratos
            WHERE id = ?
            AND status = 'ativo'
        """, (contrato_id,)).fetchone()

        if not contrato:
            return redirect_to("/pagamentos")

        pagamento_existente = conn.execute("""
            SELECT id
            FROM pagamentos
            WHERE contrato_id = ?
            AND mes_referencia = ?
        """, (contrato_id, mes_referencia)).fetchone()

        if pagamento_existente:
            return redirect_to("/pagamentos")

        cursor = conn.execute("""
            INSERT INTO pagamentos (
                contrato_id,
                imovel_id,
                inquilino_id,
                mes_referencia,
                valor_cobrado,
                valor_pago,
                data_vencimento,
                status,
                comprovante_arquivo,
                observacao
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, 'pendente', NULL, ?)
        """, (
            contrato_id,
            contrato["imovel_id"],
            contrato["inquilino_id"],
            mes_referencia,
            valor_cobrado,
            data_vencimento,
            observacao,
        ))

        pagamento_id = cursor.lastrowid

        if comprovante and comprovante.filename:
            nome_limpo = limpar_nome_arquivo(comprovante.filename)
            nome_final = f"pagamento_{pagamento_id}_{nome_limpo}"
            destino = COMPROVANTES_DIR / nome_final

            with destino.open("wb") as buffer:
                shutil.copyfileobj(comprovante.file, buffer)

            conn.execute("""
                UPDATE pagamentos
                SET comprovante_arquivo = ?
                WHERE id = ?
            """, (nome_final, pagamento_id))

        conn.commit()

    return redirect_to("/pagamentos")


@router.get("/pagamentos/{pagamento_id}/editar")
def abrir_edicao_pagamento(pagamento_id: int):
    return redirect_to(f"/pagamentos?editar_id={pagamento_id}")


@router.post("/pagamentos/{pagamento_id}/editar")
def editar_pagamento(
    pagamento_id: int,
    contrato_id: int = Form(...),
    mes_referencia: str = Form(...),
    valor_cobrado: float = Form(...),
    data_vencimento: str = Form(...),
    status: str = Form("pendente"),
    observacao: str = Form(""),
    comprovante: UploadFile | None = File(None)
):
    with get_connection() as conn:
        contrato = conn.execute("""
            SELECT
                id,
                imovel_id,
                inquilino_id
            FROM contratos
            WHERE id = ?
            AND status = 'ativo'
        """, (contrato_id,)).fetchone()

        if not contrato:
            return redirect_to("/pagamentos")

        pagamento_atual = conn.execute("""
            SELECT comprovante_arquivo
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

        comprovante_arquivo = pagamento_atual["comprovante_arquivo"] if pagamento_atual else None

        if comprovante and comprovante.filename:
            nome_limpo = limpar_nome_arquivo(comprovante.filename)
            nome_final = f"pagamento_{pagamento_id}_{nome_limpo}"
            destino = COMPROVANTES_DIR / nome_final

            with destino.open("wb") as buffer:
                shutil.copyfileobj(comprovante.file, buffer)

            if comprovante_arquivo:
                antigo = COMPROVANTES_DIR / comprovante_arquivo
                if antigo.exists():
                    antigo.unlink()

            comprovante_arquivo = nome_final

        if status == "pago":
            valor_pago = valor_cobrado
            data_pagamento = date.today().isoformat()
        else:
            valor_pago = 0
            data_pagamento = None
            status = "pendente"

        conn.execute("""
            UPDATE pagamentos
            SET
                contrato_id = ?,
                imovel_id = ?,
                inquilino_id = ?,
                mes_referencia = ?,
                valor_cobrado = ?,
                valor_pago = ?,
                data_vencimento = ?,
                data_pagamento = ?,
                status = ?,
                comprovante_arquivo = ?,
                observacao = ?
            WHERE id = ?
        """, (
            contrato_id,
            contrato["imovel_id"],
            contrato["inquilino_id"],
            mes_referencia,
            valor_cobrado,
            valor_pago,
            data_vencimento,
            data_pagamento,
            status,
            comprovante_arquivo,
            observacao,
            pagamento_id,
        ))

        conn.commit()

    return redirect_to("/pagamentos")


@router.post("/pagamentos/{pagamento_id}/pagar")
def pagar_pagamento(pagamento_id: int):
    marcar_pagamento_como_pago(pagamento_id)

    return redirect_to("/pagamentos")


@router.post("/pagamentos/{pagamento_id}/deletar")
def deletar_pagamento(pagamento_id: int):
    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT comprovante_arquivo
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

        conn.execute("""
            DELETE FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,))

        conn.commit()

    if pagamento and pagamento["comprovante_arquivo"]:
        caminho = COMPROVANTES_DIR / pagamento["comprovante_arquivo"]

        if caminho.exists():
            caminho.unlink()

    return redirect_to("/pagamentos")

@router.get("/pagamentos/{pagamento_id}/comprovante")
def abrir_comprovante(pagamento_id: int):
    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT comprovante_arquivo
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

    if not pagamento or not pagamento["comprovante_arquivo"]:
        return redirect_to("/pagamentos")

    caminho = COMPROVANTES_DIR / pagamento["comprovante_arquivo"]

    if not caminho.exists():
        return redirect_to("/pagamentos")

    return FileResponse(
        path=caminho,
        filename=caminho.name
    )