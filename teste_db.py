from sgi.core.db import conectar

conn = conectar()
cur = conn.cursor()
cur.execute("SELECT 1 as ok")
print(cur.fetchone())
cur.close()
conn.close()
print("✅ Conexão PostgreSQL OK!")
