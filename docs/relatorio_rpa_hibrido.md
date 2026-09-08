# Relatório técnico — Ir Além 2: RPA e persistência híbrida

**Módulo:** `ir_alem_2_rpa/`  
**Disclaimer:** *Este assistente não substitui atendimento médico. Em emergências, ligue 192 (SAMU).*  
**Dados:** sintéticos (`PAC-SYN-101` … `PAC-SYN-106`).

## 1. Motivação

A Fase 3 do CardioIA já demonstrou telemetria (MQTT) e um microciclo REST + “RPA de e-mail” sobre BPM e temperatura. A Fase 5 separa com clareza dois tipos de dado:

- o que é **medida repetível** (sinais vitais, alerta tipado) permanece **relacional** (SQL);
- o que é **rastro de execução** (payload textual, metadados do worker) vai para **NoSQL**.

A divisão espelha práticas de *clinical data warehouses* e de trilhas de auditoria (LGPD: minimizar identificadores no log; aqui já fictícios).

## 2. Modelo relacional

Arquivo: `schema_relational.sql` (SQLite; tipos aceitos pelo PostgreSQL com ajustes mínimos de `AUTOINCREMENT`/`datetime`).

| Tabela | Conteúdo |
| --- | --- |
| `pacientes` | Identificador sintético, idade, sexo |
| `leituras_sinais_vitais` | **PA sistólica**, **PA diastólica**, **FC**, **SpO2**, temperatura opcional (DHT22 Fase 3), flag `processado` |
| `alertas_emitidos` | Tipo, severidade, mensagem, limiar aplicado, FK para leitura |
| `adesao_medicamentosa` | Doses esperadas vs. registradas em 7 dias (protótipo de adesão) |

Índices: leituras não processadas, série por paciente, alertas por paciente.

A desagregação PAS/PAD corrige a limitação do Heart Failure Prediction (Fase 1), que oferece um único `RestingBP`. A FC continua o sucessor direto do BPM da Fase 3.

## 3. Modelo NoSQL

Arquivo: `schema_nosql.json`, coleção `rpa_audit_logs`.

Documentos de exemplo cobrem `WORKER_START`, `ANOMALY_DETECTED` e `ALERT_WRITTEN`. Campos: `run_id`, `timestamp` ISO-8601, `event_type`, `payload_textual`, `metadata`.

**Runtime padrão:** arquivo JSON em `data/rpa_audit_store.json` (sem Docker).  
**Override:** `MONGO_URI` + `MONGO_DB` + `MONGO_COLLECTION`.

## 4. Worker (`rpa_monitor.py`)

Ciclo:

1. `FETCH_UNPROCESSED` — `SELECT` com `processado = 0`
2. Heurística de anomalia
3. `INSERT` em `alertas_emitidos` se houver achado
4. Marca a leitura `processado = 1`
5. Append no store NoSQL
6. Adesão medicamentosa < 80% em 7 dias → alerta `BAIXA_ADESAO` (timestamp no SQL e no NoSQL)

**Limiares**

| Sinal | Condição | Severidade |
| --- | --- | --- |
| PAS | ≥ 180 mmHg | EMERGENCIA |
| PAD | ≥ 120 mmHg | EMERGENCIA |
| FC | > 120 bpm | CRITICO (Fase 3) |
| FC | < 50 bpm | CRITICO (Fase 3) |
| SpO2 | < 90% | EMERGENCIA |
| SpO2 | < 94% | ATENCAO |
| Temperatura | ≥ 38,0 °C | ATENCAO (Fase 3) |
| Adesão 7d | < 80% das doses | ATENCAO |

**CLI**

```text
python rpa_monitor.py --once          # smoke test
python rpa_monitor.py --interval 15   # loop
python rpa_monitor.py --init-only
python rpa_monitor.py --reinit --once # recria carga sintético
```

SQLite em `DATABASE_URL` / `RPA_SQLITE_PATH` (padrão `data/cardioia.db`). PostgreSQL pode ser apontado no `.env` futuro via `DATABASE_URL`; o worker desta entrega usa SQLite para garantir demo sem container.

## 5. Carga de demonstração

Seis pacientes e seis leituras: um perfil estável, crise sistólica, crise diastólica, taquicardia, hipoxemia e bradicardia. Um único `--once` deve emitir **cinco** grupos de alerta (o registro Alfa permanece estável).

## 6. Governança

- Não há PHI. Nomes do tipo «Paciente Sintetico Alfa».
- O log NoSQL replica o disclaimer em `metadata`.
- Reprocessar o banco usa `--reinit` (drop explícito das três tabelas).

## 7. Relação com o assistente conversacional

Os mesmos limiares de PA e FC aparecem no motor de diálogo (`pressao_arterial`) e no classificador GenAI. A consistência entre canais é requisito de segurança do protótipo: 180 mmHg não pode ser «normal» no chat e «emergência» no RPA.
