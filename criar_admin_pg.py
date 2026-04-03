import bcrypt
from sgi.core.db import conectar

def main():
    conn = conectar()
    cur = conn.cursor()

    # cria tabela se não existir
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        usuario VARCHAR(50) UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL,
        perfil VARCHAR(20) NOT NULL DEFAULT 'ADMIN',
        criado_em TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)

    usuario = "admin"
    senha = "123456"
    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    cur.execute("""
        INSERT INTO usuarios (usuario, senha_hash, perfil)
        VALUES (%s, %s, %s)
        ON CONFLICT (usuario) DO UPDATE SET
            senha_hash = EXCLUDED.senha_hash,
            perfil = EXCLUDED.perfil
    """, (usuario, senha_hash, "ADMIN"))

    conn.commit()
    cur.close()
    conn.close()

    print("✅ Tabela usuarios OK e admin criado/atualizado: admin / 123456")

if __name__ == "__main__":
    main()
