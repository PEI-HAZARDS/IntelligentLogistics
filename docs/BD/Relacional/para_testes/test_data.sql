-- ==========================
-- Trabalhadores
-- ==========================
INSERT INTO trabalhador_porto (nome, email, password_hash)
VALUES
('João Silva', 'joao.silva@porto.com', 'hash1'),
('Maria Santos', 'maria.santos@porto.com', 'hash2'),
('Carlos Oliveira', 'carlos.oliveira@porto.com', 'hash3'),
('Ana Costa', 'ana.costa@porto.com', 'hash4');

-- Gestores
INSERT INTO gestor (num_trabalhador, nivel_acesso)
VALUES
(1, 'admin'),
(2, 'default');

-- Operadores
INSERT INTO operador (num_trabalhador)
VALUES (3), (4);

-- ==========================
-- Empresas
-- ==========================
INSERT INTO empresa (nome, nif, contacto, descricao)
VALUES
('Translog S.A.', '123456789', '211000111', 'Transportes gerais'),
('FrioPorto Lda', '987654321', '211000222', 'Transportes refrigerados');

-- ==========================
-- Condutores
-- ==========================
INSERT INTO condutor (num_carta_cond, id_empresa, nome, contacto)
VALUES
('C12345', 1, 'Luis Ferreira', '910000001'),
('C54321', 2, 'Pedro Ramos', '910000002');

-- ==========================
-- Camiões
-- ==========================
INSERT INTO camiao (matricula, marca)
VALUES
('ABC1234', 'Mercedes'),
('XYZ5678', 'Volvo');

-- ==========================
-- Conduções
-- ==========================
INSERT INTO conduz (matricula_camiao, num_carta_cond, inicio, fim)
VALUES
('ABC1234', 'C12345', '2025-11-20 08:00', '2025-11-20 16:00'),
('XYZ5678', 'C54321', '2025-11-20 09:00', '2025-11-20 18:00');

-- ==========================
-- Cargas
-- ==========================
INSERT INTO carga (peso, descricao, adr, tipo_carga, estado_fisico)
VALUES
(1000.00, 'Carga geral de alimentos', FALSE, 'geral', 'sólido'),
(500.00, 'Produtos químicos inflamáveis', TRUE, 'perigosa', 'líquido'),
(2000.00, 'Carne congelada', FALSE, 'refrigerada', 'sólido'),
(50.00, 'Animais vivos', FALSE, 'viva', 'hibrido');

-- ==========================
-- Cais
-- ==========================
INSERT INTO cais (estado, capacidade_max, localizacao_gps)
VALUES
('operacional', 5, ST_GeogFromText('POINT(-8.611 41.145)')),
('manutenção', 3, ST_GeogFromText('POINT(-8.612 41.146)'));

-- ==========================
-- Turnos
-- ==========================
INSERT INTO turno (num_operador_cancela, num_gestor_responsavel, hora_inicio, hora_fim, descricao)
VALUES
(3, 1, '08:00', '16:00', 'Turno manhã'),
(4, 2, '16:00', '00:00', 'Turno tarde');

-- ==========================
-- Chegadas diárias
-- ==========================
INSERT INTO chegadas_diarias
(id_cais, id_turno, matricula_camiao, id_carga, data_prevista, hora_prevista, estado_descarga, estado_entrega)
VALUES
(1, 1, 'ABC1234', 1, '2025-11-21', '09:00', 'nao_iniciada', 'em_caminho'),
(1, 1, 'XYZ5678', 2, '2025-11-21', '10:00', 'nao_iniciada', 'em_caminho'),
(2, 2, 'ABC1234', 3, '2025-11-22', '08:00', 'nao_iniciada', 'em_caminho'),
(2, 2, 'XYZ5678', 4, '2025-11-22', '11:00', 'nao_iniciada', 'em_caminho');

-- ==========================
-- Deteções válidas (exemplo)
-- ==========================
INSERT INTO deteccao_valida (num_trabalhador_op, id_chegada, data_hora, observacoes, URL, confianca_validada)
VALUES
(3, 1, '2025-11-21 09:05', 'Deteção manual', 'https://storage.exemplo.com/crops/abc1234_1.jpg', 0.95),
(4, 2, '2025-11-21 10:10', 'Deteção manual', 'https://storage.exemplo.com/crops/xyz5678_1.jpg', 0.90);

-- ==========================
-- Histórico de ocorrências
-- ==========================
INSERT INTO historico_ocorrencias (id_turno, hora_inicio, hora_fim, descricao)
VALUES
(1, '2025-11-21 08:00', '2025-11-21 12:00', 'Inspeção cargas perigosas'),
(2, '2025-11-21 16:00', '2025-11-21 20:00', 'Operação descarga frigoríficos');

-- ==========================
-- Alertas
-- ==========================
INSERT INTO alerta (id_historico_ocorrencia, id_carga, data_hora, tipo, severidade, descricao)
VALUES
(1, 2, '2025-11-21 10:15', 'ADR', 5, 'Carga com produtos químicos inflamáveis detectada'),
(2, 3, '2025-11-21 17:00', 'geral', 3, 'Atraso na descarga de carga refrigerada');

