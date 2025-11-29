-- Criar a base
CREATE DATABASE porto_logistica;

-- Mudar para a base
\c porto_logistica;

-- ==========================
-- Habilitar extensão PostGIS para suporte geoespacial
-- ==========================
CREATE EXTENSION postgis;

-- ==========================
-- ENUMS
-- ==========================
CREATE TYPE estado_entrega AS ENUM ('em_transito', 'atrasada', 'em_descarga', 'concluida');
CREATE TYPE estado_descarga AS ENUM ('pendente', 'em_progresso', 'concluida');
CREATE TYPE tipo_carga AS ENUM ('geral', 'perigosa', 'refrigerada', 'viva');
CREATE TYPE estado_fisico AS ENUM ('liquido', 'solido', 'gasoso', 'hibrido');
CREATE TYPE nivel_acesso AS ENUM ('admin', 'bascic');
CREATE TYPE estado_cais AS ENUM ('manutencao', 'operacional', 'fechado');

-- ==========================
-- Trabalhadores
-- ==========================
CREATE TABLE trabalhador_porto (
    num_trabalhador SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT
);

CREATE TABLE gestor (
    num_trabalhador INTEGER PRIMARY KEY REFERENCES trabalhador_porto(num_trabalhador) ON DELETE CASCADE,
    nivel_acesso nivel_acesso DEFAULT 'bascic'
);

CREATE TABLE operador (
    num_trabalhador INTEGER PRIMARY KEY REFERENCES trabalhador_porto(num_trabalhador) ON DELETE CASCADE
);

-- ==========================
-- Empresa
-- ==========================
CREATE TABLE empresa (
    id_empresa SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    nif TEXT UNIQUE,
    contacto TEXT,
    descricao TEXT
);

-- ==========================
-- Condutor
-- ==========================
CREATE TABLE condutor (
    num_carta_cond TEXT PRIMARY KEY,
    id_empresa INTEGER REFERENCES empresa(id_empresa),
    nome TEXT NOT NULL,
    contacto TEXT
);

-- ==========================
-- Pesados (veiculos de transporte de carga
-- ==========================
CREATE TABLE veiculo_pesado (
    matricula TEXT PRIMARY KEY,
    marca TEXT
);

-- Histórico de condução
CREATE TABLE conduz (
    matricula_veiculo TEXT REFERENCES veiculo_pesado(matricula) ON DELETE CASCADE,
    num_carta_cond TEXT REFERENCES condutor(num_carta_cond) ON DELETE CASCADE,
    inicio TIMESTAMP NOT NULL,
    fim TIMESTAMP,
    PRIMARY KEY (matricula_veiculo, num_carta_cond, inicio)
);

-- ==========================
-- Carga
-- ==========================
CREATE TABLE carga (
    id_carga SERIAL PRIMARY KEY,
    peso DECIMAL(10,2) CHECK (peso > 0),
    descricao TEXT,
    adr BOOLEAN DEFAULT FALSE,
    tipo_carga tipo_carga NOT NULL,
    estado_fisico estado_fisico NOT NULL,
    unidade_medida VARCHAR(10) DEFAULT 'Kg'
);

-- ==========================
-- Cais
-- ==========================
CREATE TABLE cais (
    id_cais SERIAL PRIMARY KEY,
    estado estado_cais DEFAULT 'operacional',
    capacidade_max INTEGER,
    localizacao_gps GEOGRAPHY(POINT, 4326) -- garante que a localização é armazenada como um ponto geoespacial (latitude, longitude) -> WGS84
);

-- ==========================
-- Turno
-- ==========================
CREATE TABLE turno (
    id_turno SERIAL PRIMARY KEY,
    num_operador_cancela INTEGER REFERENCES operador(num_trabalhador),
    num_gestor_responsavel INTEGER REFERENCES gestor(num_trabalhador),
    id_gate INTEGER REFERENCES gate(id_gate),
    hora_inicio TIME,
    hora_fim TIME,
    descricao TEXT
);

-- ==========================
-- Chegadas Diárias
-- ==========================
CREATE TABLE chegadas_diarias (
    id_chegada SERIAL PRIMARY KEY,
    id_gate_entrada INTEGER REFERENCES gate(id_gate),
    id_cais INTEGER REFERENCES cais(id_cais),
    id_turno INTEGER REFERENCES turno(id_turno),
    matricula_pesado TEXT REFERENCES veiculo_pesado(matricula),
    id_carga INTEGER REFERENCES carga(id_carga),
    data_prevista DATE,
    hora_prevista TIME,
    data_hora_chegada TIMESTAMP,
    observacoes TEXT,
    estado_descarga estado_descarga DEFAULT 'nao_iniciada',
    estado_entrega estado_entrega DEFAULT 'em_caminho'
);

-- ==========================
-- Histórico Ocorrências
-- ==========================
CREATE TABLE historico_ocorrencias (
    id_historico SERIAL PRIMARY KEY,
    id_turno INTEGER REFERENCES turno(id_turno),
    hora_inicio TIMESTAMP,
    hora_fim TIMESTAMP,
    descricao TEXT
);

-- ==========================
-- Alertas
-- ==========================
CREATE TABLE alerta (
    id_alerta SERIAL PRIMARY KEY,
    id_historico_ocorrencia INTEGER REFERENCES historico_ocorrencias(id_historico),
    id_carga INTEGER REFERENCES carga(id_carga),
    data_hora TIMESTAMP NOT NULL DEFAULT now(),
    tipo TEXT,
    severidade SMALLINT,
    descricao TEXT
);

-- ==========================
-- Gates
-- ==========================
CREATE TABLE gate (
    id_gate SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT CHECK (tipo IN ('entrada', 'saida', 'ambos')),
    estado TEXT CHECK (estado IN ('operacional', 'avariado', 'manutencao')) DEFAULT 'operacional',
    localizacao_gps GEOGRAPHY(POINT, 4326),
    descricao TEXT
);
