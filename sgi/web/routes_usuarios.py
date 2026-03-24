from flask import (
    render_template, request, redirect,
    session, flash
)

from sgi.core.permissions import (
    login_required,
    require_perm,
    require_empresa,
    perfil_required,
    _usuario_id,
    _empresa_id
)

from sgi.core.db import conectar
from sgi.core.permissions import PERMISSOES_PROTEGIDAS

# ==========================================================
# ROTAS DE GESTÃO DE USUÁRIOS
# ==========================================================

def configurar_rotas_usuarios(app):

    # ======================================================
    # LISTAGEM DE USUÁRIOS
    # ADMIN com ou sem visão multiempresa
    # ======================================================
    @app.route("/usuarios", methods=["GET"])
    @login_required
    @require_empresa
    @require_perm("ADMIN_USUARIOS")
    def usuarios_lista():

        conn = conectar()
        cur = conn.cursor()

        empresa_id = _empresa_id()
        pode_multiempresa = bool(session.get("pode_multiempresa", False))

        if pode_multiempresa:
            # Admin com visão global
            cur.execute("""
                SELECT
                    u.id,
                    u.usuario,
                    u.perfil,
                    u.ativo,
                    u.pode_multiempresa,
                    e.nome AS empresa_nome
                FROM usuarios u
                JOIN empresas e ON e.id = u.empresa_id
                ORDER BY e.nome, u.usuario
            """)
        else:
            # Admin restrito à própria empresa
            cur.execute("""
                SELECT
                    u.id,
                    u.usuario,
                    u.perfil,
                    u.ativo,
                    u.pode_multiempresa,
                    e.nome AS empresa_nome
                FROM usuarios u
                JOIN empresas e ON e.id = u.empresa_id
                WHERE u.empresa_id = %s
                ORDER BY u.usuario
            """, (empresa_id,))

        usuarios = cur.fetchall()
        cur.close()
        conn.close()

        return render_template(
            "usuarios.html",
            usuarios=usuarios
        )
    # ======================================================
    # NOVO USUÁRIO
    # ======================================================
    @app.route("/usuarios/novo", methods=["GET", "POST"])
    @login_required
    @require_empresa
    @require_perm("ADMIN_USUARIOS")
    def usuarios_novo():

        conn = conectar()
        cur = conn.cursor()

        if request.method == "POST":

            usuario = request.form.get("usuario")
            senha = request.form.get("senha")
            perfil = request.form.get("perfil")
            empresa_id = request.form.get("empresa_id")
            pode_multiempresa = True if request.form.get("pode_multiempresa") else False

            if not usuario or not senha or not perfil or not empresa_id:
                flash("Preencha todos os campos obrigatórios.", "warning")
                return redirect("/usuarios/novo")

            try:
                cur.execute("""
                    INSERT INTO usuarios
                        (usuario, senha_hash, perfil, ativo, empresa_id, criado_em, pode_multiempresa, forcar_troca_senha)
                    VALUES
                        (%s, crypt(%s, gen_salt('bf',12)), %s, TRUE, %s, NOW(), %s, TRUE)
                """, (
                    usuario,
                    senha,
                    perfil,
                    empresa_id,
                    pode_multiempresa
                ))

                conn.commit()
                flash("Usuário criado com sucesso.", "success")
                return redirect("/usuarios")

            except Exception as e:
                conn.rollback()
                flash(f"Erro ao criar usuário: {str(e)}", "danger")

        cur.execute("""
            SELECT id, nome
            FROM empresas
            WHERE ativo = TRUE
            ORDER BY nome
        """)
        empresas = cur.fetchall()

        cur.close()
        conn.close()

        return render_template("usuarios_novo.html", empresas=empresas)
    
    # ======================================================
