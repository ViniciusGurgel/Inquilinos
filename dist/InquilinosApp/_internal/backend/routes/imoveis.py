from datetime import datetime
from pathlib import Path
import re
import shutil

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from backend.database import (
    FOTOS_IMOVEIS_DIR,
    get_connection,
    rows_to_list,
)


router = APIRouter()


def redirect_to(url: str):
    return RedirectResponse(url=url, status_code=303)


def limpar_nome_arquivo(nome):
    nome = nome.replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]", "", nome)


def montar_url_imoveis(condominio_id=None, detalhe_id=None, aba=None, busca=None):
    parametros = []

    if condominio_id:
        parametros.append(f"condominio_id={condominio_id}")

    if detalhe_id:
        parametros.append(f"detalhe_id={detalhe_id}")

    if aba:
        parametros.append(f"aba={aba}")

    if busca:
        parametros.append(f"busca={busca}")

    if parametros:
        return "/imoveis?" + "&".join(parametros)

    return "/imoveis"


def buscar_imoveis(conn, busca="", condominio_id=None, filtro_status="todos"):
    parametros = []
    filtros = []

    if condominio_id:
        filtros.append("i.condominio_id = ?")
        parametros.append(condominio_id)

    if filtro_status == "disponivel":
        filtros.append("ct.id IS NULL")

    if filtro_status == "ocupado":
        filtros.append("ct.id IS NOT NULL")

    if busca:
        termo = f"%{busca}%"
        filtros.append("""
            (
                i.nome LIKE ?
                OR i.endereco LIKE ?
                OR i.tipo LIKE ?
                OR c.nome LIKE ?
                OR iq.nome LIKE ?
            )
        """)
        parametros.extend([termo, termo, termo, termo, termo])

    sql = """
        SELECT
            i.id,
            i.nome,
            i.tipo,
            i.endereco,
            i.status,
            i.valor_aluguel,
            i.condominio_id,
            c.nome AS condominio_nome,
            MAX(iq.nome) AS inquilino_nome,
            COUNT(DISTINCT f.id) AS total_fotos
        FROM imoveis i
        LEFT JOIN condominios c ON c.id = i.condominio_id
        LEFT JOIN contratos ct
            ON ct.imovel_id = i.id
            AND ct.status = 'ativo'
        LEFT JOIN inquilinos iq ON iq.id = ct.inquilino_id
        LEFT JOIN imovel_fotos f ON f.imovel_id = i.id
    """

    if filtros:
        sql += " WHERE " + " AND ".join(filtros)

    sql += """
        GROUP BY
            i.id,
            i.nome,
            i.tipo,
            i.endereco,
            i.status,
            i.condominio_id,
            i.valor_aluguel,
            c.nome
        ORDER BY i.nome
    """

    return rows_to_list(conn.execute(sql, parametros).fetchall())


def buscar_imovel_detalhe(conn, imovel_id):
    imovel = conn.execute("""
        SELECT
            i.id,
            i.nome,
            i.tipo,
            i.endereco,
            i.valor_aluguel,
            i.status,
            i.condominio_id,
            c.nome AS condominio_nome,
            MAX(iq.nome) AS inquilino_nome,
            COUNT(DISTINCT f.id) AS total_fotos
        FROM imoveis i
        LEFT JOIN condominios c ON c.id = i.condominio_id
        LEFT JOIN contratos ct
            ON ct.imovel_id = i.id
            AND ct.status = 'ativo'
        LEFT JOIN inquilinos iq ON iq.id = ct.inquilino_id
        LEFT JOIN imovel_fotos f ON f.imovel_id = i.id
        WHERE i.id = ?
        GROUP BY
            i.id,
            i.nome,
            i.tipo,
            i.endereco,
            i.status,
            i.condominio_id,
            c.nome
    """, (imovel_id,)).fetchone()

    if not imovel:
        return None

    return dict(imovel)


@router.get("/imoveis")
def pagina_imoveis(
    request: Request,
    busca: str = Query(default=""),
    condominio_id: int | None = Query(default=None),
    detalhe_id: int | None = Query(default=None),
    aba: str = Query(default="info"),
    status: str = Query(default="todos"),
):

    templates = request.app.state.templates

    if status not in ("todos", "disponivel", "ocupado"):
        status = "todos"

    if aba not in ("info", "fotos"):
        aba = "info"

    with get_connection() as conn:
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

        condominio_atual = None

        if condominio_id:
            condominio_atual = conn.execute("""
                SELECT id, nome, cor
                FROM condominios
                WHERE id = ?
            """, (condominio_id,)).fetchone()

            if condominio_atual:
                condominio_atual = dict(condominio_atual)

        imoveis = buscar_imoveis(
            conn=conn,
            busca=busca,
            condominio_id=condominio_id,
            filtro_status=status,
        )

        imovel_detalhe = None
        fotos_imovel = []

        if detalhe_id:
            imovel_detalhe = buscar_imovel_detalhe(conn, detalhe_id)

            if imovel_detalhe:
                fotos_imovel = rows_to_list(conn.execute("""
                    SELECT
                        id,
                        imovel_id,
                        arquivo,
                        created_at
                    FROM imovel_fotos
                    WHERE imovel_id = ?
                    ORDER BY id DESC
                """, (detalhe_id,)).fetchall())

                for foto in fotos_imovel:
                    foto["nome_arquivo"] = Path(foto["arquivo"]).name

    voltar_url = montar_url_imoveis(condominio_id=condominio_id)

    return templates.TemplateResponse(request, "imoveis.html", {
        "titulo": "Imóveis",
        "pagina": "imoveis",
        "busca": busca,
        "imoveis": imoveis,
        "condominios": condominios,
        "condominio_atual": condominio_atual,
        "imovel_detalhe": imovel_detalhe,
        "fotos_imovel": fotos_imovel,
        "aba_detalhe": aba,
        "voltar_url": voltar_url,
        "filtro_status": status,
    })


