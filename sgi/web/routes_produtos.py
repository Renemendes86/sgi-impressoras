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

        # 🔥 CORREÇÃO PRINCIPAL (evita erro com campo vazio)
        valor_custo = parse_decimal(request.form.get("valor_custo")) or 0
        estoque_inicial = parse_decimal(request.form.get("estoque_inicial")) or 0

        # 🔒 VALIDAÇÕES
        if not nome:
            flash("Informe o nome do produto.", "warning")
            return redirect("/produtos")

        if not empresa_id:
            flash("Erro: empresa não selecionada.", "danger")
            return redirect("/selecionar-empresa")

        conn = conectar()
        cur = conn.cursor()

        try:
            # 🔍 DEBUG (ajuda MUITO em produção)
            print("=== DEBUG PRODUTO ===")
            print("EMPRESA_ID:", empresa_id)
            print("NOME:", nome)
            print("VALOR_CUSTO:", valor_custo)
            print("ESTOQUE_INICIAL:", estoque_inicial)

            # INSERT PRODUTO
            cur.execute("""
                INSERT INTO produtos
                (empresa_id, nome, marca, modelo, valor_custo, unidade, estoque_atual)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                empresa_id, nome, marca, modelo,
                valor_custo, unidade, estoque_inicial
            ))

            prod_id = cur.fetchone()["id"] 

            # MOVIMENTO DE ESTOQUE (somente se tiver valor)
            if estoque_inicial and estoque_inicial > 0:
                cur.execute("""
                    INSERT INTO estoque_movimentos
                    (produto_id, tipo, quantidade, observacao, usuario)
                    VALUES (%s,'ENTRADA',%s,'Estoque inicial',%s)
                """, (prod_id, estoque_inicial, usuario))

            conn.commit()
            flash("Produto cadastrado com sucesso.", "success")

        except Exception as e:
            import traceback
            print("=== ERRO AO SALVAR PRODUTO ===")
            print(traceback.format_exc())

            conn.rollback()
            flash(f"Erro ao salvar produto: {e}", "danger")

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

        # 🔥 CORREÇÃO SEGURA
        valor_custo = parse_decimal(request.form.get("valor_custo")) or 0

        # 🔒 VALIDAÇÕES
        if not nome:
            flash("Informe o nome do produto.", "warning")
            return redirect("/produtos")

        if not empresa_id:
            flash("Erro: empresa não selecionada.", "danger")
            return redirect("/selecionar-empresa")

        conn = conectar()
        cur = conn.cursor()

        try:
            # 🔍 DEBUG
            print("=== DEBUG EDITAR PRODUTO ===")
            print("PROD_ID:", prod_id)
            print("EMPRESA_ID:", empresa_id)
            print("NOME:", nome)
            print("VALOR_CUSTO:", valor_custo)

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
                flash("Produto não encontrado ou não pertence a esta empresa.", "danger")
            else:
                conn.commit()
                flash("Produto atualizado com sucesso.", "success")

        except Exception as e:
            import traceback
            print("=== ERRO AO ATUALIZAR PRODUTO ===")
            print(traceback.format_exc())

            conn.rollback()
            flash(f"Erro ao atualizar produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")

   # ======================================================
    # MOVIMENTAÇÃO DE ESTOQUE
    # ======================================================
    from decimal import Decimal

    @app.route("/produtos/<int:prod_id>/estoque/mov", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def produtos_estoque_mov(prod_id):

        empresa_id = session.get("empresa_id")
        usuario = session.get("usuario") or session.get("usuario_id")

        tipo = request.form.get("tipo")

        # 🔥 FORÇA CONVERSÃO PRA DECIMAL (RESOLVE DEFINITIVO)
        quantidade_raw = request.form.get("quantidade")
        quantidade = Decimal(str(parse_decimal(quantidade_raw) or 0))

        observacao = request.form.get("observacao", "").strip()

        # 🔒 VALIDAÇÕES
        if not empresa_id:
            flash("Erro: empresa não selecionada.", "danger")
            return redirect("/selecionar-empresa")

        if tipo not in ("ENTRADA", "SAIDA", "AJUSTE"):
            flash("Tipo de movimentação inválido.", "danger")
            return redirect("/produtos")

        if quantidade <= Decimal("0"):
            flash("Quantidade deve ser maior que zero.", "warning")
            return redirect("/produtos")

        conn = conectar()
        cur = conn.cursor()

        try:
            # 🔍 DEBUG
            print("=== DEBUG MOVIMENTAÇÃO ===")
            print("PROD_ID:", prod_id)
            print("EMPRESA_ID:", empresa_id)
            print("TIPO:", tipo)
            print("QUANTIDADE:", quantidade, type(quantidade))

            cur.execute("""
                SELECT estoque_atual
                FROM produtos
                WHERE id=%s AND empresa_id=%s
            """, (prod_id, empresa_id))

            row = cur.fetchone()

            if not row:
                flash("Produto não encontrado.", "danger")
                return redirect("/produtos")

            # ✅ SEMPRE DECIMAL
            estoque_atual = Decimal(str(row["estoque_atual"] or 0))

            # 🔄 REGRAS DE NEGÓCIO
            if tipo == "ENTRADA":
                novo_estoque = estoque_atual + quantidade

            elif tipo == "SAIDA":
                if estoque_atual < quantidade:
                    flash("Estoque insuficiente.", "danger")
                    return redirect("/produtos")
                novo_estoque = estoque_atual - quantidade

            else:  # AJUSTE
                novo_estoque = quantidade

            # UPDATE ESTOQUE
            cur.execute("""
                UPDATE produtos
                SET estoque_atual=%s
                WHERE id=%s AND empresa_id=%s
            """, (novo_estoque, prod_id, empresa_id))

            # REGISTRO DO MOVIMENTO
            cur.execute("""
                INSERT INTO estoque_movimentos
                (produto_id, tipo, quantidade, observacao, usuario)
                VALUES (%s,%s,%s,%s,%s)
            """, (prod_id, tipo, quantidade, observacao, usuario))

            conn.commit()
            flash("Movimentação registrada com sucesso.", "success")

        except Exception as e:
            import traceback
            print("=== ERRO MOVIMENTAÇÃO ===")
            print(traceback.format_exc())

            conn.rollback()
            flash(f"Erro ao movimentar estoque: {e}", "danger")

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

        if not empresa_id:
            flash("Erro: empresa não selecionada.", "danger")
            return redirect("/selecionar-empresa")

        conn = conectar()
        cur = conn.cursor()

        try:
            print("=== DEBUG EXCLUIR PRODUTO ===")
            print("PROD_ID:", prod_id)
            print("EMPRESA_ID:", empresa_id)

            # 🔒 VERIFICA MOVIMENTAÇÃO
            cur.execute("""
                SELECT 1
                FROM estoque_movimentos em
                JOIN produtos p ON p.id = em.produto_id
                WHERE em.produto_id = %s
                AND p.empresa_id = %s
                LIMIT 1
            """, (prod_id, empresa_id))

            tem_movimento = cur.fetchone()

            if tem_movimento:
                conn.rollback()
                flash(
                    "Não é possível excluir: produto possui movimentação de estoque.",
                    "warning"
                )
            else:
                # 🔒 EXCLUSÃO
                cur.execute("""
                    DELETE FROM produtos
                    WHERE id=%s AND empresa_id=%s
                """, (prod_id, empresa_id))

                if cur.rowcount == 0:
                    conn.rollback()
                    flash("Produto não encontrado ou não pertence a esta empresa.", "danger")
                else:
                    conn.commit()
                    flash("Produto excluído com sucesso.", "success")

        except Exception as e:
            import traceback
            print("=== ERRO AO EXCLUIR PRODUTO ===")
            print(traceback.format_exc())

            conn.rollback()
            flash(f"Erro ao excluir produto: {e}", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect("/produtos")

    # ======================================================
    # HISTÓRICO DE ESTOQUE (HTML)
    # ======================================================
    from decimal import Decimal
    from datetime import date

    @app.route("/produtos/<int:prod_id>/estoque/historico")
    @login_required
    @require_empresa
    def produtos_estoque_historico(prod_id):

        empresa_id = session.get("empresa_id")
        data_ini = request.args.get("data_ini") or date.today().replace(day=1).isoformat()
        data_fim = request.args.get("data_fim") or date.today().isoformat()

        conn = conectar()
        cur = conn.cursor()

        # 🔒 PRODUTO
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

        valor_custo = produto["valor_custo"] or Decimal("0")

        # 🔄 MOVIMENTOS
        cur.execute("""
            SELECT tipo, quantidade, observacao, usuario, data_mov
            FROM estoque_movimentos
            WHERE produto_id=%s
            AND DATE(data_mov) BETWEEN %s AND %s
            ORDER BY data_mov DESC
        """, (prod_id, data_ini, data_fim))

        movimentos = cur.fetchall()

        # 📊 RESUMO
        resumo = {
            "entradas": Decimal("0"),
            "saidas": Decimal("0"),
            "ajustes": Decimal("0"),
            "consumo": Decimal("0")
        }

        for mov in movimentos:
            tipo = mov["tipo"]
            qtd = mov["quantidade"] or Decimal("0")

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
    from flask import Response
    from datetime import date

    @app.route("/produtos/<int:prod_id>/estoque/historico.csv")
    @login_required
    @require_empresa
    def produtos_estoque_historico_csv(prod_id):

        empresa_id = session.get("empresa_id")
        data_ini = request.args.get("data_ini") or date.today().replace(day=1).isoformat()
        data_fim = request.args.get("data_fim") or date.today().isoformat()

        conn = conectar()
        cur = conn.cursor()

        # 🔒 PRODUTO
        cur.execute("""
            SELECT nome, unidade
            FROM produtos
            WHERE id=%s AND empresa_id=%s
        """, (prod_id, empresa_id))

        produto = cur.fetchone()

        if not produto:
            cur.close()
            conn.close()
            flash("Produto não encontrado.", "danger")
            return redirect("/produtos")

        nome = produto["nome"]
        unidade = produto["unidade"]

        # 🔄 MOVIMENTOS
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

        # 🧾 CABEÇALHO
        writer.writerow([
            "Produto", "Data/Hora", "Tipo",
            "Quantidade", "Unidade", "Observação", "Usuário"
        ])

        # 📄 DADOS
        for m in movimentos:
            writer.writerow([
                nome,
                m["data_mov"],
                m["tipo"],
                m["quantidade"],
                unidade,
                m["observacao"],
                m["usuario"]
            ])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                f"attachment; filename=historico_estoque_{prod_id}.csv"
            }
        )

