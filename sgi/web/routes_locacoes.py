# ==========================================================
# ROUTES – LOCAÇÕES
# ==========================================================

from flask import (
    render_template,
    request,
    redirect,
    flash,
    session
)

from datetime import datetime, date

from sgi.core.db import conectar
from sgi.core.permissions import (
    login_required,
    require_empresa,
    perfil_required,
    tem_permissao
)

# ==========================================================
# HELPERS
# ==========================================================

def parse_decimal(valor, default=0.0):
    """
    Converte valores vindos de formulário (pt-BR) para float.
    Valores vindos do banco (NUMERIC) não são alterados.
    """
    try:
        if valor is None:
            return float(default)

        if isinstance(valor, (int, float)):
            return float(valor)

        v = str(valor).replace("R$", "").strip()

        if "," in v:
            v = v.replace(".", "").replace(",", ".")

        return float(v)
    except Exception:
        return float(default)

# ==========================================================
# CONFIGURAÇÃO DAS ROTAS
# ==========================================================

def configurar_rotas_locacoes(app):

   # ======================================================
    # VISÃO GERAL DE LOCAÇÕES
    # ======================================================
    @app.route("/locacoes", methods=["GET"])
    @login_required
    @require_empresa
    def locacoes():

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        usuario_id = session.get("usuario_id")

        pode_ver_financeiro = tem_permissao(cur, usuario_id, "ver_financeiro")
        pode_ver_valor_aluguel = tem_permissao(cur, usuario_id, "ver_valor_aluguel")
        pode_ver_valor_custo = tem_permissao(cur, usuario_id, "ver_valor_custo")

        # ======================================================
        # DEFINIR PERÍODO DO MÊS ATUAL
        # ======================================================
        from datetime import date

        hoje = date.today()

        inicio = date(hoje.year, hoje.month, 1)

        if hoje.month == 12:
            fim = date(hoje.year + 1, 1, 1)
        else:
            fim = date(hoje.year, hoje.month + 1, 1)

        # ======================================================
        # CONSULTA
        # ======================================================

        cur.execute("""
            SELECT
                c.id,
                c.nome,

                COALESCE(i.qtd_locadas,0) AS qtd_locadas,
                COALESCE(i.total_aluguel,0) AS total_aluguel,

                COALESCE(co.custo_total,0) AS custo_total

            FROM clientes c

            LEFT JOIN (
                SELECT
                    cliente_id,
                    COUNT(*) AS qtd_locadas,
                    SUM(valor_aluguel) AS total_aluguel
                FROM impressoras
                WHERE locada = TRUE
                AND empresa_id = %s
                GROUP BY cliente_id
            ) i ON i.cliente_id = c.id

            LEFT JOIN (
                SELECT
                    cliente_id,
                    SUM(quantidade * valor_unitario) AS custo_total
                FROM custos_impressora
                WHERE data_custo >= %s
                AND data_custo < %s
                GROUP BY cliente_id
            ) co ON co.cliente_id = c.id

            WHERE c.empresa_id = %s
            AND i.qtd_locadas IS NOT NULL

            ORDER BY c.nome
        """, (empresa_id, inicio, fim, empresa_id))

        clientes = cur.fetchall()

        # ======================================================
        # CALCULAR LUCRO E MARGEM
        # ======================================================

        for c in clientes:

            aluguel = float(c["total_aluguel"] or 0)
            custo = float(c["custo_total"] or 0)

            lucro = aluguel - custo

            margem = (lucro / aluguel * 100) if aluguel > 0 else 0

            c["lucro"] = lucro
            c["margem"] = margem

        # ======================================================
        # CONTROLE DE PERMISSÕES
        # ======================================================

        if not pode_ver_valor_aluguel:
            for c in clientes:
                c["total_aluguel"] = None

        if not pode_ver_valor_custo:
            for c in clientes:
                c["custo_total"] = None

        if not pode_ver_financeiro:
            for c in clientes:
                c["lucro"] = None
                c["margem"] = None

        cur.close()
        conn.close()

        return render_template(
            "locacoes.html",
            clientes=clientes,
            pode_ver_financeiro=pode_ver_financeiro,
            pode_ver_valor_aluguel=pode_ver_valor_aluguel,
            pode_ver_valor_custo=pode_ver_valor_custo
        )

    # ======================================================
    # DETALHE DA LOCAÇÃO DO CLIENTE
    # ======================================================
    @app.route("/locacoes/<int:cliente_id>", methods=["GET"])
    @login_required
    @require_empresa
    def locacoes_cliente(cliente_id):

        empresa_id = session.get("empresa_id")
        mes = request.args.get("mes") or datetime.now().strftime("%Y-%m")

        ano, mes_num = map(int, mes.split("-"))
        inicio = date(ano, mes_num, 1)
        fim = date(ano + 1, 1, 1) if mes_num == 12 else date(ano, mes_num + 1, 1)

        conn = conectar()
        cur = conn.cursor()

        usuario_id = session.get("usuario_id")

        pode_ver_fin = tem_permissao(cur, usuario_id, "ver_financeiro")
        pode_ver_valor_aluguel = tem_permissao(cur, usuario_id, "ver_valor_aluguel")
        pode_ver_valor_custo = tem_permissao(cur, usuario_id, "ver_valor_custo")

        # CLIENTE
        cur.execute("""
            SELECT id, nome, tipo_pessoa, cnpj_cpf
            FROM clientes
            WHERE id = %s AND empresa_id = %s
        """, (cliente_id, empresa_id))

        cliente = cur.fetchone()

        if not cliente:
            cur.close()
            conn.close()
            flash("Cliente não encontrado nesta empresa.", "danger")
            return redirect("/locacoes")

        # IMPRESSORAS LOCADAS
        cur.execute("""
            SELECT
                id,
                modelo,
                marca,
                patrimonio,
                nome_equipamento,
                COALESCE(local_na_empresa,'') AS local_na_empresa,
                COALESCE(valor_aluguel,0) AS valor_aluguel
            FROM impressoras
            WHERE empresa_id = %s
              AND cliente_id = %s
              AND locada = TRUE
            ORDER BY modelo, patrimonio
        """, (empresa_id, cliente_id))

        impressoras = cur.fetchall()

        # CUSTOS POR IMPRESSORA (MÊS)
        cur.execute("""
            SELECT
                ci.impressora_id,
                SUM(ci.quantidade * ci.valor_unitario) AS custo_mes
            FROM custos_impressora ci
            JOIN impressoras i ON i.id = ci.impressora_id
            WHERE ci.cliente_id = %s
              AND i.empresa_id = %s
              AND ci.data_custo >= %s
              AND ci.data_custo < %s
            GROUP BY ci.impressora_id
        """, (cliente_id, empresa_id, inicio, fim))

        custos_por_impressora = {
        row["impressora_id"]: float(row["custo_mes"] or 0)
        for row in cur.fetchall()
        }
        

        for i in impressoras:
            valor_aluguel = float(i["valor_aluguel"] or 0)
            custo_mes = custos_por_impressora.get(i["id"], 0)

            # adicionando dinamicamente (se usar RealDictCursor isso vira chave)
            
            i["custo_mes"] = custo_mes
            i["lucro_mes"] = valor_aluguel - custo_mes
            i["margem_mes"] = (
                    (i["lucro_mes"] / valor_aluguel) * 100
                    if valor_aluguel > 0 else 0
                )
            
    

        # IMPRESSORAS DISPONÍVEIS
        cur.execute("""
            SELECT id, modelo, marca, patrimonio, nome_equipamento
            FROM impressoras
            WHERE empresa_id = %s AND locada = FALSE
            ORDER BY modelo, patrimonio
        """, (empresa_id,))

        impressoras_disponiveis = cur.fetchall()

        # PRODUTOS
        cur.execute("""
            SELECT id, nome,
                   COALESCE(valor_custo,0) AS valor_custo,
                   COALESCE(estoque_atual,0) AS estoque_atual
            FROM produtos
            WHERE empresa_id = %s
            ORDER BY nome
        """, (empresa_id,))

        produtos = cur.fetchall()

        # SERVIÇOS
        cur.execute("""
            SELECT id, nome,
                   COALESCE(valor_custo,0) AS valor_custo
            FROM servicos
            WHERE empresa_id = %s
            ORDER BY nome
        """, (empresa_id,))

        servicos = cur.fetchall()

        # CUSTOS DO MÊS (DETALHADO CORRETO)
        cur.execute("""
            SELECT
            ci.id,
            ci.data_custo,
            ci.tipo,
            ci.quantidade,
            ci.valor_unitario,
            (ci.quantidade * ci.valor_unitario) AS total_item,
            i.modelo AS imp_modelo,
            i.patrimonio AS imp_patrimonio,
            COALESCE(p.nome, s.nome) AS item
            FROM custos_impressora ci
            JOIN impressoras i ON i.id = ci.impressora_id
            LEFT JOIN produtos p ON p.id = ci.produto_id
            LEFT JOIN servicos s ON s.id = ci.servico_id
            WHERE ci.cliente_id = %s
            AND i.empresa_id = %s
            AND ci.data_custo >= %s
            AND ci.data_custo < %s
            ORDER BY ci.data_custo DESC
        """, (cliente_id, empresa_id, inicio, fim))

        custos_detalhe = cur.fetchall()


        cur.close()
        conn.close()

        total_aluguel = sum(float(i["valor_aluguel"] or 0) for i in impressoras)
        custo_total = sum(float(c["total_item"] or 0) for c in custos_detalhe)
        lucro = total_aluguel - custo_total
        margem = (lucro / total_aluguel * 100) if total_aluguel > 0 else 0

        if not pode_ver_valor_aluguel:
            total_aluguel = None

        if not pode_ver_valor_custo:
            custo_total = None

        if not pode_ver_fin:
            lucro = None
            margem = None

        return render_template(
            "locacoes_cliente.html",
            cliente=cliente,
            impressoras=impressoras,
            impressoras_disponiveis=impressoras_disponiveis,
            produtos=produtos,
            servicos=servicos,
            custos_detalhe=custos_detalhe,
            mes=mes,

            total_aluguel=total_aluguel,
            custo_total=custo_total,

            # 🔹 NOVO PADRÃO
            lucro=lucro,
            margem=margem,

            # 🔹 COMPATIBILIDADE TOTAL (não perde nada)
            lucro_total=lucro,
            margem_total=margem,

            pode_ver_financeiro=pode_ver_fin,
            pode_ver_valor_aluguel=pode_ver_valor_aluguel,
            pode_ver_valor_custo=pode_ver_valor_custo
        )




    # ======================================================
    # ADICIONAR IMPRESSORA À LOCAÇÃO
    # ======================================================
    @app.route("/locacoes/<int:cliente_id>/impressora/adicionar", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def locacao_adicionar_impressora(cliente_id):

        empresa_id = session.get("empresa_id")

        impressora_id = request.form.get("impressora_id")
        local = request.form.get("local_na_empresa", "").strip()
        valor_aluguel = parse_decimal(request.form.get("valor_aluguel", "0"))

        if not impressora_id:
            flash("Selecione uma impressora disponível.", "warning")
            return redirect(f"/locacoes/{cliente_id}")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE impressoras
            SET locada = TRUE,
                cliente_id = %s,
                local_na_empresa = %s,
                valor_aluguel = %s
            WHERE id = %s
              AND empresa_id = %s
              AND locada = FALSE
        """, (cliente_id, local, valor_aluguel, impressora_id, empresa_id))

        if cur.rowcount == 0:
            conn.rollback()
            flash("Não foi possível locar a impressora.", "danger")
        else:
            conn.commit()
            flash("Impressora adicionada à locação.", "success")

        cur.close()
        conn.close()

        return redirect(f"/locacoes/{cliente_id}")

    # ======================================================
    # REMOVER IMPRESSORA DA LOCAÇÃO
    # ======================================================
    @app.route("/locacoes/<int:cliente_id>/impressora/<int:imp_id>/remover", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def locacao_remover_impressora(cliente_id, imp_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            UPDATE impressoras
            SET locada = FALSE,
                cliente_id = NULL,
                local_na_empresa = ''
            WHERE id = %s
              AND empresa_id = %s
              AND cliente_id = %s
              AND locada = TRUE
        """, (imp_id, empresa_id, cliente_id))

        if cur.rowcount == 0:
            conn.rollback()
            flash("Impressora não encontrada nesta locação.", "warning")
        else:
            conn.commit()
            flash("Impressora removida da locação.", "success")

        cur.close()
        conn.close()

        return redirect(f"/locacoes/{cliente_id}")

        #======================================================
    # LANÇAR CUSTO NA LOCAÇÃO (COM BAIXA AUTOMÁTICA)
    # ======================================================
    @app.route("/locacoes/<int:cliente_id>/custos/novo", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def locacao_lancar_custo(cliente_id):

        empresa_id = session.get("empresa_id")
        usuario = session.get("usuario") or session.get("usuario_id")

        impressora_id = request.form.get("impressora_id")
        tipo = request.form.get("tipo")
        descricao = request.form.get("descricao", "").strip()
        quantidade = parse_decimal(request.form.get("quantidade", "1"), 1)
        valor_unitario = parse_decimal(request.form.get("valor_unitario", "0"))
        data_custo = request.form.get("data_custo") or date.today()

        produto_id = request.form.get("produto_id") or None
        servico_id = request.form.get("servico_id") or None

        # =============================
        # VALIDAÇÕES INICIAIS
        # =============================
        if not impressora_id or not tipo:
            flash("Dados do custo incompletos.", "warning")
            return redirect(f"/locacoes/{cliente_id}")

        try:
            impressora_id = int(impressora_id)

            if produto_id:
                produto_id = int(produto_id)

            if servico_id:
                servico_id = int(servico_id)

        except ValueError:
            flash("ID inválido enviado pelo formulário.", "danger")
            return redirect(f"/locacoes/{cliente_id}")

        if tipo == "PRODUTO" and not produto_id:
            flash("Selecione um produto.", "warning")
            return redirect(f"/locacoes/{cliente_id}")

        if tipo == "SERVICO" and not servico_id:
            flash("Selecione um serviço.", "warning")
            return redirect(f"/locacoes/{cliente_id}")

        conn = conectar()
        cur = conn.cursor()

        try:
            # =============================
            # BAIXA ESTOQUE SE FOR PRODUTO
            # =============================
            if tipo == "PRODUTO":

                cur.execute("""
                    SELECT estoque_atual
                    FROM produtos
                    WHERE id = %s AND empresa_id = %s
                    FOR UPDATE
                """, (produto_id, empresa_id))

                row = cur.fetchone()

                if not row:
                    raise Exception("Produto não encontrado.")

                estoque_atual = float(row["estoque_atual"])

                if estoque_atual < quantidade:
                    raise Exception("Estoque insuficiente para lançar este custo.")

                novo_estoque = estoque_atual - quantidade

                cur.execute("""
                    UPDATE produtos
                    SET estoque_atual = %s
                    WHERE id = %s AND empresa_id = %s
                """, (novo_estoque, produto_id, empresa_id))

                # Registrar histórico de consumo
                cur.execute("""
                    INSERT INTO estoque_movimentos
                        (produto_id, tipo, quantidade, observacao, usuario)
                    VALUES (%s, 'CONSUMO', %s, %s, %s)
                """, (
                    produto_id,
                    quantidade,
                    f"Consumo na locação - Cliente {cliente_id}",
                    usuario
                ))

            # =============================
            # INSERIR CUSTO
            # =============================
            cur.execute("""
                INSERT INTO custos_impressora
                    (cliente_id,
                    impressora_id,
                    tipo,
                    produto_id,
                    servico_id,
                    descricao,
                    quantidade,
                    valor_unitario,
                    data_custo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                cliente_id,
                impressora_id,
                tipo,
                produto_id,
                servico_id,
                descricao,
                quantidade,
                valor_unitario,
                data_custo
            ))

            conn.commit()
            flash("Custo lançado com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            print("ERRO REAL AO LANÇAR CUSTO:", repr(e))  # Debug real no terminal
            flash("Erro ao lançar custo. Verifique o terminal.", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect(f"/locacoes/{cliente_id}")
    
        # ======================================================
    # EXCLUIR CUSTO DA LOCAÇÃO
    # ======================================================
    @app.route("/locacoes/<int:cliente_id>/custo/<int:custo_id>/excluir", methods=["POST"])
    @login_required
    @require_empresa
    @perfil_required("ADMIN", "OPERADOR", "SUPER_ADMIN")
    def locacao_excluir_custo(cliente_id, custo_id):

        empresa_id = session.get("empresa_id")

        conn = conectar()
        cur = conn.cursor()

        try:
            # Buscar custo antes de excluir
            cur.execute("""
                SELECT tipo, produto_id, quantidade
                FROM custos_impressora
                WHERE id = %s AND cliente_id = %s
            """, (custo_id, cliente_id))

            custo = cur.fetchone()

            if not custo:
                flash("Custo não encontrado.", "warning")
                return redirect(f"/locacoes/{cliente_id}")

            tipo = custo["tipo"]
            produto_id = custo["produto_id"]
            quantidade = float(custo["quantidade"] or 0)

            # Se for produto → devolver estoque
            if tipo == "PRODUTO" and produto_id:

                cur.execute("""
                    UPDATE produtos
                    SET estoque_atual = estoque_atual + %s
                    WHERE id = %s AND empresa_id = %s
                """, (quantidade, produto_id, empresa_id))

                # Registrar ajuste de retorno
                cur.execute("""
                    INSERT INTO estoque_movimentos
                        (produto_id, tipo, quantidade, observacao, usuario)
                    VALUES (%s, 'AJUSTE', %s, %s, %s)
                """, (
                    produto_id,
                    quantidade,
                    f"Estorno de consumo - Exclusão custo cliente {cliente_id}",
                    session.get("usuario")
                ))

            # Excluir custo
            cur.execute("""
                DELETE FROM custos_impressora
                WHERE id = %s AND cliente_id = %s
            """, (custo_id, cliente_id))

            conn.commit()
            flash("Custo excluído com sucesso.", "success")

        except Exception as e:
            conn.rollback()
            print("ERRO AO EXCLUIR CUSTO:", repr(e))
            flash("Erro ao excluir custo. Verifique o terminal.", "danger")

        finally:
            cur.close()
            conn.close()

        return redirect(f"/locacoes/{cliente_id}")
