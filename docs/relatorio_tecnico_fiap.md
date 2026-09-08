# Relatório técnico — CardioIA + ECO (FIAP Fase 5, Cap. 1)

**Autores / projeto:** CardioIA Assistente  
**Repositório:** https://github.com/tiagoalvescordeiro/cardio-ia-assistente  
**Aviso:** protótipo acadêmico. Não diagnostica, não prescreve e não é dispositivo médico. Emergência cardíaca: **192**. Crise emocional com ideação: **188**.

## Introdução

O CardioIA é um canal de triagem conversacional cardiológica em português, integrado ao IBM Watson Assistant v2 e a um motor local de paridade. O Capítulo 1 acrescenta o **ECO**: acolhimento de queixas psicossomáticas (taquicardia, aperto, dispneia subjetiva, insônia, tensão) com psicoeducação da resposta neurobiológica de estresse — **sempre subordinada** à triagem de *red flags* cardíacos.

A hipótese de trabalho é arquitetural, não clínica: no mesmo diálogo podem coexistir um fork de emergência (SAMU 192) e um fork de regulação autonômica (4-7-8), sem que o segundo “explique” o primeiro.

## Problema

Dor torácica, palpitação e falta de ar habitam a zona cinzenta entre síndrome coronariana aguda e crise de alerta. Tranquilizar cedo demais é o erro de maior gravidade; limitar-se a “192” abandona quem precisa de acolhimento. Famílias e serviços convivem com os dois mundos no mesmo relato em linguagem natural.

Restrições de disciplina: Flask, skill Watson exportável, UI calma com dark mode, GitHub e vídeo de até três minutos. Restrição ética: na dúvida, presencial.

## Arquitetura

O navegador consome `POST /api/chat` (alias `/api/message`). O Flask aplica `evaluate_safety` **antes** de qualquer NLU: léxico de ideação devolve **CVV 188 e SAMU 192** e **não chama Watson**. Red flags isolados seguem para o diálogo (skill ou `LocalRuleEngine`), que faz *jump* para o hold do 192 e não retorna ao 4-7-8. Erro de conexão não silencia a orientação de emergência.

Sessões Watson v2 usam `assistant_id` + `environment_id`. Sem credencial, ou se a Lite falhar, o motor local replica intents, entidades e a matriz A/B/C (isquêmico, mecânico, incompleto) e acrescenta o ramo ECO (rastreio → psicoeducação → 4-7-8). Extração clínica (`/api/extract`) e RPA híbrido permanecem como *Ir Além*, fora do caminho crítico do chat.

## Fluxo conversacional

1. Saudação isolada (`oi` / `olá`) — sem narrativa de dor.
2. Ideação (`#ideacao_risco`) → 188 **e** 192 (interceptor).
3. Isolamento / imobilidade / alarme isquêmico (`#red_flags`) → 192, *hold*.
4. Narrativa mecânica (repuxo após esforço) sem autonômicos → cenário B (UBS), inalterado.
5. `#duvida_infarto` → rastreio; sim ou incerteza → 192; nunca «é só ansiedade».
6. `#estresse_ansiedade` / taquicardia sem *red flags* → psicoeducação autonômica (luta-ou-fuga) + 4-7-8 + CVV/ABRATA/CAPS.
7. Pedido de respiração com alarme no mesmo turno → 192, não o exercício.

A UI oferece *chips*, discagem `tel:`, modal bloqueante 188/192, círculo 4-7-8, **pulso k-anônimo sintético** («Na sua região metropolitana, N pessoas relataram…») e heatmap agregado sem pinos — **sem coleta de localização real**. Dark mode é o padrão. Conformidade: [tabela_conformidade_eco.md](tabela_conformidade_eco.md).

## Conclusão

O ECO integra-se ao CardioIA sem descartar Watson, GitHub ou a triagem prévia. A viabilidade acadêmica é alta; a viabilidade clínica de produção, no plano Lite e sem validação assistencial, é baixa — e deve permanecer declarada. O valor da entrega está na **governança do fork**: estresse se acolhe; SCA se encaminha; a dúvida não se resolve no chat.
