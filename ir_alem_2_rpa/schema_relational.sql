-- =============================================================================
-- CardioIA Assistente — schema relacional (SQLite / PostgreSQL-friendly)
-- Herança da Fase 1/3: PA Sistólica, PA Diastólica, FC (BPM) e SpO2.
-- Todos os registros abaixo são SINTÉTICOS. Não há dado real de paciente.
-- =============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identificador TEXT NOT NULL UNIQUE,
    nome_sintetico TEXT NOT NULL,
    idade INTEGER NOT NULL CHECK (idade BETWEEN 0 AND 120),
    sexo TEXT CHECK (sexo IN ('F', 'M', 'O', 'NI')),
    observacao TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leituras_sinais_vitais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    -- Alinhado ao Heart Failure (RestingBP) da Fase 1, desdobrado em PAS/PAD.
    pressao_sistolica REAL NOT NULL CHECK (pressao_sistolica BETWEEN 50 AND 300),
    pressao_diastolica REAL NOT NULL CHECK (pressao_diastolica BETWEEN 30 AND 200),
    -- FC / BPM — mesmo limiar da Fase 3 Ir Além 1 (alerta se > 120).
    frequencia_cardiaca REAL NOT NULL CHECK (frequencia_cardiaca BETWEEN 20 AND 250),
    -- SpO2 herdada do protocolo de telemetria CardioIA (Fase 5).
    spo2 REAL CHECK (spo2 IS NULL OR (spo2 BETWEEN 40 AND 100)),
    -- Temperatura opcional (DHT22 da Fase 3).
    temperatura REAL CHECK (temperatura IS NULL OR (temperatura BETWEEN 30 AND 45)),
    coletado_em TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'sintetico',
    processado INTEGER NOT NULL DEFAULT 0 CHECK (processado IN (0, 1)),
    processado_em TEXT,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
);

CREATE TABLE IF NOT EXISTS alertas_emitidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leitura_id INTEGER NOT NULL,
    paciente_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    severidade TEXT NOT NULL CHECK (severidade IN ('INFO', 'ATENCAO', 'CRITICO', 'EMERGENCIA')),
    mensagem TEXT NOT NULL,
    limiar_aplicado TEXT,
    emitido_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (leitura_id) REFERENCES leituras_sinais_vitais(id),
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
);

CREATE INDEX IF NOT EXISTS idx_leituras_nao_processadas
    ON leituras_sinais_vitais (processado, coletado_em);

CREATE INDEX IF NOT EXISTS idx_leituras_paciente
    ON leituras_sinais_vitais (paciente_id, coletado_em);

CREATE INDEX IF NOT EXISTS idx_alertas_paciente
    ON alertas_emitidos (paciente_id, emitido_em);

CREATE INDEX IF NOT EXISTS idx_pacientes_identificador
    ON pacientes (identificador);

CREATE TABLE IF NOT EXISTS adesao_medicamentosa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id INTEGER NOT NULL,
    medicamento TEXT NOT NULL,
    doses_esperadas_7d INTEGER NOT NULL CHECK (doses_esperadas_7d > 0),
    doses_registradas_7d INTEGER NOT NULL CHECK (doses_registradas_7d >= 0),
    coletado_em TEXT NOT NULL,
    processado INTEGER NOT NULL DEFAULT 0 CHECK (processado IN (0, 1)),
    processado_em TEXT,
    FOREIGN KEY (paciente_id) REFERENCES pacientes(id)
);

CREATE INDEX IF NOT EXISTS idx_adesao_nao_processada
    ON adesao_medicamentosa (processado, coletado_em);

-- -----------------------------------------------------------------------------
-- Carga sintético-didática
-- -----------------------------------------------------------------------------
INSERT INTO pacientes (identificador, nome_sintetico, idade, sexo, observacao) VALUES
    ('PAC-SYN-101', 'Paciente Sintetico Alfa', 58, 'M', 'Perfil estável — demo'),
    ('PAC-SYN-102', 'Paciente Sintetico Beta', 67, 'F', 'Crise hipertensiva sistólica'),
    ('PAC-SYN-103', 'Paciente Sintetico Gama', 71, 'M', 'PAD em faixa de emergência'),
    ('PAC-SYN-104', 'Paciente Sintetico Delta', 49, 'F', 'Taquicardia em repouso (Fase 3)'),
    ('PAC-SYN-105', 'Paciente Sintetico Epsilon', 80, 'M', 'Hipoxemia (SpO2)'),
    ('PAC-SYN-106', 'Paciente Sintetico Zeta', 63, 'F', 'Bradicardia sintomática');

INSERT INTO leituras_sinais_vitais (
    paciente_id, pressao_sistolica, pressao_diastolica, frequencia_cardiaca,
    spo2, temperatura, coletado_em, origem, processado
) VALUES
    (1, 128, 78, 72, 98, 36.5, datetime('now', '-2 hours'), 'sintetico', 0),
    (2, 188, 96, 90, 97, 36.7, datetime('now', '-90 minutes'), 'sintetico', 0),
    (3, 156, 124, 88, 96, 36.4, datetime('now', '-70 minutes'), 'sintetico', 0),
    (4, 142, 88, 128, 95, 36.8, datetime('now', '-40 minutes'), 'sintetico', 0),
    (5, 118, 70, 108, 87, 36.2, datetime('now', '-25 minutes'), 'sintetico', 0),
    (6, 110, 68, 44, 97, 35.9, datetime('now', '-10 minutes'), 'sintetico', 0);

INSERT INTO adesao_medicamentosa (
    paciente_id, medicamento, doses_esperadas_7d, doses_registradas_7d, coletado_em, processado
) VALUES
    (1, 'losartana 50 mg', 7, 7, datetime('now', '-1 hours'), 0),
    (4, 'atenolol 25 mg', 7, 3, datetime('now', '-50 minutes'), 0);
