# ==========================================================
# ROUTES – SERVIÇOS
# ==========================================================

from flask import (
    render_template,
    request,
    redirect,
    flash,
    session
)

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required,
    pode_excluir
)

# ==========================================================
# HELPERS
# ==========================================================

def _get(row, key, default=None):
    """
    Acesso seguro a campos do banco.
    Funciona tanto para cursor dict quanto tuple.
    """
    if not row:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    return default


def parse_decimal(valor, default=0.0):
    try:
        if valor is None:
            return float(default)
        v = str(valor).replace("R$", "").replace(".", "").replace(",", ".")
        return float(v)
    except Exception:
        return float(default)


# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_servicos(app):

    # ======================================================
    # LISTAGEM
    # ======================================================
    @app.route("/servicos", methods=["GET"])
    @login_required
    @require_empresa
    def servicos_listar():

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT id,
                   nome,
                   COALESCE(valor_custo, 0) AS valor_custo
            FROM servicos
            WHERE empresa_id = %s
            ORDER BY id DESC
        """, (empresa_id,))

        servicos = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "servicos.html",
            servicos=servicos
        )

    # ======================================================
    # NOVO SERVIÇO
    # ======================================================
    @app.route("/servicos/novo", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def servicos_novo():

        empresa_id = session.get("empresa_id")

        nome = request.form.get("nome", "").strip()
        valor_custo = parse_decimal(request.form.get("valor_custo", "0"))

        if not nome:
            flash("Informe o nome do serviço.", "warning")
            return redirect("/servicos")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO servicos
                    (empresa_id, nome, valor_custo)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (empresa_id, nome, valor_custo))

            cur.fetchone()

            conn.commit()
            flash("Serviço cadastrado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar serviço: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/servicos")

    # ======================================================
    # EDITAR SERVIÇO
    # ======================================================
    @app.route("/servicos/<int:serv_id>/editar", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def servicos_editar(serv_id):

        empresa_id = session.get("empresa_id")

        nome = request.form.get("nome", "").strip()
        valor_custo = parse_decimal(request.form.get("valor_custo", "0"))

        if not nome:
            flash("Informe o nome do serviço.", "warning")
            return redirect("/servicos")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE servicos
                SET nome = %s,
                    valor_custo = %s
                WHERE id = %s
                  AND empresa_id = %s
            """, (nome, valor_custo, serv_id, empresa_id))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Serviço não encontrado nesta empresa.", "danger")
            else:
                conn.commit()
                flash("Serviço atualizado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar serviço: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/servicos")

    # ======================================================
    # EXCLUIR SERVIÇO
    # ======================================================
    @app.route("/servicos/<int:serv_id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("SUPER_ADMIN")
    def servicos_excluir(serv_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        # 🔒 BLOQUEIO POR PERMISSÃO
        if not pode_excluir(cur, session["usuario_id"]):
            flash("Você não possui permissão para excluir registros.", "warning")
            cur.close()
            conn.close()
            return redirect("/dashboard")

        try:
            # Bloqueia exclusão se houver vínculo com custos/locações
            cur.execute("""
                SELECT 1
                FROM custos_impressora ci
                JOIN clientes c ON c.id = ci.cliente_id
                WHERE ci.servico_id = %s
                  AND c.empresa_id = %s
                LIMIT 1
            """, (serv_id, empresa_id))

            if cur.fetchone():
                flash(
                    "Exclusão bloqueada: serviço possui vínculos com locações.",
                    "warning"
                )
                return redirect("/servicos")

            cur.execute("""
                DELETE FROM servicos
                WHERE id = %s
                  AND empresa_id = %s
            """, (serv_id, empresa_id))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Serviço não encontrado.", "danger")
            else:
                conn.commit()
                flash("Serviço excluído com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir serviço: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/servicos")
