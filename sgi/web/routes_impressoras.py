# ==========================================================
# ROUTES – IMPRESSORAS
# ==========================================================
from sgi.core.permissions import tem_permissao
import os
import uuid

from flask import (
    render_template,
    request,
    redirect,
    flash,
    session,
    send_from_directory,
    abort
)

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required,
    require_perm,
    pode_ver_financeiro
)

# ==========================================================
# HELPERS
# ==========================================================

def _get(row, key, default=None):
    """
    Acesso seguro a campos do banco.
    Compatível com cursor dict ou tuple.
    """
    if not row:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    return default


# ==========================================================
# CONFIGURAÇÃO DE UPLOAD
# ==========================================================

UPLOAD_DIR = os.path.abspath(os.path.join(os.getcwd(), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _file_ext(filename):
    return filename.rsplit(".", 1)[1].lower()


# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_impressoras(app):

    # ======================================================
    # LISTAGEM
    # ======================================================
    @app.route("/impressoras", methods=["GET"])
    @login_required
    @require_empresa
    def impressoras_listar():

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        pode_ver = pode_ver_financeiro(cur, session.get("usuario_id"))

        cur.execute("""
            SELECT
                i.id,
                i.nome_equipamento,
                i.modelo,
                i.marca,
                i.num_serie,
                i.patrimonio,
                i.locada,
                CASE WHEN %s THEN COALESCE(i.valor_compra,0) ELSE 0 END AS valor_compra,
                CASE WHEN %s THEN COALESCE(i.valor_aluguel,0) ELSE 0 END AS valor_aluguel,
                COALESCE(c.nome,'') AS cliente_nome
            FROM impressoras i
            LEFT JOIN clientes c ON c.id = i.cliente_id
            WHERE i.empresa_id = %s
            ORDER BY i.id DESC
        """, (pode_ver, pode_ver, empresa_id))

        impressoras = cur.fetchall()

                # =========================
        # RESUMO DE IMPRESSORAS
        # =========================
        total_impressoras = len(impressoras)
        total_locadas = sum(1 for i in impressoras if _get(i, "locada"))
        total_disponiveis = total_impressoras - total_locadas

        
        # 🔹 TOTAL DE ALUGUEL DAS IMPRESSORAS LOCADAS
        total_aluguel_locadas = sum(
            float(_get(i, "valor_aluguel", 0))
            for i in impressoras
            if _get(i, "locada")
        )

        cur.execute("""
            SELECT id, nome
            FROM clientes
            WHERE empresa_id = %s
            ORDER BY nome
        """, (empresa_id,))
        clientes = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
    "impressoras.html",
    impressoras=impressoras,
    clientes=clientes,
    total_aluguel_locadas=total_aluguel_locadas,

    # aliases para o HTML existente
    total=total_impressoras,
    locadas=total_locadas,
    disponiveis=total_disponiveis
)



    # ======================================================
    # NOVA IMPRESSORA
    # ======================================================
        
    @app.route("/impressoras/novo", methods=["POST"])
    @login_required
    @require_empresa
    def impressoras_novo():

        empresa_id = session.get("empresa_id")

        nome_equipamento = request.form.get("nome_equipamento")
        modelo = request.form.get("modelo")
        marca = request.form.get("marca")
        num_serie = request.form.get("num_serie")
        patrimonio = request.form.get("patrimonio")
        valor_compra = request.form.get("valor_compra") or 0
        valor_aluguel = request.form.get("valor_aluguel") or 0

        # 🔹 NOVOS CAMPOS
        locada = request.form.get("locada") == "SIM"
        cliente_id = request.form.get("cliente_id")
        local_na_empresa = request.form.get("local_na_empresa") or ""

        # 🔒 VALIDAÇÃO PROFISSIONAL
        if locada and not cliente_id:
            flash("Selecione um cliente para marcar como locada.", "warning")
            return redirect("/impressoras")

        if not nome_equipamento or not modelo or not marca:
            flash("Preencha todos os campos obrigatórios.", "warning")
            return redirect("/impressoras")

        conn = conectar()
        cur = conn.cursor()

                # 🔐 Bloqueia lançamento de valores financeiros
        if not tem_permissao(cur, session.get("usuario_id"), "EDITAR_FINANCEIRO"):
            valor_compra = 0
            valor_aluguel = 0

        try:
            cur.execute("""
                INSERT INTO impressoras (
                    empresa_id,
                    nome_equipamento,
                    modelo,
                    marca,
                    num_serie,
                    patrimonio,
                    valor_compra,
                    valor_aluguel,
                    locada,
                    cliente_id,
                    local_na_empresa
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                empresa_id,
                nome_equipamento,
                modelo,
                marca,
                num_serie,
                patrimonio,
                valor_compra,
                valor_aluguel,
                locada,
                cliente_id if locada else None,
                local_na_empresa if locada else ""
            ))

            conn.commit()
            flash("Impressora cadastrada com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar impressora: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/impressoras")


    # ======================================================
    # EDITAR IMPRESSORA
    # ======================================================
    @app.route("/impressoras/<int:imp_id>/editar", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR" , "SUPER_ADMIN")
    def impressoras_editar(imp_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

                # 🔐 Bloqueia edição financeira
        if not tem_permissao(cur, session.get("usuario_id"), "EDITAR_FINANCEIRO"):
            cur.close()
            conn.close()
            flash("Você não possui permissão para editar valores financeiros.", "warning")
            return redirect("/impressoras")

        try:
            cur.execute("""
                UPDATE impressoras
                SET
                    nome_equipamento=%s,
                    modelo=%s,
                    marca=%s,
                    num_serie=%s,
                    patrimonio=%s,
                    valor_compra=%s,
                    valor_aluguel=%s,
                    locada=%s,
                    cliente_id=%s,
                    local_na_empresa=%s
                WHERE id=%s AND empresa_id=%s
            """, (
                request.form.get("nome_equipamento"),
                request.form.get("modelo"),
                request.form.get("marca"),
                request.form.get("num_serie"),
                request.form.get("patrimonio"),
                request.form.get("valor_compra") or 0,
                request.form.get("valor_aluguel") or 0,
                request.form.get("locada") == "SIM",
                request.form.get("cliente_id") if request.form.get("locada") == "SIM" else None,
                request.form.get("local_na_empresa") if request.form.get("locada") == "SIM" else "",
                imp_id,
                empresa_id
            ))


            if cur.rowcount == 0:
                conn.rollback()
                flash("Impressora não encontrada.", "danger")
            else:
                conn.commit()
                flash("Impressora atualizada com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/impressoras")

    # ======================================================
    # EXCLUIR IMPRESSORA
    # ======================================================
    @app.route("/impressoras/<int:imp_id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @require_perm("EXCLUIR_REGISTROS")
    def impressoras_excluir(imp_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT locada
                FROM impressoras
                WHERE id=%s AND empresa_id=%s
            """, (imp_id, empresa_id))

            imp = cur.fetchone()
            if not imp:
                flash("Impressora não encontrada.", "danger")
                return redirect("/impressoras")

            if _get(imp, "locada", False):
                flash("Exclusão bloqueada: impressora está locada.", "warning")
                return redirect("/impressoras")

            cur.execute("""
                DELETE FROM impressoras
                WHERE id=%s AND empresa_id=%s
            """, (imp_id, empresa_id))

            conn.commit()
            flash("Impressora excluída com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/impressoras")

    # ======================================================
    # ARQUIVOS DA IMPRESSORA
    # ======================================================
    @app.route("/impressoras/<int:imp_id>/arquivos", methods=["GET"])
    @login_required
    @require_empresa
    def impressora_arquivos(imp_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, nome_equipamento
            FROM impressoras
            WHERE id=%s AND empresa_id=%s
        """, (imp_id, empresa_id))
        impressora = cur.fetchone()

        if not impressora:
            abort(404)

        cur.execute("""
            SELECT id, nome_original, nome_armazenado, criado_em
            FROM impressora_arquivos
            WHERE impressora_id=%s
            ORDER BY criado_em DESC
        """, (imp_id,))
        arquivos = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "impressora_arquivos.html",
            impressora=impressora,
            arquivos=arquivos
        )

    @app.route("/impressoras/<int:imp_id>/arquivos/upload", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def impressora_arquivos_upload(imp_id):

        arquivo = request.files.get("arquivo")

        if not arquivo or not _allowed_file(arquivo.filename):
            flash("Arquivo inválido.", "warning")
            return redirect(f"/impressoras/{imp_id}/arquivos")

        ext = _file_ext(arquivo.filename)
        nome_stored = f"{uuid.uuid4().hex}.{ext}"
        caminho = os.path.join(UPLOAD_DIR, nome_stored)

        arquivo.save(caminho)

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO impressora_arquivos
                    (impressora_id, nome_original, nome_armazenado)
                VALUES (%s,%s,%s)
            """, (imp_id, arquivo.filename, nome_stored))

            conn.commit()
            flash("Arquivo enviado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            os.remove(caminho)
            flash(f"Erro ao enviar arquivo: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect(f"/impressoras/{imp_id}/arquivos")

    @app.route("/impressoras/<int:imp_id>/arquivos/<int:arq_id>/download")
    @login_required
    @require_empresa
    def impressora_arquivo_download(imp_id, arq_id):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT nome_original, nome_armazenado
            FROM impressora_arquivos
            WHERE id=%s AND impressora_id=%s
        """, (arq_id, imp_id))

        arq = cur.fetchone()

        cur.close()
        conn.close()

        if not arq:
            abort(404)

        return send_from_directory(
            UPLOAD_DIR,
            _get(arq, "nome_armazenado"),
            as_attachment=True,
            download_name=_get(arq, "nome_original")
        )
