# Especificação — Módulo conversacional CardioIA + ECO

**Projeto:** CardioIA Assistente  
**Herança:** [cardio-ia-fase1](https://github.com/tiagoalvescordeiro/cardio-ia-fase1)  
**Caráter:** protótipo acadêmico / demonstração técnica. **Não** é dispositivo médico nem sistema de apoio diagnóstico validado.  
**Disclaimer:** *Este assistente não substitui atendimento médico e não é dispositivo médico. Em emergências cardíacas, ligue 192 (SAMU). Em crise emocional com ideação, ligue 188 (CVV).*  
**Complemento:** [relatorio_viabilidade_eco.md](relatorio_viabilidade_eco.md).

## 1. Objetivo

Canal conversacional em português (pt-BR) que:

1. reconheça intenções clínicas frequentes em cardiologia de triagem (saudação, dor torácica, equivalente isquêmico epigástrico, pressão arterial, lembrete de medicação, agendamento, emergência);
2. identifique *red flags* (irradiação, sudorese fria, dispneia, equivalentes isquêmicos) e oriente o SAMU 192;
3. acolha queixas psicossomáticas (ECO) com psicoeducação da resposta de estresse e respiração 4-7-8 **somente após** rastreio negativo de alarme — possível SCA nunca é «só ansiedade»;
4. intercepte ideação/automutilação no Flask (CVV 188) **sem** chamar Watson;
5. opere com **IBM Watson Assistant v2** quando houver credenciais e, na ausência delas, com um **motor de regras local** isomorfo ao skill.

O fallback local garante demonstração offline: o fluxo não depende de chave de nuvem para ser evidenciado.

## 2. Arquitetura

```
Navegador (frontend/)  --JSON-->  Flask (backend/app.py)
                                      |
                                      +--> safety_filter (ideação → 188, sem Watson)
                                      +--> WatsonService
                                            |-- IBM AssistantV2 (se WATSON_API_KEY + ASSISTANT_ID)
                                            +-- LocalRuleEngine (skill espelhado + ramo ECO)
```

Aliases de contrato: `POST /api/message` = `/api/chat`; `POST/DELETE /api/session` criam e encerram a sessão Watson v2.

O Flask também serve `frontend/` na raiz HTTP (`python backend/app.py` como comando único de demo). Bind padrão: `FLASK_HOST=0.0.0.0`, `FLASK_PORT=5000`.

Contrato de `POST /api/chat`:

| Campo | Direção | Descrição |
| --- | --- | --- |
| `message` | request | Texto livre do usuário |
| `session_id` | request opcional | Sessão Watson ou UUID local |
| `reply` | response | Texto do diálogo (aviso ético uma vez por sessão, na saudação) |
| `intents` / `entities` | response | Espelho do output Watson ou do classificador local |
| `disclaimer` | response | Texto ético padronizado |
| `source` | response | `watson` ou `fallback` |

`GET /api/health` expõe `watson_mode` (`cloud` \| `fallback`) para o *status pill* da UI.

## 3. Skill Watson (`watson/cardio_assistant_skill.json`)

Exportação no formato clássico de *workspace/skill* (intents, entities, `dialog_nodes`, *counterexamples*).

**Intents principais**

| Intent | Papel clínico no diálogo |
| --- | --- |
| `#saudacao` | Só cumprimento curto isolado (`Oi`, `Olá`, `Bom dia`…). Sem dor, peito, mal, problema ou pedido de ajuda |
| `#relatar_sintoma` | Narrativa cotidiana (roçar mato, carpir, varrer, repuxo, mau jeito, fisgada na costela) — **início imediato de triagem**, nunca boas-vindas |
| `#queixa_abdominal` | Equivalente isquêmico (epigástrio / barriga alta) — ramo próprio |
| `#triagem_dor_peito` | Anamnese dirigida de dor torácica |
| `#pressao_arterial` | Técnica de medida e limiares PAS/PAD |
| `#lembrete_medicamento` | Adesão — **sem** alterar prescrição |
| `#agendamento_consulta` | Encaminhamento institucional (agenda não integrada) |
| `#emergencia_cardio` | Prioridade máxima; SAMU 192 |
| `#afirmacao` / `#negacao` | Respostas curtas da anamnese (não caem em `anything_else`) |
| `#pedido_medicacao` | Recusa categórica de indicação de remédio |
| `#despedida` | Encerramento regional + UBS se a dor voltar |
| `#sintoma_peito` | Alias ECO de dor/aperto torácico (segue triagem, não o 4-7-8) |
| `#sintoma_taquicardia` | Palpitação — rastreio de *red flags* antes de psicoeducação |
| `#sintoma_ansiedade` | Queixa de estresse/tensão/insônia — rastreio primeiro |
| `#duvida_infarto` | Medo de IAM: **nunca** tranquiliza; incerteza → 192 |
| `#alerta_emergencia` | Alias ECO de `#emergencia_cardio` |
| `#solicitar_respiracao` | 4-7-8; bloqueado se `$risco == A` ou `@sinal_alerta` |
| `#ideacao_crise` / `#ideacao_risco` | CVV 188 + SAMU 192 (o backend intercepta) |
| `#sintoma_cardiaco` | Alias de dor/aperto torácico |
| `#red_flags` | Alias de emergência → 192 |
| `#estresse_ansiedade` | Alias de queixa psicossomática (rastreio primeiro) |

**Entidades:** `@sintoma`, `@local_dor` (epigástrio, baixo ventre, peito, **so_peito**, costas, braço, mandíbula), `@qualidade_dor` (aperto, queimação, cólica, pontada, **repuxo**), `@caracteristica_msk` (palpável, pleurítica, muscular, **esforço localizado**), `@intensidade`, `@duracao`, `@sintoma_associado`, `@gatilho_emocional`, `@medicamento`, `@pressao_arterial`, `@barreira_socorro`, `@contexto`, **`@sinal_alerta` / `@sinais_alerta`** (irradiação, suor_frio, desmaio), **`@sintoma_somatico` / `@sintomas_somaticos`** (aperto, no_garganta, tensao, palpitacao).

Aliases adicionais: `#relatar_dor_peito` (dor torácica) e `#pedir_ajuda_humana` (encaminha 192/188/UBS, nunca «só ansiedade»).

**Fork ECO.** Depois do rastreio: (1) *red flag* cardíaco → *jump* `node_emergencia_hold` (192), sem retorno ao 4-7-8; (2) psicossomático sem alarme → psicoeducação + 4-7-8; (3) `#duvida_infarto` rastreia antes de qualquer hipótese de ansiedade; (4) `#ideacao_crise` → 188. A saudação permanece isolada a cumprimentos curtos.

**Árvore de diálogo (anamnese adaptativa).** No máximo **uma** pergunta objetiva por turno. Variáveis `$triagem_etapa`, `$local_dor`, `$qualidade`, `$irradiacao`, `$sintomas_associados`, `$negou_irradiacao`, `$negou_suor`, `$negou_dispneia`, `$dor_palpavel`, `$dor_pleuritica`, `$emergencia_ativa` e `$risco` (A/B/C) permitem que respostas curtas continuem a mesma ficha. Alarme usa `jump_to` para `node_emergencia_hold`.

**Negações.** “Não”, “nem”, “sem”, “nunca”, “nenhuma”, “não tenho”, “não sinto”, “não irradia”, “sem irradiação” marcam o achado como **ausente**. O motor local replica o parser no estado da sessão.

**Matriz de decisão.** A — alarme confirmado: SAMU 192. B — padrão mecânico/MSK sem irradiação e sem sintomas autonômicos: tranquiliza com voz do Vale, oriente **postinho**, **sem** 192. C — incompleto: uma pergunta só. Misto (esforço localizado **mas** suor frio + aperto/peso) → **A vence**.

Ordem de prioridade: isolamento sem telefone → imobilidade com peito/suor → **dor mecânica por esforço (B)** → padrão MSK palpável sem alarme (B) → equivalente isquêmico com suor e irradiação (SAMU) → emergência clássica → continuação da anamnese → entrada abdominal → entrada de peito → demais intents → saudação curta. `anything_else` cobre o *fallback*.

Importação sugerida: IBM Cloud → Watson Assistant → *Upload skill*. Após o upload, anotar `ASSISTANT_ID` e o `ENVIRONMENT_ID`.

## 4. Motor local (paridade)

`LocalRuleEngine` normaliza o texto (NFKD, minúsculas) e replica a mesma máquina de estados do skill. Regras clínicas extras:

- queixa de barriga/estômago/epigástrio **não** dispara o bloco de dor torácica — investiga localização e qualidade;
- suor frio + irradiação, dispneia súbita, tontura grave ou impossibilidade de se mover disparam SAMU 192 — **somente se o usuário não negou** esses achados;
- padrão palpável/pleurítico **ou narrativa mecânica** sem irradiação e sem sintomas autonômicos cai no cenário B;
- `#saudacao` no fallback só casa cumprimento curto por regex;
- respostas monossilábicas herdam `$triagem_etapa` da sessão;
- leitura `PAS/PAD` por regex alimenta o comentário de crise (PAS ≥ 180 ou PAD ≥ 120), alinhada ao worker RPA e à Fase 1/3 (FC > 120 bpm).

Sessões locais são UUID em memória; sessões Watson usam `create_session` / `delete_session` / `message` do SDK `ibm-watson` (AssistantV2). Exceção de rede ou IAM **degrada** para o motor local sem quebrar a UI.

## 5. Interface

Widget calmo (dark mode padrão): bolhas distintas, indicador **«digitando…»**, envio por Enter ou botão, banner «sessão segura e anônima», *disclaimer* legal, discagem `tel:192` / `tel:188`, *chips*, círculo 4-7-8 com timer e modal bloqueante de crise. Idioma integralmente pt-BR.

## 6. Persona (Santa Catarina) e paciente isolado

A CardioIA *é* a interlocutora do Vale do Itajaí / Blumenau: assertiva, pragmática e resolutiva. Marcadores discretos (“Pois então”, “Olha só”, “Bem certinho”, “Fica tranquilo, visse?”). Tu/você fluido. No máximo 3–4 frases e **uma** pergunta por turno.

Não há diagnóstico nem prescrição. O aviso ético entra **uma vez** na sessão. Socorro: **192 (SAMU)**. Dor epigástrica / “dor na barriga alta” / queimação / náusea é equivalente isquêmico (SBC/AHA).

**Jump-to de emergência.** Alarme interrompe a anamnese: `jump_to` em `node_emergencia_hold`, grava `$emergencia_ativa` e **não retorna** a perguntas secundárias. O motor local replica o salto: uma vez A, permanece A.

**`#pedido_medicacao`.** Recusa categórica. Em contexto de alarme, recusa **e** mantém o CTA do SAMU.

**Paciente sozinho que não alcança o telefone.** Permanece em `#emergencia_cardio` (`node_isolamento_sem_telefone`). Comando de voz; chamar vizinho; sem esforço. Não reabre a triagem de peito.

## 7. Limitações e ética

- Não há NLU estatístico no fallback: homonímias e negações compostas ainda podem falhar.
- O skill não substitui protocolo de Manchester/ESI nem diretriz da SBC/AHA.
- Nenhum dado real de paciente deve ser colado no chat de demonstração.

## 8. Referências de herança

- Dataset Heart Failure (Fase 1): `RestingBP`, `MaxHR` — aqui desdobrados em PAS, PAD e FC.
- Limiares de telemetria (Fase 3): alerta de taquicardia se **BPM > 120** e bradicardia se **BPM < 50**.
- Textos e mapa de sintomas da Fase 2 informam o vocabulário de dor irradiada e sudorese fria.
