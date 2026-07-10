from datetime import date
import shutil
import re

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from io import BytesIO

from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from backend.database import (
    get_connection,
    rows_to_list,
    marcar_pagamento_como_pago,
    COMPROVANTES_DIR,
)


router = APIRouter()


MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


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


def obter_mes_base(mes_texto=None):
    if mes_texto:
        try:
            ano, mes = map(int, mes_texto.split("-"))
            return date(ano, mes, 1)
        except ValueError:
            pass

    hoje = date.today()
    return date(hoje.year, hoje.month, 1)


def adicionar_meses(data_base, quantidade):
    novo_mes = data_base.month - 1 + quantidade
    novo_ano = data_base.year + novo_mes // 12
    novo_mes = novo_mes % 12 + 1

    return date(novo_ano, novo_mes, 1)


def formatar_mes_input(data_base):
    return f"{data_base.year:04d}-{data_base.month:02d}"


def formatar_mes_titulo(data_base):
    nome_mes = MESES_PT.get(data_base.month, "")
    return f"{nome_mes} de {data_base.year}"


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
    mes: str | None = Query(default=None),
    editar_id: int | None = Query(default=None)
):
    templates = request.app.state.templates

    mes_base = obter_mes_base(mes)
    mes_selecionado = formatar_mes_input(mes_base)
    mes_anterior = formatar_mes_input(adicionar_meses(mes_base, -1))
    proximo_mes = formatar_mes_input(adicionar_meses(mes_base, 1))
    mes_titulo = formatar_mes_titulo(mes_base)

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
            WHERE p.mes_referencia = ?
            ORDER BY
                p.status = 'pago',
                p.data_vencimento ASC,
                p.id DESC
        """, (mes_selecionado,)).fetchall())

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
        "mes_selecionado": mes_selecionado,
        "mes_titulo": mes_titulo,
        "mes_anterior": mes_anterior,
        "proximo_mes": proximo_mes,
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
            return redirect_to(f"/pagamentos?mes={mes_referencia}")

        pagamento_existente = conn.execute("""
            SELECT id
            FROM pagamentos
            WHERE contrato_id = ?
            AND mes_referencia = ?
        """, (contrato_id, mes_referencia)).fetchone()

        if pagamento_existente:
            return redirect_to(f"/pagamentos?mes={mes_referencia}")

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

    return redirect_to(f"/pagamentos?mes={mes_referencia}")


@router.get("/pagamentos/{pagamento_id}/editar")
def abrir_edicao_pagamento(pagamento_id: int):
    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT mes_referencia
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

    if pagamento:
        return redirect_to(
            f"/pagamentos?mes={pagamento['mes_referencia']}&editar_id={pagamento_id}"
        )

    return redirect_to("/pagamentos")


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
            return redirect_to(f"/pagamentos?mes={mes_referencia}")

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

    return redirect_to(f"/pagamentos?mes={mes_referencia}")


@router.post("/pagamentos/{pagamento_id}/pagar")
def pagar_pagamento(pagamento_id: int):
    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT mes_referencia
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

    marcar_pagamento_como_pago(pagamento_id)

    if pagamento:
        return redirect_to(f"/pagamentos?mes={pagamento['mes_referencia']}")

    return redirect_to("/pagamentos")


@router.post("/pagamentos/{pagamento_id}/deletar")
def deletar_pagamento(pagamento_id: int):
    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT
                mes_referencia,
                comprovante_arquivo
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

        conn.execute("""
            DELETE FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,))

        conn.commit()

    mes_referencia = pagamento["mes_referencia"] if pagamento else None

    if pagamento and pagamento["comprovante_arquivo"]:
        caminho = COMPROVANTES_DIR / pagamento["comprovante_arquivo"]

        if caminho.exists():
            caminho.unlink()

    if mes_referencia:
        return redirect_to(f"/pagamentos?mes={mes_referencia}")

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


@router.get("/pagamentos/relatorio")
def gerar_relatorio_pagamentos(
    mes_inicio: str = Query(...),
    mes_fim: str = Query(...)
):
    try:
        data_inicio = obter_mes_base(mes_inicio)
        data_fim = obter_mes_base(mes_fim)
    except Exception:
        return redirect_to("/pagamentos")

    if data_inicio > data_fim:
        mes_inicio, mes_fim = mes_fim, mes_inicio
        data_inicio, data_fim = data_fim, data_inicio

    with get_connection() as conn:
        pagamentos = rows_to_list(conn.execute("""
            SELECT
                p.id,
                p.mes_referencia,
                p.valor_cobrado,
                p.valor_pago,
                p.data_vencimento,
                p.data_pagamento,
                p.status,
                i.nome AS inquilino_nome,
                im.nome AS imovel_nome
            FROM pagamentos p
            LEFT JOIN inquilinos i ON i.id = p.inquilino_id
            LEFT JOIN imoveis im ON im.id = p.imovel_id
            WHERE p.status = 'pago'
            AND p.mes_referencia BETWEEN ? AND ?
            ORDER BY p.mes_referencia ASC, p.data_pagamento ASC
        """, (mes_inicio, mes_fim)).fetchall())

    total_recebido = sum(float(p["valor_pago"] or 0) for p in pagamentos)

    buffer = BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )

    estilos = getSampleStyleSheet()
    elementos = []

    titulo = "Relatório de Pagamentos Realizados"
    periodo = f"Período: {formatar_mes_titulo(data_inicio)} até {formatar_mes_titulo(data_fim)}"

    elementos.append(Paragraph(titulo, estilos["Title"]))
    elementos.append(Spacer(1, 8))
    elementos.append(Paragraph(periodo, estilos["Normal"]))
    elementos.append(Spacer(1, 12))
    elementos.append(Paragraph(f"Total recebido: {formatar_moeda(total_recebido)}", estilos["Heading2"]))
    elementos.append(Spacer(1, 16))

    dados_tabela = [
        ["Inquilino", "Imóvel", "Mês", "Vencimento", "Pagamento", "Valor"]
    ]

    for pagamento in pagamentos:
        dados_tabela.append([
            pagamento["inquilino_nome"] or "Sem inquilino",
            pagamento["imovel_nome"] or "Sem imóvel",
            pagamento["mes_referencia"],
            formatar_data(pagamento["data_vencimento"]),
            formatar_data(pagamento["data_pagamento"]),
            formatar_moeda(pagamento["valor_pago"]),
        ])

    if len(dados_tabela) == 1:
        dados_tabela.append([
            "-",
            "-",
            "-",
            "-",
            "-",
            "Nenhum pagamento pago no período",
        ])

    dados_tabela.append([
        "",
        "",
        "",
        "",
        "Total",
        formatar_moeda(total_recebido),
    ])

    tabela = Table(
        dados_tabela,
        repeatRows=1,
        colWidths=[
            3.2 * cm,
            3.2 * cm,
            2.2 * cm,
            2.5 * cm,
            2.5 * cm,
            2.8 * cm,
        ],
    )

    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d2a3d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
        ("FONTNAME", (4, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f4f6")),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(tabela)

    documento.build(elementos)

    buffer.seek(0)

    nome_arquivo = f"relatorio_pagamentos_{mes_inicio}_a_{mes_fim}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"'
        }
    )