# EDITAR USUÁRIO
# ======================================================
    @app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
    @login_required
    @require_empresa
    @require_perm("ADMIN_USUARIOS")
    def usuarios_editar(usuario_id):

        conn = conectar()
        cur = conn.cursor()

        # Busca usuário
        cur.execute("""
            SELECT id, usuario, perfil, empresa_id, pode_multiempresa
            FROM usuarios
            WHERE id = %s
        """, (usuario_id,))
        usuario = cur.fetchone()

        if not usuario:
            flash("Usuário não encontrado.", "danger")
            return redirect("/usuarios")

        if request.method == "POST":

            novo_usuario = request.form.get("usuario")
            novo_perfil = request.form.get("perfil")
            nova_empresa = request.form.get("empresa_id")
            pode_multiempresa = True if request.form.get("pode_multiempresa") else False

            try:
                cur.execute("""
                    UPDATE usuarios
                    SET usuario=%s,
                        perfil=%s,
                        empresa_id=%s,
                        pode_multiempresa=%s
                    WHERE id=%s
                """, (
                    novo_usuario,
                    novo_perfil,
                    nova_empresa,
                    pode_multiempresa,
                    usuario_id
                ))

                conn.commit()
                flash("Usuário atualizado com sucesso.", "success")
                return redirect("/usuarios")

            except Exception as e:
                conn.rollback()
                flash(f"Erro ao atualizar: {str(e)}", "danger")

        # Lista empresas
        cur.execute("""
            SELECT id, nome
            FROM empresas
            WHERE ativo = TRUE
            ORDER BY nome
        """)
        empresas = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "usuarios_editar.html",
            usuario=usuario,
            empresas=empresas
        )
    
    # ======================================================
    # EXCLUIR USUÁRIO
    # ======================================================
    @app.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
    @login_required
    @require_perm("ADMIN_USUARIOS")
    def usuarios_excluir(usuario_id):

        usuario_logado = _usuario_id()

        if usuario_id == usuario_logado:
            flash("Você não pode excluir o próprio usuário.", "warning")
            return redirect("/usuarios")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                DELETE FROM usuarios
                WHERE id = %s
            """, (usuario_id,))

            if cur.rowcount == 0:
                flash("Usuário não encontrado.", "danger")
            else:
                flash("Usuário excluído com sucesso.", "success")

            conn.commit()

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir: {str(e)}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/usuarios")

        # ======================================================
    # GERENCIAR PERMISSÕES DO USUÁRIO
    # ======================================================
    @app.route("/usuarios/<int:usuario_id>/permissoes", methods=["GET", "POST"])
    @login_required
    @require_empresa
    @require_perm("ADMIN_USUARIOS")
    def usuarios_permissoes(usuario_id):

        conn = conectar()
        cur = conn.cursor()

        # Verifica se usuário existe
        cur.execute("""
            SELECT id, usuario
            FROM usuarios
            WHERE id = %s
        """, (usuario_id,))
        usuario = cur.fetchone()

        if not usuario:
            flash("Usuário não encontrado.", "danger")
            return redirect("/usuarios")

        if request.method == "POST":

            # Remove todas permissões atuais
            cur.execute("""
                DELETE FROM usuarios_permissoes
                WHERE usuario_id = %s
            """, (usuario_id,))

            # Adiciona permissões marcadas
            permissoes_selecionadas = request.form.getlist("permissoes")

            for perm_id in permissoes_selecionadas:
                cur.execute("""
                    INSERT INTO usuarios_permissoes (usuario_id, permissao_id)
                    VALUES (%s, %s)
                """, (usuario_id, perm_id))

            conn.commit()
            flash("Permissões atualizadas com sucesso.", "success")
            return redirect("/usuarios")

        # Lista todas permissões do sistema
        cur.execute("""
            SELECT id, codigo, descricao
            FROM permissoes
            ORDER BY codigo
        """)
        todas_permissoes = cur.fetchall()

        # Permissões já atribuídas
        cur.execute("""
            SELECT permissao_id
            FROM usuarios_permissoes
            WHERE usuario_id = %s
        """, (usuario_id,))
        permissoes_usuario = {row["permissao_id"] for row in cur.fetchall()}

        cur.close()
        conn.close()

        return render_template(
            "usuarios_permissoes.html",
            usuario=usuario,
            permissoes=todas_permissoes,
            permissoes_usuario=permissoes_usuario
        )

    # ======================================================
    # ATIVAR / DESATIVAR USUÁRIO
    # ======================================================
    @app.route("/usuarios/<int:usuario_id>/status", methods=["POST"])
    @login_required
    @require_perm("ADMIN_USUARIOS")
    def usuarios_toggle_status(usuario_id):

        usuario_logado = _usuario_id()

        # Segurança: não permitir auto-desativação
        if usuario_id == usuario_logado:
            flash("Você não pode alterar o status do próprio usuário.", "warning")
            return redirect("/usuarios")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE usuarios
            SET ativo = NOT ativo
            WHERE id = %s
            RETURNING usuario, ativo
        """, (usuario_id,))

        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close()
            conn.close()
            flash("Usuário não encontrado.", "danger")
            return redirect("/usuarios")

        usuario_nome = row["usuario"]
        novo_status = "ATIVADO" if row["ativo"] else "DESATIVADO"

        # Log de auditoria
        cur.execute("""
            INSERT INTO logs_sistema (usuario, acao, entidade, entidade_id, detalhes)
            VALUES (%s,'STATUS_USUARIO','usuarios',%s,%s)
        """, (
            session.get("usuario"),
            usuario_id,
            f"Usuário {usuario_nome} foi {novo_status}"
        ))

        conn.commit()
        cur.close()
        conn.close()

        flash(f"Usuário {usuario_nome} {novo_status.lower()} com sucesso.", "success")
        return redirect("/usuarios")

    # ======================================================
    # RESET DE SENHA (ADMIN)
    # ======================================================
    @app.route("/usuarios/<int:usuario_id>/reset-senha", methods=["POST"])
    @login_required
    @require_perm("ADMIN_USUARIOS")
    def usuarios_reset_senha(usuario_id):

        usuario_logado = _usuario_id()

        # Segurança: impedir reset da própria senha
        if usuario_id == usuario_logado:
            flash("Você não pode redefinir a própria senha por aqui.", "warning")
            return redirect("/usuarios")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE usuarios
            SET senha_hash = crypt('trocar123', gen_salt('bf', 12)),
                forcar_troca_senha = TRUE
            WHERE id = %s
            RETURNING usuario
        """, (usuario_id,))

        row = cur.fetchone()
        if not row:
            conn.rollback()
            cur.close()
            conn.close()
            flash("Usuário não encontrado.", "danger")
            return redirect("/usuarios")

        usuario_nome = row["usuario"]

        # Log de auditoria
        cur.execute("""
            INSERT INTO logs_sistema (usuario, acao, entidade, entidade_id, detalhes)
            VALUES (%s,'RESET_SENHA','usuarios',%s,%s)
        """, (
            session.get("usuario"),
            usuario_id,
            f"Senha redefinida para o usuário {usuario_nome}"
        ))

        conn.commit()
        cur.close()
        conn.close()

        flash(f"Senha do usuário {usuario_nome} redefinida para: trocar123", "warning")
        return redirect("/usuarios")

    # ======================================================
    # EXCLUIR PERMISSÃO
    # ======================================================

    @app.route("/permissoes/excluir/<int:id>")
    @login_required
    @perfil_required("SUPER_ADMIN")
    def excluir_permissao(id):

        conn = conectar()
        cur = conn.cursor()

        cur.execute("SELECT codigo FROM permissoes WHERE id = %s", (id,))
        p = cur.fetchone()

        if not p:
            flash("Permissão não encontrada.", "danger")
            return redirect(request.referrer or "/usuarios")

        codigo = p["codigo"] if isinstance(p, dict) else p[0]

        if codigo in PERMISSOES_PROTEGIDAS:
            flash("Esta permissão é protegida e não pode ser excluída.", "danger")
            return redirect(request.referrer or "/usuarios")

        cur.execute(
            "DELETE FROM usuarios_permissoes WHERE permissao_id = %s",
            (id,)
        )

        cur.execute(
            "DELETE FROM permissoes WHERE id = %s",
            (id,)
        )

        conn.commit()

        cur.close()
        conn.close()

        flash("Permissão excluída com sucesso.", "success")
        return redirect(request.referrer or "/usuarios")