# Especificação — Extração clínica GenAI

**Módulo:** `ir_alem_1_genai/`  
**Disclaimer:** *Este assistente não substitui atendimento médico. Em emergências, ligue 192 (SAMU).*  
**Dados:** exclusivamente sintéticos (`PAC-SYN-*`).

## 1. Problema

Prontuários e relatos de paciente chegam em texto livre. O ecossistema CardioIA já opera sinais estruturados (PA, FC e, na telemetria, BPM/temperatura). Este módulo completa o elo: **narrativa → JSON estrito**, para alimentar triagem, RPA e auditoria.

## 2. Contrato de saída

Validação **Pydantic v2** (`RegistroClinico`), com aliases de compatibilidade:

```json
{
  "paciente": { "identificador": "string", "idade": 0 },
  "historico_cardiovascular": "string",
  "sintomas_atuais": ["string"],
  "queixa_principal": "string",
  "sinais_vitais": {
    "pressao_sistolica": 0,
    "pressao_diastolica": 0,
    "frequencia_cardiaca": 0
  },
  "medicamentos_em_uso": [{ "nome": "string", "posologia": "string" }],
  "medicacoes_em_uso": [{ "nome": "string", "posologia": "string" }],
  "classificacao_risco": "BAIXO | MODERADO | ALTO | EMERGENCIA",
  "risco_estratificado": "BAIXO | MODERADO | ALTO | EMERGENCIA",
  "necessidade_encaminhamento": true,
  "conduta_sugerida": "string"
}
```

O campo opcional `spo2` é aceito no modelo interno para alinhar oximetria ao RPA; o JSON mínimo do contrato permanece válido.

## 3. Pipeline

```
texto
  ├─ (opcional) LLM OpenAI-compatible, few-shot + JSON mode
  │     └─ validate Pydantic → reclassificar risco local
  └─ heurística regex/NLP
        ├─ ID PAC-*, idade, PAS/PAD, FC, SpO2, medicamentos
        ├─ classify_risk() determinístico
        └─ conduta_sugerida()
```

O recálculo local do risco após o LLM impede que um modelo generativo **subestratifique** uma crise hipertensiva ou a tríade de alarme.

### 3.1 Few-shot

O *system prompt* descreve o schema, os limiares e o disclaimer. Um exemplo BAIXO (`PAC-DEMO-00`) ancora formato e unidades (mmHg, bpm, %).

### 3.2 Fallback heurístico

- PA: `PA 128/78`, `128/78 mmHg`, `sistólica … diastólica …`
- FC: `FC 72`, `72 bpm`, `frequência cardíaca 72`
- Negação: `sem sudorese`, `Nega irradiação…` não disparam red flags (janela lexical de prefixo)

Essa camada garante demo **offline** e *smoke test* determinístico.

## 4. Estratificação de risco (protótipo)

| Nível | Critério (demonstração) |
| --- | --- |
| **EMERGENCIA** | Irradiação **e** sudorese **e** dispneia; **ou** PAS ≥ 180; **ou** PAD ≥ 120; **ou** FC > 120 em repouso **com** sintoma isquêmico/dispneia; **ou** SpO2 < 90% |
| **ALTO** | Angina com um red flag; PAS ≥ 160 ou PAD ≥ 100; SpO2 < 94%; síncope |
| **MODERADO** | Dor atípica isolada; palpitação; PA 140–159 / 90–99 |
| **BAIXO** | Vitais estáveis e queixa não aguda |

Limiar de FC **> 120** e **< 50** replica a telemetria da Fase 3. PAS/PAD de crise seguem a faixa usada no worker RPA (compatível com discussão de emergência hipertensiva em materiais da SBC/AHA, **sem** pretender aplicar a diretriz completa).

## 5. Dataset de teste

`dataset_casos_teste.json` contém 10 narrativas (2 BAIXO, 2 MODERADO, 2 ALTO, 4 EMERGENCIA), com identificadores `PAC-SYN-001` … `PAC-SYN-010`. Nenhuma linha deriva de prontuário real.

O notebook `notebook_extracao.ipynb` executa o lote e uma extração pontual.

## 6. Integração

`backend/services/llm_extractor.py` reexporta `extract_to_dict` para `POST /api/extract`. Variáveis: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.

## 7. Limitações

- Regex não substitui um NER clínico (cTAKES, MedSpaCy) em produção.
- Posologia incompleta cai em `"não informada"`.
- Condutas são textos pedagógicos, não prescrição.
