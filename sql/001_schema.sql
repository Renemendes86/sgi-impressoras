CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil VARCHAR(20) NOT NULL DEFAULT 'ADMIN',
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    tipo_pessoa VARCHAR(10) NOT NULL CHECK (tipo_pessoa IN ('FISICA','JURIDICA')),
    nome VARCHAR(120) NOT NULL,
    cnpj_cpf VARCHAR(20) UNIQUE NOT NULL,
    telefone VARCHAR(30),
    email VARCHAR(120),
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes (nome);
CREATE INDEX IF NOT EXISTS idx_clientes_doc ON clientes (cnpj_cpf);
