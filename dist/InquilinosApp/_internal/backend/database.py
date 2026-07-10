import sqlite3
from pathlib import Path
from datetime import date
import calendar
import os

APP_DATA_DIR = Path(os.getenv("APPDATA")) / "InquilinosApp"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DATA_DIR / "imoveis.db"

CONTRATOS_DIR = APP_DATA_DIR / "contratos"
CONTRATOS_DIR.mkdir(parents=True, exist_ok=True)

COMPROVANTES_DIR = APP_DATA_DIR / "comprovantes"
COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)

FOTOS_IMOVEIS_DIR = APP_DATA_DIR / "fotos_imoveis"
FOTOS_IMOVEIS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS condominios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cor TEXT DEFAULT '#2f7df6'
        );

        CREATE TABLE IF NOT EXISTS imoveis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT,
            endereco TEXT,
            status TEXT NOT NULL DEFAULT 'disponivel',
            condominio_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (condominio_id) REFERENCES condominios(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS inquilinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            cpf TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contratos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imovel_id INTEGER NOT NULL,
            inquilino_id INTEGER NOT NULL,
            valor_aluguel REAL NOT NULL DEFAULT 0,
            dia_vencimento INTEGER NOT NULL DEFAULT 10,
            data_inicio TEXT NOT NULL,
            data_fim TEXT,
            status TEXT NOT NULL DEFAULT 'ativo',
            caminho_pdf TEXT,
            observacao TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (imovel_id) REFERENCES imoveis(id) ON DELETE CASCADE,
            FOREIGN KEY (inquilino_id) REFERENCES inquilinos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id INTEGER NOT NULL,
            imovel_id INTEGER,
            inquilino_id INTEGER,
            mes_referencia TEXT NOT NULL,
            valor_cobrado REAL NOT NULL DEFAULT 0,
            valor_pago REAL NOT NULL DEFAULT 0,
            data_vencimento TEXT NOT NULL,
            data_pagamento TEXT,
            status TEXT NOT NULL DEFAULT 'pendente',
            comprovante_arquivo TEXT,
            observacao TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
            FOREIGN KEY (imovel_id) REFERENCES imoveis(id) ON DELETE SET NULL,
            FOREIGN KEY (inquilino_id) REFERENCES inquilinos(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS interessados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            descricao TEXT
        );
                           
        CREATE TABLE IF NOT EXISTS imovel_fotos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imovel_id INTEGER NOT NULL,
            arquivo TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (imovel_id) REFERENCES imoveis(id) ON DELETE CASCADE
        );
        """)


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(row) for row in rows]


def proximo_mes(data_base):
    ano = data_base.year
    mes = data_base.month + 1

    if mes > 12:
        mes = 1
        ano += 1

    return date(ano, mes, 1)


def montar_data_vencimento(ano, mes, dia_vencimento):
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(dia_vencimento, ultimo_dia)
    return date(ano, mes, dia)


def gerar_fatura_contrato(contrato_id, ano=None, mes=None):
    hoje = date.today()

    if ano is None:
        ano = hoje.year

    if mes is None:
        mes = hoje.month

    with get_connection() as conn:
        contrato = conn.execute("""
            SELECT *
            FROM contratos
            WHERE id = ? AND status = 'ativo'
        """, (contrato_id,)).fetchone()

        if not contrato:
            return None

        mes_referencia = f"{ano:04d}-{mes:02d}"

        data_vencimento = montar_data_vencimento(
            ano,
            mes,
            contrato["dia_vencimento"]
        )

        fatura_existente = conn.execute("""
            SELECT id
            FROM pagamentos
            WHERE contrato_id = ? AND mes_referencia = ?
        """, (contrato_id, mes_referencia)).fetchone()

        if fatura_existente:
            return fatura_existente["id"]

        cursor = conn.execute("""
            INSERT INTO pagamentos (
                contrato_id,
                imovel_id,
                inquilino_id,
                mes_referencia,
                valor_cobrado,
                data_vencimento,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pendente')
        """, (
            contrato["id"],
            contrato["imovel_id"],
            contrato["inquilino_id"],
            mes_referencia,
            contrato["valor_aluguel"],
            data_vencimento.isoformat()
        ))

        return cursor.lastrowid


def marcar_pagamento_como_pago(pagamento_id, valor_pago=None, data_pagamento=None):
    if data_pagamento is None:
        data_pagamento = date.today().isoformat()

    with get_connection() as conn:
        pagamento = conn.execute("""
            SELECT *
            FROM pagamentos
            WHERE id = ?
        """, (pagamento_id,)).fetchone()

        if not pagamento:
            return None

        if valor_pago is None:
            valor_pago = pagamento["valor_cobrado"]

        conn.execute("""
            UPDATE pagamentos
            SET valor_pago = ?,
                data_pagamento = ?,
                status = 'pago'
            WHERE id = ?
        """, (valor_pago, data_pagamento, pagamento_id))

        contrato_id = pagamento["contrato_id"]
        ano, mes = map(int, pagamento["mes_referencia"].split("-"))

    proxima_data = proximo_mes(date(ano, mes, 1))

    gerar_fatura_contrato(
        contrato_id,
        proxima_data.year,
        proxima_data.month
    )

    return True