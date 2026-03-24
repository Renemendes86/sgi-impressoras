from sgi.core.db import conectar

def listar_clientes(busca: str = ""):
    conn = conectar()
    cur = conn.cursor()

    if busca:
        like = f"%{busca}%"
        cur.execute("""
            SELECT id, tipo_pessoa, nome, cnpj_cpf, telefone, email, criado_em
            FROM clientes
            WHERE nome ILIKE %s OR cnpj_cpf ILIKE %s OR email ILIKE %s
            ORDER BY id DESC
        """, (like, like, like))
    else:
        cur.execute("""
            SELECT id, tipo_pessoa, nome, cnpj_cpf, telefone, email, criado_em
            FROM clientes
            ORDER BY id DESC
        """)

    dados = cur.fetchall()
    cur.close()
    conn.close()
    return dados


def inserir_cliente(tipo_pessoa, nome, cnpj_cpf, telefone, email):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO clientes (tipo_pessoa, nome, cnpj_cpf, telefone, email)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (tipo_pessoa, nome, cnpj_cpf, telefone, email))

    novo_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return novo_id


def atualizar_cliente(cliente_id, tipo_pessoa, nome, cnpj_cpf, telefone, email):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        UPDATE clientes
        SET tipo_pessoa=%s, nome=%s, cnpj_cpf=%s, telefone=%s, email=%s
        WHERE id=%s
    """, (tipo_pessoa, nome, cnpj_cpf, telefone, email, cliente_id))

    conn.commit()
    cur.close()
    conn.close()


def deletar_cliente(cliente_id):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("DELETE FROM clientes WHERE id=%s", (cliente_id,))

    conn.commit()
    cur.close()
    conn.close()
