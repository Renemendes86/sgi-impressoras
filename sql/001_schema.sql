-- EMPRESAS
CREATE TABLE IF NOT EXISTS empresas (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    criado_em TIMESTAMP DEFAULT NOW()
);

-- USUÁRIOS
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil VARCHAR(20) NOT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    empresa_id INTEGER REFERENCES empresas(id),
    criado_em TIMESTAMP DEFAULT NOW()
);

-- CLIENTES
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER REFERENCES empresas(id),
    nome VARCHAR(120) NOT NULL,
    cnpj_cpf VARCHAR(20),
    municipio VARCHAR(100),
    criado_em TIMESTAMP DEFAULT NOW()
);


-- ADMIN PADRÃO (GARANTE SUPER_ADMIN SEMPRE)
INSERT INTO usuarios (usuario, senha_hash, perfil)
VALUES ('admin', 'admin123', 'SUPER_ADMIN')
ON CONFLICT (usuario)
DO UPDATE SET perfil = EXCLUDED.perfil;

-- EMPRESA PADRÃO
INSERT INTO empresas (nome)
VALUES ('EMPRESA PADRÃO')
ON CONFLICT DO NOTHING;