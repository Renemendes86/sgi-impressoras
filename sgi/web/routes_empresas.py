# ==========================================================
# ROUTES - EMPRESAS (ADMIN / MULTIEMPRESA)
# ==========================================================

from flask import (
    render_template, request, redirect, flash, session
)

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    perfil_required,
    require_perm,
    tem_permissao,   # 👈 ADICIONAR
    _sync_empresa_nome,
)

# ==========================================================
# CONFIGURAÇÃO DAS ROTAS DE EMPRESAS
# ==========================================================

def configurar_rotas_empresas(app):

    # ------------------------------------------------------
    # SELECIONAR EMPRESA (GET → painel / POST → grava sessão)
    # ------------------------------------------------------
    @app.route("/selecionar-empresa", methods=["GET", "POST"])
    @login_required
    def selecionar_empresa():

        # GET → apenas redireciona para o painel
        if request.method == "GET":
            return redirect("/multiempresa")

        # POST → seleciona empresa
        empresa_id = request.form.get("empresa_id")

        if not empresa_id or not empresa_id.isdigit():
            flash("Empresa inválida.", "warning")
            return redirect("/multiempresa")

        empresa_id = int(empresa_id)

        conn = conectar()
        cur = conn.cursor()

        usuario_id = session.get("usuario_id")

        if not tem_permissao(cur, usuario_id, "ACESSAR_TODAS_EMPRESAS"):
            cur.close()
            conn.close()
            flash("Você não tem permissão para alterar empresa.", "danger")
            return redirect("/dashboard")

        cur.execute("""
            SELECT id, nome
            FROM empresas
            WHERE id=%s AND ativo=TRUE
        """, (empresa_id,))

        empresa = cur.fetchone()

        cur.close()
        conn.close()

        if not empresa:
            flash("Empresa não encontrada ou inativa.", "danger")
            return redirect("/multiempresa")

        # grava na sessão
        session["empresa_id"] = empresa_id
        session.pop("empresa_nome", None)  # força sincronização correta

        empresa_nome = empresa["nome"] if isinstance(empresa, dict) else empresa[1]
        flash(f"Empresa '{empresa_nome}' selecionada com sucesso.", "success")
        return redirect("/dashboard")

    # ------------------------------------------------------
    # LISTAR EMPRESAS
    # ------------------------------------------------------
    @app.route("/empresas", methods=["GET"])
    @login_required
    @perfil_required("SUPER_ADMIN")
    @require_perm("ADMIN_EMPRESAS")
    def empresas_listar():

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                id,
                nome,
                cnpj,
                endereco,
                telefone,
                email,
                ativo
            FROM empresas
            ORDER BY nome
        """)
        empresas = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "empresas.html",
            empresas=empresas,
            empresa=None
        )

    # ------------------------------------------------------
    # CADASTRAR NOVA EMPRESA (GET + POST)
    # ------------------------------------------------------
    @app.route("/empresas/novo", methods=["GET", "POST"])
    @login_required
    @perfil_required("SUPER_ADMIN")
    @require_perm("ADMIN_EMPRESAS")
    def empresas_novo():

        if request.method == "GET":
            return render_template(
                "empresas.html",
                empresa=None
            )

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        endereco = request.form.get("endereco", "").strip()
        telefone = request.form.get("telefone", "").strip()
        email = request.form.get("email", "").strip()

        if not nome:
            flash("Nome da empresa é obrigatório.", "warning")
            return redirect("/empresas/novo")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO empresas
                    (nome, cnpj, endereco, telefone, email, ativo)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (nome, cnpj, endereco, telefone, email))

            conn.commit()
            flash("Empresa cadastrada com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar empresa: {e}", "danger")
            return redirect("/empresas/novo")

        finally:
            cur.close()
            conn.close()

        return redirect("/empresas")

    # ------------------------------------------------------
    # EDITAR EMPRESA
    # ------------------------------------------------------
    @app.route("/empresas/<int:empresa_id>/editar", methods=["POST"])
    @login_required
    @perfil_required("SUPER_ADMIN")
    @require_perm("ADMIN_EMPRESAS")
    def empresas_editar(empresa_id):

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        endereco = request.form.get("endereco", "").strip()
        telefone = request.form.get("telefone", "").strip()
        email = request.form.get("email", "").strip()
        ativo = request.form.get("ativo", "1") == "1"

        if not nome:
            flash("Nome da empresa é obrigatório.", "warning")
            return redirect("/empresas")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE empresas
                SET
                    nome=%s,
                    cnpj=%s,
                    endereco=%s,
                    telefone=%s,
                    email=%s,
                    ativo=%s
                WHERE id=%s
            """, (nome, cnpj, endereco, telefone, email, ativo, empresa_id))

            # mantém sessão consistente
            if session.get("empresa_id") == empresa_id:
                _sync_empresa_nome(cur, empresa_id)

            conn.commit()
            flash("Empresa atualizada com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar empresa: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/empresas")

    # ------------------------------------------------------
    # EXCLUIR EMPRESA (COM BLOQUEIO DE VÍNCULOS)
    # ------------------------------------------------------
    @app.route("/empresas/<int:empresa_id>/excluir", methods=["POST"])
    @login_required
    @perfil_required("SUPER_ADMIN")
    @require_perm("ADMIN_EMPRESAS")
    def empresas_excluir(empresa_id):

        conn = conectar()
        cur = conn.cursor()

        try:
            checks = [
                ("usuarios", "usuários"),
                ("clientes", "clientes"),
                ("impressoras", "impressoras"),
                ("produtos", "produtos"),
                ("servicos", "serviços"),
                ("fechamentos_cliente", "financeiro"),
            ]

            motivos = []

            for tabela, nome_legivel in checks:
                cur.execute(
                    f"SELECT COUNT(*) AS n FROM {tabela} WHERE empresa_id=%s",
                    (empresa_id,)
                )
                if cur.fetchone().get("n", 0) > 0:
                    motivos.append(nome_legivel)

            if motivos:
                flash(
                    "Exclusão não permitida: existem vínculos com "
                    + ", ".join(motivos) + ".",
                    "warning"
                )
                return redirect("/empresas")

            cur.execute("DELETE FROM empresas WHERE id=%s", (empresa_id,))
            conn.commit()
            flash("Empresa excluída com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir empresa: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/empresas")
