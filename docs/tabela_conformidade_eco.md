# Matriz de conformidade — CardioIA + ECO

Status: **Conforme** | **Parcialmente conforme** | **Não conforme**  
Evidência aponta para código no repositório.

| # | Requisito | Status | Evidência |
| --- | --- | --- | --- |
| 1 | Flask REST, `.env`, ciclo de sessão Watson v2, degradação em erro de conexão | **Conforme** | `backend/app.py` (`/api/chat`, `/api/message`, `/api/session`, `/api/health`); `backend/config.py` + `.env.example`; `WatsonService.create_session` / `delete_session` / `message` com `environment_id`; falha IBM → motor local; 500 de chat devolve 192/188 |
| 2 | Skill Watson exportável com intents, entidades e nós condicionais | **Conforme** | `watson/cardio_assistant_skill.json`: intents e aliases (`#sintoma_cardiaco`, `#red_flags`, `#estresse_ansiedade`, `#solicitar_respiracao`, `#ideacao_risco`); `@sinais_alerta` / `@sintomas_somaticos`; fork 192 vs 4-7-8 |
| 3 | UI fala com Flask; Calm UI / Dark Mode; disclaimer de não diagnóstico | **Conforme** | `frontend/script.js` → `POST /api/chat`; `index.html` + `styles.css` (`data-theme="dark"`); aviso legal permanente (não diagnostica / não é dispositivo médico) |
| 4 | Red flags cardíacos **antes** de hipótese psicossomática | **Conforme** | `LocalRuleEngine._start_eco` / `_start_duvida_infarto`: alarme ou incerteza → SAMU; `#duvida_infarto` nunca tranquiliza; conflito ansiedade+irradiação+suor → cardíaco em `safety_filter.py` |
| 5 | Acolhimento + psicoeducação autonômica (luta-ou-fuga compartilhada) | **Conforme** | `REPLY_ECO_SCREEN` em `watson_service.py` e nós ECO do skill |
| 6 | 4-7-8 com timer visual + rede CVV / ABRATA / CAPS | **Conforme** | Círculo/fase 4-7-8 em `frontend/`; `REPLY_ECO_478` e rodapé/painel com CVV 188, ABRATA e CAPS |
| 7 | Interceptor de crise 188 **e** 192, sem Watson | **Conforme** | `evaluate_safety` em `safety_filter.py`; `app.py` não chama Watson; payload e modal 188+192 |
| 8 | Pulso k-anônimo + heatmap sintético (sem GPS/PII) | **Conforme** | `backend/services/eco_social.py`, `GET /api/eco-pulse`, painel `#eco-social` no frontend; k≥10; `geo_collected: false` |
| 9 | Bind adequado a túnel / LAN (`0.0.0.0:5000`) | **Conforme** | `FLASK_HOST` / `FLASK_PORT` em `config.py` e `.env.example`; seção de túnel no README |

Nenhum item permanece **Não conforme** ou **Parcialmente conforme** nesta auditoria.
