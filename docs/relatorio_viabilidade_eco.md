# Relatório de viabilidade — CardioIA + ECO

**Projeto:** CardioIA Assistente  
**Repositório:** [tiagoalvescordeiro/cardio-ia-assistente](https://github.com/tiagoalvescordeiro/cardio-ia-assistente)  
**Escopo:** FIAP Fase 5, Capítulo 1 — integração ECO (acolhimento psicossomático) ao assistente cardiológico já existente.  
**Caráter:** protótipo acadêmico. **Não** é dispositivo médico (não se enquadra em registro ANVISA de software como dispositivo médico).  
**Princípio clínico:** na dúvida diagnóstica, o atendimento presencial **sempre** prevalece sobre a hipótese de estresse. Possível SCA **nunca** é classificado como «só ansiedade».

---

## 1. Viabilidade técnica e IBM Lite

### 1.1 O que já existia e o que o ECO acrescenta

O backend Flask (`backend/app.py`) já consumia IBM Watson Assistant v2 (`create_session` / `message` / `delete_session`) com `environment_id`, e já possuía um motor local isomorfo ao skill (`LocalRuleEngine`). A integração ECO **não substitui** essa pilha: acrescenta intents psicossomáticos, um filtro de segurança pré-Watson e uma UI calma (4-7-8, 188/192).

Manter o fallback local não é atalho: é a forma de demonstrar o fluxo pedagógico quando a nuvem Lite recusa snapshot, release ou cota.

### 1.2 Limites do plano Lite (honestidade operacional)

Limites já observados neste repositório:

| Limite Lite | Efeito observado | Mitigação no protótipo |
| --- | --- | --- |
| Cotas de *API calls* (mensagens + sessões) | `create_session` / `message` passam a falhar no meio da demo | `WatsonService` degrada para o motor local sem quebrar a UI |
| Timeout de sessão (tipicamente ~5 minutos sem atividade) | `session_id` inválido no turno seguinte | Recriação de sessão + memória local de triagem |
| Latência de ida e volta (IAM + Assistant, frequentemente 400–1200 ms) | Percebe-se no «digitando…»; o Flask não é o gargalo | Timeout curto no SDK; fallback se a nuvem atrasar ou errar |
| Limite de *snapshots* / versões de skill | `update_skill` ou o treino assíncrono recusam novas versões | O JSON versionado em `watson/cardio_assistant_skill.json` permanece a fonte da verdade |
| Limite de *releases* (Lite costuma restringir publicações LIVE) | `create_release` / `deploy_release` retornam erro de cota | O relatório registra a falha; a `environment_id` do `.env` pode continuar apontando para draft já existente |

**Veredito técnico:** o desenho é viável para disciplina e demo local. **Não** é viável como canal clínico 24/7 em Lite: cota, ausência de SLA e teto de releases impedem operação assistencial. Para um piloto institucional seriam necessários plano Plus/Enterprise, filas, observabilidade e revisão clínica formal.

### 1.3 Latência versus consumo Flask

O Flask serializa JSON e aplica o interceptor. O custo dominante, quando a nuvem está no caminho, é a chamada Assistant v2. O interceptor de ideação **não chama Watson** — reduz cota e remove a dependência de NLU para um evento de vida.

Sessões Watson v2 são stateful no ambiente; sessões locais são UUID em memória de processo. Reiniciar o Flask zera o estado local — adequado a demo, inadequado a produção.

### 1.4 Publicação LIVE

O script `scripts/publish_watson_skill.py` executa `update_skill` → `create_release` → `deploy_release`. No plano Lite, o teto de **2 snapshots** de diálogo e de actions foi confirmado na prática: a primeira `create_release` falhou até a remoção de uma release antiga que não estava no LIVE. Após correção de uma colisão de `previous_sibling` no JSON, o skill treinou (`Available`) e a **release 10** (aliases de auditoria + ABRATA/CAPS) foi publicada no environment LIVE. O `WATSON_ENVIRONMENT_ID` do `.env` aponta para esse LIVE. Sem o fallback local, qualquer novo estouro de cota voltaria a impedir a demo — o motor de regras permanece a rede de segurança.

---

## 2. Viabilidade ético-regulatória

### 2.1 Risco civil e clínico do falso-positivo de ansiedade

O dano mais grave deste produto não é «assustar» alguém com o 192. É o inverso: acolher como crise de pânico um IAM/SCA em curso (STEMI ou equivalente). Sudorese fria, irradiação para braço/mandíbula e desmaio são *red flags* clássicos; a sobreposição com sintomas de pânico (taquicardia, aperto, dispneia) é exatamente o que torna o erro plausível.

**Regra de decisão (implementada):**

1. Ideação / automutilação → CVV 188, **sem Watson**.
2. Ideação **e** linguagem de emergência cardíaca → 188 **e** 192, sem Watson.
3. Red flags cardíacos (irradiação, suor frio, desmaio, SCA explícito) → SAMU 192; *jump* sem retorno ao 4-7-8.
4. Dúvida de infarto (`#duvida_infarto`) → **não** tranquiliza; rastreia *red flags*; qualquer positivo **ou incerteza** → 192.
5. Psicossomático só após rastreio negativo → psicoeducação + 4-7-8, com ressalva de avaliação presencial.
6. Conflito «ansiedade» + irradiação + sudorese → rota **cardíaca**. O léxico está em `backend/services/safety_filter.py`.

Na dúvida, o nó decide por presencial. Falso-positivo de SAMU é aceitável em protótipo; falso-negativo de SCA não é.

### 2.2 LGPD e anonimato do chat

- Não há cadastro, cookie de identificação nem persistência da conversa em banco.
- O banner da UI declara sessão segura e anônima.
- Sessões Watson na IBM Cloud transitam texto livre: **não se deve colar dado pessoal real** (nome, CPF, prontuário). A demo usa narrativas sintéticas.
- Base legal de um piloto real exigiria aviso de privacidade, minimização, retenção definida e DPO. Este repositório não implementa isso — e o relatório não afirma que implementa.

### 2.3 Não é dispositivo médico

O CardioIA + ECO não calcula escore de TIMI/HEART, não lê ECG e não emite laudo. É um **protótipo de diálogo** com regras explícitas. Qualquer uso clínico seria exercício irregular de atribuição profissional e risco civil (CDC, responsabilidade do desenvolvedor e da instituição). O *disclaimer* permanece visível em todas as telas.

---

## 3. Viabilidade de UX (pânico e calma)

Pessoas em taquicardia ou aperto não leem parágrafos longos nem suportam UI alarmista.

| Recurso | Função |
| --- | --- |
| Linguagem não alarmista | Acolhimento; sem «calma, é só ansiedade» |
| *Chips* de resposta rápida | Aperto no peito, palpitação, ansiedade, 4-7-8, emergência |
| Componente 4-7-8 | Círculo visual (inspire 4 / segure 7 / expire 8) — só após rastreio |
| Dark mode (padrão) | Paleta fria (teal/slate); vermelho **apenas** no CTA 192 |
| Discagem `tel:192` e `tel:188` | Um toque, inclusive no modal |
| Modal bloqueante de crise | Não fecha sem reconhecer os números |
| Banner + rodapé legais | Permanentes em qualquer rota da página única |

Fricção residual: quem está em pânico ainda precisa **digitar** se não usar *chip*. Aceitável em demo; em produto real caberia voz.

---

## 4. Rubrica FIAP — checklist

| Entrega | Status | Evidência |
| --- | --- | --- |
| Backend Flask (REST, sessões, filtro de risco) | **Pass** | `backend/app.py` — `/api/chat`, `/api/message`, `/api/session`, `/api/health`, interceptor |
| Skill Watson exportado em JSON | **Pass** | `watson/cardio_assistant_skill.json` |
| Documentação do fluxo conversacional | **Pass** | `docs/relatorio_conversacional.md` + este relatório |
| Relatório técnico 1–2 páginas | **Pass** | `docs/relatorio_tecnico_fiap.md` |
| GitHub | **Pass** | repositório público informado no cabeçalho |
| Roteiro de vídeo ≤ 3 min | **Pass** | `docs/roteiro_video_pitch.md` (gravação é ato do aluno) |
| UI HTML5/CSS3/JS + dark/calm | **Pass** | `frontend/` |
| Segurança 192 / 188 | **Pass** | filtro + skill + modal |
| Publicação LIVE IBM | **Condicional** | depende da cota Lite no momento do `publish_watson_skill.py` |

---

## 5. Veredito (quatro eixos)

1. **Técnico:** viável como protótipo com fallback; Lite é o elo frágil (cota, sessão, release).
2. **Ético-regulatório:** viável apenas como material acadêmico; o desenho dos nós reduz — não elimina — o risco de SCA rotulado como ansiedade.
3. **UX:** viável para demo de pânico leve; discagem e 4-7-8 diminuem fricção.
4. **Acadêmico (rubrica):** entrega alinhada ao Capítulo 1; o vídeo permanece pendência humana.

**Recomendação:** seguir com a demo FIAP. Não promover o assistente como ferramenta clínica.
