from __future__ import annotations

from pathlib import Path

from sgi.core.db import conectar


def main() -> None:
    # Resolve caminho absoluto do SQL independente do "onde rodou o python"
    base_dir = Path(__file__).resolve().parent
    sql_path = base_dir / "sql" / "001_schema.sql"

    if not sql_path.exists():
        raise FileNotFoundError(f"Arquivo SQL não encontrado em: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")

    conn = conectar(dict_cursor=True)
    cur = conn.cursor()

    try:
        # Executa o schema
        cur.execute(sql)
        conn.commit()

        # Verificações rápidas (profissionais)
        cur.execute("SELECT 1 FROM public.empresas LIMIT 1;")
        if not cur.fetchone():
            raise RuntimeError("Falha: tabela empresas não foi criada/populada corretamente.")

        cur.execute("SELECT usuario, perfil, ativo FROM public.usuarios WHERE usuario='admin' LIMIT 1;")
        admin = cur.fetchone()
        if not admin:
            raise RuntimeError("Falha: usuário admin não foi criado pelo SQL (seed).")

        print("✅ Banco aplicado com sucesso.")
        print("✅ Admin confirmado no banco: usuario=admin")

        # Importante: a senha padrão deve ser a mesma do seu SQL
        print("ℹ️ Login padrão esperado: admin / admin123")

    finally:
        try:
            cur.close()
        finally:
            conn.close()


if __name__ == "__main__":
    main()
