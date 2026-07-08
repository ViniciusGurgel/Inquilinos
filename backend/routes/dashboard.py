from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Request
from backend.database import get_connection, rows_to_list


router = APIRouter()


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


def calcular_status_pagamento(pagamento):
    if pagamento["status"] == "pago":
        return "pago"

    if pagamento["data_vencimento"]:
        try:
            vencimento = date.fromisoformat(pagamento["data_vencimento"])

            if vencimento < date.today():
                return "atrasado"
        except ValueError:
            pass

    return "pendente"


@router.get("/dashboard")
def pagina_dashboard(request: Request):
    templates = request.app.state.templates
    mes_atual = date.today().strftime("%Y-%m")

    with get_connection() as conn:
        total_imoveis = conn.execute("""
            SELECT COUNT(*)
            FROM imoveis
        """).fetchone()[0]

        total_inquilinos = conn.execute("""
            SELECT COUNT(*)
            FROM inquilinos
        """).fetchone()[0]

        contratos_ativos = conn.execute("""
            SELECT COUNT(*)
            FROM contratos
            WHERE status = 'ativo'
        """).fetchone()[0]

        total_alugados = conn.execute("""
            SELECT COUNT(DISTINCT imovel_id)
            FROM contratos
            WHERE status = 'ativo'
        """).fetchone()[0]

        total_disponiveis = conn.execute("""
            SELECT COUNT(*)
            FROM imoveis i
            WHERE NOT EXISTS (
                SELECT 1
                FROM contratos c
                WHERE c.imovel_id = i.id
                AND c.status = 'ativo'
            )
        """).fetchone()[0]

        receita_mensal = conn.execute("""
            SELECT COALESCE(SUM(valor_pago), 0)
            FROM pagamentos
            WHERE status = 'pago'
            AND substr(data_pagamento, 1, 7) = ?
        """, (mes_atual,)).fetchone()[0]

        pagamentos = rows_to_list(conn.execute("""
            SELECT
                p.id,
                p.mes_referencia,
                p.valor_cobrado,
                p.valor_pago,
                p.data_vencimento,
                p.data_pagamento,
                p.status,
                p.observacao,
                i.nome AS inquilino_nome,
                im.nome AS imovel_nome
            FROM pagamentos p
            LEFT JOIN inquilinos i ON i.id = p.inquilino_id
            LEFT JOIN imoveis im ON im.id = p.imovel_id
            ORDER BY p.data_vencimento ASC
        """).fetchall())

        imoveis_disponiveis = rows_to_list(conn.execute("""
            SELECT
                i.id,
                i.nome,
                i.tipo,
                i.endereco,
                c.nome AS condominio_nome
            FROM imoveis i
            LEFT JOIN condominios c ON c.id = i.condominio_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM contratos ct
                WHERE ct.imovel_id = i.id
                AND ct.status = 'ativo'
            )
            ORDER BY i.nome
            LIMIT 6
        """).fetchall())

        interessados = rows_to_list(conn.execute("""
            SELECT
                id,
                nome,
                telefone,
                descricao
            FROM interessados
            ORDER BY id DESC
            LIMIT 5
        """).fetchall())
    
    for interessado in interessados:
        interessado["whatsapp_link"] = montar_link_whatsapp(
            interessado["telefone"],
            interessado["nome"]
        )

    pagamentos_pendentes = 0
    pagamentos_atrasados = 0
    vencimentos = []

    for pagamento in pagamentos:
        status_calculado = calcular_status_pagamento(pagamento)

        pagamento["status_calculado"] = status_calculado
        pagamento["data_vencimento_formatada"] = formatar_data(pagamento["data_vencimento"])
        pagamento["valor_cobrado_formatado"] = formatar_moeda(pagamento["valor_cobrado"])

        if status_calculado == "pendente":
            pagamentos_pendentes += 1
            vencimentos.append(pagamento)

        elif status_calculado == "atrasado":
            pagamentos_atrasados += 1
            vencimentos.append(pagamento)

    vencimentos = vencimentos[:5]

    return templates.TemplateResponse(request, "dashboard.html", {
        "titulo": "Dashboard",
        "pagina": "dashboard",

        "total_imoveis": total_imoveis,
        "total_disponiveis": total_disponiveis,
        "total_alugados": total_alugados,
        "total_inquilinos": total_inquilinos,
        "contratos_ativos": contratos_ativos,

        "receita_mensal": receita_mensal,
        "receita_mensal_formatada": formatar_moeda(receita_mensal),

        "pagamentos_pendentes": pagamentos_pendentes,
        "pagamentos_atrasados": pagamentos_atrasados,

        "imoveis_disponiveis": imoveis_disponiveis,
        "vencimentos": vencimentos,
        "interessados": interessados,
    })


def somente_numeros(texto):
    return "".join(caractere for caractere in (texto or "") if caractere.isdigit())


def formatar_telefone_whatsapp(telefone):
    numero = somente_numeros(telefone)

    # Se digitou com zero na frente, remove.
    # Ex: 061999999999 -> 61999999999
    if numero.startswith("0"):
        numero = numero[1:]

    # Se já veio com código do Brasil, mantém.
    # Ex: 5561999999999
    if numero.startswith("55"):
        return numero

    # Se veio só DDD + número, adiciona 55.
    # Ex: 61999999999 -> 5561999999999
    if len(numero) in (10, 11):
        return "55" + numero

    return numero


def saudacao_por_horario():
    hora = datetime.now().hour

    if hora < 12:
        return "Bom dia"

    if hora < 18:
        return "Boa tarde"

    return "Boa noite"


def montar_link_whatsapp(telefone, nome):
    numero = formatar_telefone_whatsapp(telefone)

    mensagem = f"{saudacao_por_horario()}, {nome}!"
    mensagem_formatada = quote(mensagem)

    return f"https://api.whatsapp.com/send?phone={numero}&text={mensagem_formatada}"