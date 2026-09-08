# CardioIA Assistente — Fase 5 (CardioIA + ECO)

Assistente conversacional cardiológico e de acolhimento psicossomático (IBM Watson Assistant ou fallback local), com extração de prontuário sintético por IA generativa e RPA com persistência híbrida (SQL + NoSQL).

Herança de modelos e limiares: [tiagoalvescordeiro/cardio-ia-fase1](https://github.com/tiagoalvescordeiro/cardio-ia-fase1) (PA sistólica/diastólica, FC/BPM, SpO2).

> **Este assistente não substitui atendimento médico e não é dispositivo médico.**  
> Emergência cardíaca: **192 (SAMU)**. Crise emocional com ideação: **188 (CVV)**.  
> Todos os pacientes (`PAC-SYN-*`) são **sintéticos**. Não utilize dados reais.  
> Na dúvida diagnóstica, o atendimento presencial sempre prevalece sobre hipótese de estresse.

Requisitos: **Python 3.10+** (testado em 3.12), Windows/macOS/Linux.

---

## Mapa entrega FIAP ↔ pastas

| Entrega do enunciado | Onde está no repo | Evidência rápida |
| --- | --- | --- |
| **Parte 1** — backend Python + skill Watson + relatório do fluxo (1–2 pág.) | `backend/`, `watson/cardio_assistant_skill.json`, `docs/relatorio_conversacional.md` (+ `docs/relatorio_tecnico_fiap.md`) | `python backend/app.py` → `GET /api/health` |
| **Parte 2** — UI HTML + GitHub público + vídeo ≤3 min | `frontend/` · repo público · `docs/roteiro_video_pitch.md` | Abrir http://127.0.0.1:5000 (vídeo é **manual**) |
| **Ir Além 1** — GenAI → JSON estruturado + **PDF** do fluxo | `ir_alem_1_genai/` · `docs/relatorio_genai.md` · **`docs/relatorio_genai.pdf`** | `python ir_alem_1_genai/clinical_extraction.py --dataset …` |
| **Ir Além 2** — RPA periódico + NoSQL + anomalia + relatório + schemas | `ir_alem_2_rpa/` · `docs/relatorio_rpa_hibrido.md` | `python ir_alem_2_rpa/rpa_monitor.py --reinit --once` |
| **Extra +1** — equipe 4–5 | Seção 7 (abaixo) | Nomes reais do grupo 54; registre no portal FIAP |

```
backend/                 API Flask + Watson + extração
frontend/                 Widget de chat (pt-BR)
watson/                   Skill IBM Watson Assistant (pt-BR)
ir_alem_1_genai/          Extração clínica (Pydantic + heurística/LLM) + notebook
ir_alem_2_rpa/            Worker RPA + schemas SQL/NoSQL
docs/                     Relatórios (MD + PDF GenAI), roteiro de vídeo
scripts/                  Patch/publish do skill, smoke ECO, md→PDF
```

---

## 1. Instalação (uma vez)

No diretório raiz deste repositório:

```bash
python -m venv .venv
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install -r ir_alem_2_rpa\requirements_rpa.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r ir_alem_2_rpa/requirements_rpa.txt
```

Copie o ambiente:

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

Deixe `WATSON_API_KEY` e `OPENAI_API_KEY` vazios para a demo offline. Preencha apenas se for usar IBM Cloud ou um LLM OpenAI-compatible.

Jupyter (opcional, só para o notebook):

```bash
pip install notebook
```

---

## 2. Backend + frontend (comando único)

Na raiz, com a venv ativa:

```bash
python backend/app.py
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000). O Flask serve `frontend/index.html` e a API.

Verificação rápida:

```bash
curl http://127.0.0.1:5000/api/health
```

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

Chat (exemplo):

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:5000/api/chat -ContentType application/json -Body '{"message":"Olá, bom dia."}'
```

Se abrir `frontend/index.html` direto no disco (`file://`), o script aponta para `http://127.0.0.1:5000`. Prefira a URL do Flask.

### Watson (opcional)

1. Importe `watson/cardio_assistant_skill.json` no Dialog do watsonx Assistant (tipo de entidade `patterns`; `next_step.behavior` = `get_user_input`).  
2. Preencha no `.env`: `WATSON_API_KEY`, `WATSON_URL`, `WATSON_ASSISTANT_ID`, `WATSON_ENVIRONMENT_ID`, `WATSON_VERSION`.  
3. `WATSON_ENVIRONMENT_ID` (draft ou live) é o ID usado em session/message no Assistant v2 atual.  
4. Reinicie o Flask. `GET /api/health` deve mostrar `"watson_mode": "cloud"`. Sem chave/ID, o modo permanece `fallback` (regra local).

---

## 3. Ir Além 1 — extração clínica

```bash
python ir_alem_1_genai/clinical_extraction.py --dataset ir_alem_1_genai/dataset_casos_teste.json
```

Um caso avulso:

```bash
python ir_alem_1_genai/clinical_extraction.py --text "PAC-SYN-001, 45 anos. PA 118/76 mmHg, FC 68 bpm, SpO2 99%. Cansaço leve após treino."
```

Via API (Flask ligado):

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:5000/api/extract -ContentType application/json -Body '{"text":"PAC-SYN-007, 59 anos. Dor no peito irradiando para a mandíbula, sudorese fria e falta de ar. PA 148/92 mmHg, FC 110 bpm, SpO2 93%. AAS 100 mg 1x/dia."}'
```

Notebook:

```bash
jupyter notebook ir_alem_1_genai/notebook_extracao.ipynb
```

Execute as células em ordem (o dataset é resolvido tanto a partir de `ir_alem_1_genai/` quanto da raiz).

---

## 4. Ir Além 2 — RPA híbrido

Inicializa SQLite (`data/cardioia.db`) a partir de `ir_alem_2_rpa/schema_relational.sql` e processa um ciclo:

```bash
python ir_alem_2_rpa/rpa_monitor.py --reinit --once
```

Loop periódico (intervalo em segundos, padrão 15):

```bash
python ir_alem_2_rpa/rpa_monitor.py --interval 15
```

Só schema/carga, sem processar:

```bash
python ir_alem_2_rpa/rpa_monitor.py --init-only
```

Conferência SQL (após `--once`):

```bash
python -c "import sqlite3; c=sqlite3.connect('data/cardioia.db'); print(c.execute('select tipo, severidade, mensagem from alertas_emitidos').fetchall())"
```

Auditoria NoSQL (arquivo): `data/rpa_audit_store.json`. Para MongoDB, defina `MONGO_URI` no `.env`.

---

## 5. Documentação

| Arquivo | Conteúdo |
| --- | --- |
| [docs/tabela_conformidade_eco.md](docs/tabela_conformidade_eco.md) | Auditoria Conforme / Parcial / Não conforme |
| [docs/relatorio_viabilidade_eco.md](docs/relatorio_viabilidade_eco.md) | Viabilidade técnica, ética, UX e rubrica FIAP |
| [docs/relatorio_tecnico_fiap.md](docs/relatorio_tecnico_fiap.md) | Relatório técnico curto (Parte 1) |
| [docs/relatorio_conversacional.md](docs/relatorio_conversacional.md) | Fluxo conversacional (Parte 1) |
| [docs/relatorio_genai.md](docs/relatorio_genai.md) | Ir Além 1 — fonte em Markdown |
| [docs/relatorio_genai.pdf](docs/relatorio_genai.pdf) | **Ir Além 1 — PDF exigido pelo enunciado** |
| [docs/relatorio_rpa_hibrido.md](docs/relatorio_rpa_hibrido.md) | Ir Além 2 — RPA SQL/NoSQL |
| [docs/roteiro_video_pitch.md](docs/roteiro_video_pitch.md) | Roteiro do vídeo ≤3 min (gravação manual) |

Regenerar o PDF GenAI (se o `.md` mudar):

```powershell
python scripts\md_to_pdf_genai.py
```

---

## 6. API (resumo)

| Método | Rota | Corpo |
| --- | --- | --- |
| GET | `/api/health` | — |
| GET | `/api/eco-pulse` | — (agregados sintéticos, sem GPS) |
| POST | `/api/chat` | `{"message":"...", "session_id": "..."}` |
| POST | `/api/extract` | `{"text":"..."}` |
| POST | `/api/message` | alias de `/api/chat` |
| POST | `/api/session` | — |
| DELETE | `/api/session/<id>` | — |

---

## 7. Equipe — pontuação extra (+1,0)

**Grupo 54 — CardioIA Fase 5.** Os quatro integrantes abaixo constituem a equipe acadêmica oficial do projeto. A autoria no GitHub reflete o usuário que realiza os *pushes* no repositório; a composição do grupo para fins de avaliação é a registrada nesta seção e no portal FIAP.

| Nome | RM |
| --- | --- |
| Tiago Alves Cordeiro | 561791 |
| Matheus Parra | 561907 |
| Otávio Custódio de Oliveira | 565606 |
| Leandro Arthur Marinho Ferreira | 565240 |

---

## Licença e ética

Trabalho de disciplina (FIAP, turma 1TIAO). Sem uso clínico. Sem dados pessoais reais.
