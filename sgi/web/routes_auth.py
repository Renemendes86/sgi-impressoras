# ==========================================================
# ROUTES - AUTENTICAÇÃO (LOGIN / LOGOUT)
# ==========================================================

from flask import render_template, request, redirect, session, flash
from sgi.core.auth import autenticar
from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,   # ✅ ADICIONE ISSO
    _usuario_id,
    _get_empresas_disponiveis,
    _empresa_existe_ativa,
    _sync_empresa_nome
)

def configurar_rotas_auth(app):

    # ======================================================
    # LOGIN
    # ======================================================
    @app.route("/", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            usuario = (request.form.get("usuario") or "").strip()
            senha = (request.form.get("senha") or "").strip()

            if not usuario or not senha:
                flash("Informe usuário e senha.", "warning")
                return render_template("login.html")

            user = autenticar(usuario, senha)

            if not user:
                flash("Usuário ou senha inválidos.", "danger")
                return render_template("login.html")

            if not user.get("ativo", True):
                flash("Usuário desativado. Contate o administrador.", "danger")
                return render_template("login.html")
            

            # ----------------------------------------------
            # Monta sessão
            # ----------------------------------------------
            session.clear()
            session["usuario"] = user["usuario"]
            session["usuario_id"] = user["id"]
            session["perfil"] = user["perfil"]
            session["pode_multiempresa"] = bool(user.get("pode_multiempresa", False))

            # ======================================================
            # CARREGA PERMISSÕES DO USUÁRIO
            # ======================================================

            conn = conectar()
            cur = conn.cursor()

            cur.execute("""
                SELECT p.codigo
                FROM usuarios_permissoes up
                JOIN permissoes p ON p.id = up.permissao_id
                WHERE up.usuario_id = %s
            """, (user["id"],))

            permissoes = [row["codigo"] for row in cur.fetchall()]

            session["permissoes"] = permissoes

            cur.close()
            conn.close()

            # empresa será definida depois
            session.pop("empresa_id", None)
            session.pop("empresa_nome", None)

            # 🔐 AGORA verifica troca obrigatória
            if user.get("forcar_troca_senha"):
                return redirect("/trocar-senha")

            # ----------------------------------------------
            # Seleção automática se houver apenas 1 empresa
            # ----------------------------------------------

            conn = conectar()
            cur = conn.cursor()

            empresas = _get_empresas_disponiveis(cur, user["id"])

            # Se só houver 1 empresa, seleciona automaticamente
            if len(empresas) == 1:
                empresa_id = empresas[0]["id"]
                session["empresa_id"] = empresa_id
                _sync_empresa_nome(cur, empresa_id)
                cur.close()
                conn.close()
                return redirect("/dashboard")

            cur.close()
            conn.close()

            return redirect("/selecionar-empresa")

        # GET → Exibir tela login
        return render_template("login.html")

    # ======================================================
    # LOGOUT
    # ======================================================
    @app.route("/logout")
    def logout():
        session.clear()
        return redirect("/")
    
    @app.route("/trocar-senha", methods=["GET", "POST"])
    @login_required
    def trocar_senha():

        if request.method == "POST":

            nova_senha = request.form.get("nova_senha")
            confirmar = request.form.get("confirmar")

            if not nova_senha or nova_senha != confirmar:
                flash("As senhas não coincidem.", "danger")
                return render_template("trocar_senha.html")

            conn = conectar()
            cur = conn.cursor()

            cur.execute("""
                UPDATE usuarios
                SET senha_hash = crypt(%s, gen_salt('bf',12)),
                    forcar_troca_senha = FALSE
                WHERE id = %s
            """, (
                nova_senha,
                session.get("usuario_id")
            ))

            conn.commit()

            # ===== Decide para onde ir depois =====
            empresas = _get_empresas_disponiveis(cur, session.get("usuario_id"))

            if len(empresas) == 1:
                empresa_id = empresas[0]["id"]
                session["empresa_id"] = empresa_id
                _sync_empresa_nome(cur, empresa_id)
                destino = "/dashboard"
            else:
                destino = "/selecionar-empresa"

            cur.close()
            conn.close()

            flash("Senha alterada com sucesso.", "success")
            return redirect(destino)

        # 🔥 AGORA TEM RETORNO PARA GET
        return render_template("trocar_senha.html")
