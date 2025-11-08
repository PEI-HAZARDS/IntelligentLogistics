-- DDL PostgreSQL

-- enums para estados
CREATE TYPE estado_entrega AS ENUM ('concluida', 'em_caminho', 'atrasada');
CREATE TYPE estado_descarga AS ENUM ('nao_iniciada', 'em_espera', 'em_descarga', 'concluida', 'saiu_porto');
CREATE TYPE tipo_carga AS ENUM ('geral', 'perigosa', 'refrigerada', 'viva');
CREATE TYPE estado_fisico AS ENUM ('líquido', 'sólido', 'gasoso', 'hibrido');
CREATE TYPE origem_detecao AS ENUM ('camera', 'manual');
CREATE TYPE nivel_acesso AS ENUM ('admin', 'default');


-- Classe pai: Trabalhador_Porto
CREATE TABLE trabalhador_porto (
    num_trabalhador SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT
);

-- Classe filha: Gestor e Operador (PK = FK -> trabalhador_porto)
CREATE TABLE gestor (
    num_trabalhador INTEGER PRIMARY KEY REFERENCES trabalhador_porto(num_trabalhador) ON DELETE CASCADE,
    cargo TEXT,
    departamento TEXT,
    contacto_interno TEXT,
    nivel_acesso nivel_acesso DEFAULT 'default'
);

CREATE TABLE operador (
    num_trabalhador INTEGER PRIMARY KEY REFERENCES trabalhador_porto(num_trabalhador) ON DELETE CASCADE
);

-- Empresa
CREATE TABLE empresa (
    id_empresa SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    nif TEXT UNIQUE,
    contacto TEXT,
    descricao TEXT
);

-- Condutor
CREATE TABLE condutor (
  num_carta_cond TEXT PRIMARY KEY,
  id_empresa INTEGER REFERENCES empresa(id_empresa),
  nome TEXT NOT NULL,
  contacto TEXT
);

-- Camião
CREATE TABLE camiao (
    matricula TEXT PRIMARY KEY,
    marca TEXT,
    tipo_carroceria TEXT,
);

-- relação Conduz (histórico de que condutor conduziu que camião)
CREATE TABLE conduz (
    matricula_camiao TEXT REFERENCES camiao(matricula) ON DELETE CASCADE,
    num_carta_cond TEXT REFERENCES condutor(num_carta_cond) ON DELETE CASCADE,
    inicio TIMESTAMP NOT NULL,
    fim TIMESTAMP,

    PRIMARY KEY (matricula_camiao, num_carta_cond, inicio)
);

-- Carga
CREATE TABLE carga (
    id_carga SERIAL PRIMARY KEY,
    peso DECIMAL(10,2) CHECK (peso > 0),
    descricao TEXT,
    adr BOOLEAN DEFAULT FALSE,
    tipo_carga tipo_carga NOT NULL,
    estado_fisico, estado_fisico NOT NULL,
    unidade_medida VARCHAR(10) DEFAULT 'Kg' -- Exemplo: Kg, Toneladas (será para fazer conversões de kg para toneladas através de funções)
);


-- Cais
CREATE TABLE cais (
    id_cais SERIAL PRIMARY KEY,
    estado TEXT CHECK (estado IN ('manutenção', 'operacional', 'fechado')) DEFAULT 'operacional',
    capacidade_max INTEGER,
    localizacao_gps TEXT CHECK (localizacao_gps ~ '^\-?\d{1,3}\.\d+,\s*\-?\d{1,3}\.\d+$')
);

-- Turno
    CREATE TABLE turno (
    id_turno SERIAL PRIMARY KEY,
    num_trabalhador_operador INTEGER REFERENCES operador(num_trabalhador) AS num_operador_cancela,
    num_trabalhador_gestor INTEGER REFERENCES gestor(num_trabalhador) AS num_gestor_responsavel,
    hora_inicio TIME,
    hora_fim TIME,
    descricao TEXT
);


-- Deteccao_Valida
CREATE TABLE deteccao_valida (
    id_detecao INTEGER PRIMARY KEY,
    num_trabalhador_op INTEGER REFERENCES operador(num_trabalhador),
    id_chegada INTEGER REFERENCES chegadas_diarias(id_chegada) ,
    data_hora TIMESTAMP NOT NULL DEFAULT now(),
    observacoes TEXT,
    origem_validacao origem_detecao NOT NULL,
    confianca_validada NUMERIC(5,4) CHECK (confianca_validada >= 0 AND confianca_validada <= 1)
);

-- Chegadas_Diarias
CREATE TABLE chegadas_diarias (
    id_chegada SERIAL PRIMARY KEY,
    id_cais INTEGER REFERENCES cais(id_cais),
    id_turno INTEGER REFERENCES turno(id_turno),
    matricula_camiao TEXT REFERENCES camiao(matricula),
    id_carga INTEGER REFERENCES carga(id_carga),
    data_prevista DATE,
    hora_prevista TIME,
    data_hora_chegada TIMESTAMP,
    observacoes TEXT,
    estado_descarga estado_descarga DEFAULT 'nao_iniciada', -- com triggers para atualizar
    estado_entrega estado_entrega DEFAULT 'em_caminho' -- com triggers para atualizar
);

-- Alerta
CREATE TABLE alerta (
    id_alerta SERIAL PRIMARY KEY,
    id_historico_ocorrencia INTEGER REFERENCES historico_ocorrencias(id_historico),
    id_carga INTEGER REFERENCES carga(id_carga),
    data_hora TIMESTAMP NOT NULL DEFAULT now(),
    tipo TEXT,
    severidade SMALLINT,
    comentario TEXT,
    descricao TEXT
);

-- Historico_Ocorrencias
CREATE TABLE historico_ocorrencias (
    id_historico SERIAL PRIMARY KEY,
    id_turno INTEGER REFERENCES turno(id_turno),
    hora_inicio TIMESTAMP,
    hora_fim TIMESTAMP,
    descricao TEXT
);

-- Criar indices, triggers, functions, indexs, views conforme necessário