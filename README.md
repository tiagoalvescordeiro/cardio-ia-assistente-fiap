# CardioIA Assistente

Assistente conversacional cardiológico com acolhimento psicossomático (IBM Watson Assistant ou motor local), extração estruturada de prontuário sintético (GenAI) e monitoramento RPA com persistência híbrida (SQL + NoSQL).

Herança de limiares clínicos: [tiagoalvescordeiro/cardio-ia-fase1](https://github.com/tiagoalvescordeiro/cardio-ia-fase1) (PA sistólica/diastólica, FC/BPM, SpO2).

> **Este assistente não substitui atendimento médico e não é dispositivo médico.**  
> Emergência cardíaca: **192 (SAMU)**. Crise emocional com ideação: **188 (CVV)**.  
> Pacientes de demonstração (`PAC-SYN-*`) são **sintéticos**. Não utilize dados reais.  
> Na dúvida diagnóstica, o atendimento presencial prevalece sobre hipótese de estresse.

**Repositório:** [tiagoalvescordeiro/cardio-ia-assistente-fiap](https://github.com/tiagoalvescordeiro/cardio-ia-assistente-fiap)  
**Runtime:** Python 3.10+ (validado em 3.12), Windows / macOS / Linux.

---

## Arquitetura de módulos

| Módulo | Pasta | Função |
| --- | --- | --- |
| API + orquestração | `backend/` | Flask REST, filtro de segurança, sessão Watson/local |
| Interface conversacional | `frontend/` | Widget HTML/CSS/JS (pt-BR), dark mode, 4-7-8, CTAs 192/188 |
| NLP conversacional (skill) | `watson/` | Skill IBM Watson Assistant exportado (`cardio_assistant_skill.json`) |
| Extração clínica GenAI | `ir_alem_1_genai/` | Narrativa → JSON (Pydantic; heurística ou LLM) |
| RPA + persistência híbrida | `ir_alem_2_rpa/` | Worker periódico, SQLite + auditoria NoSQL |
| Documentação técnica | `docs/` | Relatórios de arquitetura, fluxo, GenAI, RPA, viabilidade |
| Operação / smoke | `scripts/` | Smoke ECO, publicação do skill, utilitários |

```
backend/          API Flask + Watson + extração
frontend/         Widget de chat (pt-BR)
watson/           Skill IBM Watson Assistant (pt-BR)
ir_alem_1_genai/  Extração clínica (Pydantic + heurística/LLM)
ir_alem_2_rpa/    Worker RPA + schemas SQL/NoSQL
docs/             Especificações e relatórios técnicos
scripts/          Smoke, patch/publish do skill, tunnel, md→PDF
```

---

## Instalação

Na raiz do repositório:

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

Ambiente:

```powershell
copy .env.example .env
```

```bash
cp .env.example .env
```

Deixe `WATSON_API_KEY` e `OPENAI_API_KEY` vazios para demo offline (fallback local + heurística). Preencha apenas se for usar IBM Cloud ou LLM OpenAI-compatible.

---

## Execução (backend + frontend)

Com a venv ativa, na raiz:

```bash
python backend/app.py
```

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `FLASK_HOST` | `0.0.0.0` | Escuta em todas as interfaces (necessário para túnel / LAN) |
| `FLASK_PORT` | `5000` | Porta HTTP |
| `FLASK_DEBUG` | `false` | Debug Flask |
| `CORS_ORIGINS` | `*` | Origens CORS da API |

- Local: [http://127.0.0.1:5000](http://127.0.0.1:5000)  
- O Flask serve `frontend/` na raiz e a API em `/api/*`.

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

Chat (exemplo):

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:5000/api/chat -ContentType application/json -Body '{"message":"Olá, bom dia."}'
```

Smoke do módulo conversacional / ECO (sem servidor):

```bash
python scripts/smoke_eco.py
```

### Watson (opcional)

1. Importe `watson/cardio_assistant_skill.json` no Dialog do watsonx Assistant.  
2. Preencha no `.env`: `WATSON_API_KEY`, `WATSON_URL`, `WATSON_ASSISTANT_ID`, `WATSON_ENVIRONMENT_ID`, `WATSON_VERSION`.  
3. Reinicie o Flask. `GET /api/health` deve exibir `"watson_mode": "cloud"`. Sem chave/ID, permanece `fallback`.

---

## Extração clínica (GenAI)

```bash
python ir_alem_1_genai/clinical_extraction.py --dataset ir_alem_1_genai/dataset_casos_teste.json
```

Via API (Flask em execução):

```powershell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:5000/api/extract -ContentType application/json -Body '{"text":"PAC-SYN-007, 59 anos. Dor no peito irradiando para a mandíbula, sudorese fria e falta de ar. PA 148/92 mmHg, FC 110 bpm, SpO2 93%. AAS 100 mg 1x/dia."}'
```

---

## RPA híbrido

```bash
python ir_alem_2_rpa/rpa_monitor.py --reinit --once
```

Loop periódico:

```bash
python ir_alem_2_rpa/rpa_monitor.py --interval 15
```

Auditoria NoSQL (arquivo): `data/rpa_audit_store.json`. MongoDB opcional via `MONGO_URI`.

---

## Acesso externo para homologação (túnel)

Por padrão o serviço escuta em `0.0.0.0:5000`. A limitação de acesso externo não é o bind: é a ausência de IP público / NAT. Solução recomendada (gratuita, reversível): **Cloudflare Tunnel** (`cloudflared`) ou **ngrok**, expondo a porta `5000`.

### Opção A — Cloudflare Tunnel (preferencial)

1. Instale o [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) (Windows: binário em `tools/cloudflared.exe`, ou `winget install Cloudflare.cloudflared`).  
2. Suba o Flask (`python backend/app.py`).  
3. Em outro terminal, na raiz:

```powershell
.\scripts\start_tunnel.ps1
```

Ou com o binário portátil:

```powershell
.\tools\cloudflared.exe tunnel --url http://127.0.0.1:5000
```

Ou via PATH:

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

A URL pública `https://*.trycloudflare.com` aparece no terminal. Não exige conta paga para o modo quick tunnel.

### Opção B — ngrok

```powershell
ngrok http 5000
```

Use a URL `https://…` exibida. Plano gratuito é suficiente para homologação pontual.

**Segurança:** o túnel expõe o protótipo na internet. Não cole dados reais de pacientes. Encerre o processo do túnel ao terminar a homologação.

---

## Deploy no Render

O Flask já serve `frontend/` na raiz e a API em `/api/*`. Para homologação persistente, publique um **Web Service** no [Render](https://render.com) ligado a este repositório GitHub, branch `main`. Duas vias equivalentes:

1. **Blueprint:** New → Blueprint e aplique o `render.yaml` da raiz.  
2. **Manual:** New → Web Service, runtime Python, plano Free.

| | Comando |
| --- | --- |
| Build | `pip install -r backend/requirements.txt` |
| Start | `gunicorn --chdir backend -b 0.0.0.0:$PORT app:app` |
| Health check | `GET /api/health` |

O `Procfile` da raiz usa o mesmo start (útil se o Render detectar o processo automaticamente). `gunicorn` já está em `backend/requirements.txt`.

Variáveis (dashboard do Render; **nunca** commitar `.env`):

| Variável | Valor | Notas |
| --- | --- | --- |
| `FLASK_DEBUG` | `false` | Debug desligado em produção |
| `CORS_ORIGINS` | `*` | Origens CORS da API |
| `PYTHON_VERSION` | `3.12.8` | Runtime Python no Render |
| `WATSON_VERSION` | `2024-08-25` | API Watson Assistant v2 |
| `WATSON_API_KEY`, `WATSON_URL`, `WATSON_ASSISTANT_ID`, `WATSON_ENVIRONMENT_ID` | secrets (`sync: false`) | Opcionais. Sem chave/ID o health fica `"watson_mode": "fallback"` |
| `OPENAI_API_KEY` | secret (`sync: false`) | Opcional. Sem chave a extração usa heurística |

No Blueprint, os secrets são pedidos no dashboard na criação — não há valores reais no repositório.

**Plano Free:** o serviço dorme após inatividade. A primeira requisição após o sono pode levar dezenas de segundos (cold start); o health check `/api/health` confirma quando o processo voltou.

Após o deploy, valide a UI como no [checklist local](#execução-backend--frontend) / [túnel](#acesso-externo-para-homologação-túnel): abra `https://….onrender.com`, confirme `GET /api/health` (`status: ok`) e envie uma mensagem no widget (ex.: «Olá, bom dia.»). Sem dados reais de pacientes.

---

## Documentação

| Arquivo | Conteúdo |
| --- | --- |
| [docs/relatorio_conversacional.md](docs/relatorio_conversacional.md) | Especificação do módulo NLP conversacional |
| [docs/relatorio_tecnico_fiap.md](docs/relatorio_tecnico_fiap.md) | Visão técnica consolidada |
| [docs/relatorio_genai.md](docs/relatorio_genai.md) | Extração clínica GenAI |
| [docs/relatorio_genai.pdf](docs/relatorio_genai.pdf) | PDF do módulo GenAI |
| [docs/relatorio_rpa_hibrido.md](docs/relatorio_rpa_hibrido.md) | RPA e persistência híbrida |
| [docs/relatorio_viabilidade_eco.md](docs/relatorio_viabilidade_eco.md) | Viabilidade técnica, ética e UX |
| [docs/tabela_conformidade_eco.md](docs/tabela_conformidade_eco.md) | Matriz de conformidade funcional |
| [docs/roteiro_video_pitch.md](docs/roteiro_video_pitch.md) | Roteiro de demonstração em vídeo |

Regenerar PDF GenAI:

```powershell
python scripts\md_to_pdf_genai.py
```

---

## API

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

## Grupo 54 — CardioIA Fase 5

| Nome | RM |
| --- | --- |
| Tiago Alves Cordeiro | 561791 |
| Matheus Parra | 561907 |
| Otávio Custódio de Oliveira | 565606 |
| Leandro Arthur Marinho Ferreira | 565240 |

---

## Licença e ética

Protótipo acadêmico (FIAP). Sem uso clínico. Sem dados pessoais reais.