@router.post("/imoveis/criar")
def criar_imovel(
    nome: str = Form(...),
    tipo: str = Form(...),
    endereco: str = Form(...),
    valor_aluguel: float = Form(...),
    condominio_id: str = Form(default="")
):
    condominio_id_final = int(condominio_id) if condominio_id else None

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO imoveis (
                nome,
                tipo,
                endereco,
                valor_aluguel,
                status,
                condominio_id
            )
            VALUES (?, ?, ?, ?, 'disponivel', ?)
        """, (
            nome,
            tipo,
            endereco,
            valor_aluguel,
            condominio_id_final,
        ))

        conn.commit()

    return redirect_to(montar_url_imoveis(condominio_id=condominio_id_final))


@router.post("/imoveis/{imovel_id}/editar")
def editar_imovel(
    imovel_id: int,
    nome: str = Form(...),
    tipo: str = Form(...),
    endereco: str = Form(...),
    valor_aluguel: float = Form(...),
    condominio_id: str = Form(default="")
):
    condominio_id_final = int(condominio_id) if condominio_id else None

    with get_connection() as conn:
        conn.execute("""
            UPDATE imoveis
            SET
                nome = ?,
                tipo = ?,
                endereco = ?,
                valor_aluguel = ?,
                condominio_id = ?
            WHERE id = ?
        """, (
            nome,
            tipo,
            endereco,
            valor_aluguel,
            condominio_id_final,
            imovel_id,
        ))

        conn.commit()

    return redirect_to(
        montar_url_imoveis(
            condominio_id=condominio_id_final,
            detalhe_id=imovel_id,
            aba="info",
        )
    )


@router.post("/imoveis/{imovel_id}/fotos")
def adicionar_fotos_imovel(
    imovel_id: int,
    fotos: list[UploadFile] = File(default=[])
):
    pasta_imovel = FOTOS_IMOVEIS_DIR / f"imovel_{imovel_id}"
    pasta_imovel.mkdir(parents=True, exist_ok=True)

    extensoes_permitidas = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    with get_connection() as conn:
        for foto in fotos:
            if not foto.filename:
                continue

            extensao = Path(foto.filename).suffix.lower()

            if extensao not in extensoes_permitidas:
                continue

            nome_limpo = limpar_nome_arquivo(foto.filename)
            momento = datetime.now().strftime("%Y%m%d%H%M%S%f")
            nome_final = f"foto_{momento}_{nome_limpo}"

            destino = pasta_imovel / nome_final
            arquivo_relativo = f"imovel_{imovel_id}/{nome_final}"

            with destino.open("wb") as buffer:
                shutil.copyfileobj(foto.file, buffer)

            conn.execute("""
                INSERT INTO imovel_fotos (
                    imovel_id,
                    arquivo
                )
                VALUES (?, ?)
            """, (
                imovel_id,
                arquivo_relativo,
            ))

        conn.commit()

    return redirect_to(montar_url_imoveis(detalhe_id=imovel_id, aba="fotos"))


@router.get("/imoveis/fotos/{foto_id}")
def abrir_foto_imovel(foto_id: int):
    with get_connection() as conn:
        foto = conn.execute("""
            SELECT arquivo
            FROM imovel_fotos
            WHERE id = ?
        """, (foto_id,)).fetchone()

    if not foto:
        return redirect_to("/imoveis")

    caminho = FOTOS_IMOVEIS_DIR / foto["arquivo"]

    if not caminho.exists():
        return redirect_to("/imoveis")

    return FileResponse(path=caminho)


@router.post("/imoveis/fotos/{foto_id}/deletar")
def deletar_foto_imovel(foto_id: int):
    with get_connection() as conn:
        foto = conn.execute("""
            SELECT
                id,
                imovel_id,
                arquivo
            FROM imovel_fotos
            WHERE id = ?
        """, (foto_id,)).fetchone()

        if not foto:
            return redirect_to("/imoveis")

        conn.execute("""
            DELETE FROM imovel_fotos
            WHERE id = ?
        """, (foto_id,))

        conn.commit()

    caminho = FOTOS_IMOVEIS_DIR / foto["arquivo"]

    if caminho.exists():
        caminho.unlink()

    return redirect_to(
        montar_url_imoveis(
            detalhe_id=foto["imovel_id"],
            aba="fotos",
        )
    )


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
    pasta_imovel = FOTOS_IMOVEIS_DIR / f"imovel_{imovel_id}"

    with get_connection() as conn:
        conn.execute("""
            DELETE FROM imoveis
            WHERE id = ?
        """, (imovel_id,))

        conn.commit()

    if pasta_imovel.exists():
        shutil.rmtree(pasta_imovel, ignore_errors=True)

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