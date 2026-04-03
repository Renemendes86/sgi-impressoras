# ==========================================================
# ROUTES – MUNICÍPIOS
# ==========================================================

from flask import render_template, request, redirect, flash
from sgi.core.db import conectar
from sgi.core.permissions import login_required


def configurar_rotas_municipios(app):

    # ======================================================
    # LISTAR MUNICÍPIOS
    # ======================================================
    @app.route("/municipios")
    @login_required
    def municipios():

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, nome
            FROM municipios
            ORDER BY nome
        """)

        municipios = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "municipios.html",
            municipios=municipios
        )


    # ======================================================
    # NOVO MUNICÍPIO
    # ======================================================
    @app.route("/municipios/novo", methods=["POST"])
    @login_required
    def municipios_novo():

        nome = request.form.get("nome")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO municipios (nome)
            VALUES (%s)
        """, (nome,))

        conn.commit()

        cur.close()
        conn.close()

        flash("Município cadastrado com sucesso.", "success")

        return redirect("/municipios")


    # ======================================================
    # EDITAR MUNICÍPIO
    # ======================================================
    @app.route("/municipios/<int:id>/editar", methods=["POST"])
    @login_required
    def municipios_editar(id):

        nome = request.form.get("nome")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE municipios
            SET nome = %s
            WHERE id = %s
        """, (nome, id))

        conn.commit()

        cur.close()
        conn.close()

        flash("Município atualizado com sucesso.", "success")

        return redirect("/municipios")


    # ======================================================
    # EXCLUIR MUNICÍPIO
    # ======================================================
    @app.route("/municipios/<int:id>/excluir", methods=["POST"])
    @login_required
    def municipios_excluir(id):

        conn = conectar()
        cur = conn.cursor()

        # verificar se existem secretarias vinculadas
        cur.execute("""
            SELECT 1
            FROM clientes
            WHERE municipio_id = %s
            LIMIT 1
        """, (id,))

        if cur.fetchone():

            cur.close()
            conn.close()

            flash(
                "Não é possível excluir este município pois existem secretarias vinculadas.",
                "warning"
            )

            return redirect("/municipios")

        cur.execute("""
            DELETE FROM municipios
            WHERE id = %s
        """, (id,))

        conn.commit()

        cur.close()
        conn.close()

        flash("Município excluído com sucesso.", "success")

        return redirect("/municipios")