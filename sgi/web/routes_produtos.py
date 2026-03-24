# ==========================================================
# ROUTES – PRODUTOS / ESTOQUE (VERSÃO FINAL CORRETA)
# ==========================================================

from datetime import date
from flask import (
    render_template,
    request,
    redirect,
    flash,
    session,
    Response
)

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required
)

# ==========================================================
# HELPERS
# ==========================================================

def _get(row, key, default=None):
    if not row:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def parse_decimal(valor, default=0.0):
    try:
        if valor is None:
            return float(default)
        v = str(valor).replace("R$", "").replace(".", "").replace(",", ".")
        return float(v)
    except Exception:
        return float(default)


def usuario_pode_ver_custos(cur, usuario_id):
    if session.get("perfil") == "SUPER_ADMIN":
        return True

    cur.execute("""
        SELECT 1
        FROM usuarios_permissoes up
        JOIN permissoes p ON p.id = up.permissao_id
        WHERE up.usuario_id=%s
          AND p.codigo='VER_VALOR_CUSTO'
    """, (usuario_id,))
    return bool(cur.fetchone())


# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_produtos(app):

    # ======================================================
    # LISTAGEM
    # ======================================================
    @app.route("/produtos")
    @login_required
    @require_empresa
    def produtos_listar():

        empresa_id = session.get("empresa_id")
        usuario_id = session.get("usuario_id")

        conn = conectar()
        cur = conn.cursor()

        pode_ver = usuario_pode_ver_custos(cur, usuario_id)
        campo_custo = "valor_custo" if pode_ver else "0"

        cur.execute("""
    SELECT 
        id,
        nome,
        marca,
        modelo,
        COALESCE(unidade, 'UN') AS unidade,
        COALESCE(estoque_atual, 0) AS estoque_atual,
        COALESCE(valor_custo, 0) AS valor_custo
    FROM produtos
    WHERE empresa_id = %s
    ORDER BY id DESC
""", (empresa_id,))

        produtos = cur.fetchall()
        cur.close()
        conn.close()

        return render_template(
            "produtos.html",
            produtos=produtos,
            pode_ver=pode_ver
        )

    # ======================================================
    # NOVO PRODUTO
    # ======================================================
    @app.route("/produtos/novo", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def produtos_novo():

        empresa_id = session.get("empresa_id")
        usuario = session.get("usuario") or session.get("usuario_id")

        nome = request.form.get("nome", "").strip()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        unidade = request.form.get("unidade", "UN").upper()
        valor_custo = parse_decimal(request.form.get("valor_custo"))
        estoque_inicial = parse_decimal(request.form.get("estoque_inicial"))

        if not nome:
            flash("Informe o nome do produto.", "warning")
            return redirect("/produtos")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO produtos
                (empresa_id, nome, marca, modelo, valor_custo, unidade, estoque_atual)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                empresa_id, nome, marca, modelo,
                valor_custo, unidade, estoque_inicial
            ))

            prod_id = cur.fetchone()[0]

            if estoque_inicial > 0:
                cur.execute("""
                    INSERT INTO estoque_movimentos
                    (produto_id, tipo, quantidade, observacao, usuario)
                    VALUES (%s,'ENTRADA',%s,'Estoque inicial',%s)
                """, (prod_id, estoque_inicial, usuario))

            conn.commit()
            flash("Produto cadastrado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(str(e), "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")

    # ======================================================
    # EDITAR PRODUTO
    # ======================================================
    @app.route("/produtos/<int:prod_id>/editar", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def produtos_editar(prod_id):

        empresa_id = session.get("empresa_id")

        nome = request.form.get("nome", "").strip()
        marca = request.form.get("marca", "").strip()
        modelo = request.form.get("modelo", "").strip()
        unidade = request.form.get("unidade", "UN").strip().upper()
        valor_custo = parse_decimal(request.form.get("valor_custo", "0"))

        if not nome:
            flash("Informe o nome do produto.", "warning")
            return redirect("/produtos")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                UPDATE produtos
                SET nome=%s,
                    marca=%s,
                    modelo=%s,
                    unidade=%s,
                    valor_custo=%s
                WHERE id=%s AND empresa_id=%s
            """, (
                nome, marca, modelo,
                unidade, valor_custo,
                prod_id, empresa_id
            ))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Produto não encontrado.", "danger")
            else:
                conn.commit()
                flash("Produto atualizado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")

    # ======================================================
    # MOVIMENTAÇÃO DE ESTOQUE
    # ======================================================
    @app.route("/produtos/<int:prod_id>/estoque/mov", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def produtos_estoque_mov(prod_id):

        empresa_id = session.get("empresa_id")
        usuario = session.get("usuario") or session.get("usuario_id")

        tipo = request.form.get("tipo")
        quantidade = parse_decimal(request.form.get("quantidade", "0"))
        observacao = request.form.get("observacao", "").strip()

        if tipo not in ("ENTRADA", "SAIDA", "AJUSTE"):
            flash("Tipo de movimentação inválido.", "danger")
            return redirect("/produtos")

        if quantidade <= 0:
            flash("Quantidade deve ser maior que zero.", "warning")
            return redirect("/produtos")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT estoque_atual
                FROM produtos
                WHERE id=%s AND empresa_id=%s
            """, (prod_id, empresa_id))

            row = cur.fetchone()
            if not row:
                flash("Produto não encontrado.", "danger")
                return redirect("/produtos")

            estoque_atual = row[0]

            if tipo == "ENTRADA":
                novo_estoque = estoque_atual + quantidade
            elif tipo == "SAIDA":
                if estoque_atual < quantidade:
                    flash("Estoque insuficiente.", "danger")
                    return redirect("/produtos")
                novo_estoque = estoque_atual - quantidade
            else:  # AJUSTE
                novo_estoque = quantidade

            cur.execute("""
                UPDATE produtos
                SET estoque_atual=%s
                WHERE id=%s AND empresa_id=%s
            """, (novo_estoque, prod_id, empresa_id))

            cur.execute("""
                INSERT INTO estoque_movimentos
                (produto_id, tipo, quantidade, observacao, usuario)
                VALUES (%s,%s,%s,%s,%s)
            """, (prod_id, tipo, quantidade, observacao, usuario))

            conn.commit()
            flash("Movimentação registrada com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(str(e), "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")
    # ======================================================
    # EXCLUIR PRODUTO
    # ======================================================
    @app.route("/produtos/<int:prod_id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("SUPER_ADMIN")
    def produtos_excluir(prod_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT 1 FROM estoque_movimentos
                WHERE produto_id=%s LIMIT 1
            """, (prod_id,))

            if cur.fetchone():
                flash(
                    "Exclusão bloqueada: produto possui histórico de estoque.",
                    "warning"
                )
                return redirect("/produtos")

            cur.execute("""
                DELETE FROM produtos
                WHERE id=%s AND empresa_id=%s
            """, (prod_id, empresa_id))

            if cur.rowcount == 0:
                conn.rollback()
                flash("Produto não encontrado.", "danger")
            else:
                conn.commit()
                flash("Produto excluído com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao excluir produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")

    # ======================================================
    # HISTÓRICO DE ESTOQUE (HTML)
    # ======================================================
    @app.route("/produtos/<int:prod_id>/estoque/historico")
    @login_required
    @require_empresa
    def produtos_estoque_historico(prod_id):

        empresa_id = session.get("empresa_id")
        data_ini = request.args.get("data_ini") or date.today().replace(day=1).isoformat()
        data_fim = request.args.get("data_fim") or date.today().isoformat()

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, nome, marca, modelo, unidade, estoque_atual, valor_custo
            FROM produtos
            WHERE id=%s AND empresa_id=%s
        """, (prod_id, empresa_id))

        produto = cur.fetchone()
        if not produto:
            cur.close()
            conn.close()
            flash("Produto não encontrado.", "danger")
            return redirect("/produtos")

        valor_custo = produto["valor_custo"] or 0

        cur.execute("""
            SELECT tipo, quantidade, observacao, usuario, data_mov
            FROM estoque_movimentos
            WHERE produto_id=%s
              AND DATE(data_mov) BETWEEN %s AND %s
            ORDER BY data_mov DESC
        """, (prod_id, data_ini, data_fim))

        movimentos = cur.fetchall()

        resumo = {
            "entradas": 0,
            "saidas": 0,
            "ajustes": 0,
            "consumo": 0.0
        }

        for tipo, qtd, *_ in movimentos:
            if tipo == "ENTRADA":
                resumo["entradas"] += qtd
            elif tipo == "SAIDA":
                resumo["saidas"] += qtd
                resumo["consumo"] += qtd * valor_custo
            elif tipo == "AJUSTE":
                resumo["ajustes"] += qtd

        cur.close()
        conn.close()

        return render_template(
            "estoque_historico.html",
            produto=produto,
            movimentos=movimentos,
            resumo=resumo,
            data_ini=data_ini,
            data_fim=data_fim,
            total_reg=len(movimentos),
            page=1,
            per_page=len(movimentos) or 1,
            total_pages=1
        )

    # ======================================================
    # HISTÓRICO CSV
    # ======================================================
    @app.route("/produtos/<int:prod_id>/estoque/historico.csv")
    @login_required
    @require_empresa
    def produtos_estoque_historico_csv(prod_id):

        empresa_id = session.get("empresa_id")
        data_ini = request.args.get("data_ini")
        data_fim = request.args.get("data_fim")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            SELECT nome, unidade
            FROM produtos
            WHERE id=%s AND empresa_id=%s
        """, (prod_id, empresa_id))

        nome, unidade = cur.fetchone()

        cur.execute("""
            SELECT data_mov, tipo, quantidade, observacao, usuario
            FROM estoque_movimentos
            WHERE produto_id=%s
              AND DATE(data_mov) BETWEEN %s AND %s
            ORDER BY data_mov DESC
        """, (prod_id, data_ini, data_fim))

        movimentos = cur.fetchall()
        cur.close()
        conn.close()

        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output, delimiter=';')

        writer.writerow([
            "Produto", "Data/Hora", "Tipo",
            "Quantidade", "Unidade", "Observação", "Usuário"
        ])

        for m in movimentos:
            writer.writerow([nome, *m, unidade])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                f"attachment; filename=historico_estoque_{prod_id}.csv"
            }
        )
