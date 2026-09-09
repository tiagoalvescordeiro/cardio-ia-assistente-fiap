# Roteiro de demonstração em vídeo — CardioIA + ECO (≤ 3 minutos)

**Tom:** institucional, calmo, sem promessa de diagnóstico.  
**Disclaimer (0:00–0:08 e 2:50–3:00):**  
*Este assistente não substitui atendimento médico e não é dispositivo médico. Emergência cardíaca: 192. Crise emocional com ideação: 188.*  
**Dados na tela:** apenas narrativas sintéticas. Nenhum nome civil.

Tela cheia em `http://127.0.0.1:5000` (ou URL pública do túnel). Dark mode ligado. Banner «sessão segura e anônima» visível.

---

## 0:00–0:08 — Abertura + disclaimer

**Visual:** topbar CardioIA + ECO, banner, *disclaimer*, botões 192 e 188.  
**Narração:**  
«CardioIA mais ECO: acolhimento inicial de queixa cardíaca e psicossomática. Não diagnostica. Na dúvida, o presencial vem primeiro. SAMU 192. CVV 188.»

## 0:08–0:22 — Problema em uma frase

**Visual:** chips (aperto, palpitação, ansiedade, 4-7-8, emergência).  
**Narração:**  
«Aperto, taquicardia e tensão moram na fronteira entre alerta de estresse e síndrome coronariana. O erro grave é chamar infarto de ansiedade.»

## 0:22–0:48 — Saudação isolada

**Ação:** chip **Saudação** → «Oi».  
**Esperado:** boas-vindas curtas, sem triagem.  
**Narração:**  
«Saudação só responde a oi e olá. Narrativa de dor nunca cai em boas-vindas.»

## 0:48–1:28 — Ramo ECO (ansiedade → rastreio → 4-7-8)

**Ação 1:** chip **Ansiedade**.  
**Esperado:** acolhimento + pergunta de irradiação / suor frio / desmaio.  
**Ação 2:** digitar **«Não, sem irradiação e sem suor frio»**.  
**Esperado:** psicoeducação de luta-ou-fuga + oferta 4-7-8; o painel do círculo, o **pulso anônimo** e o heatmap agregado aparecem — sem pedir localização.  
**Ação 3:** clicar **Iniciar 4-7-8** (2–3 segundos de inspire).  
**Narração:**  
«Sem red flag depois do rastreio, vêm a psicoeducação, o 4-7-8 e o pulso k-anônimo sintético. Não há diagnóstico de pânico e não há GPS.»

## 1:28–2:05 — Red flag cardíaco → 192 (sem voltar ao 4-7-8)

**Ação:** nova ideia na mesma sessão ou recarregar e enviar  
«Dor no peito irradiando para o braço com suor frio».  
**Esperado:** CTA SAMU 192; botão vermelho `tel:192`; **não** abre exercício de respiração como desfecho.  
**Narração:**  
«Irradiação mais sudorese é rota cardíaca. O diálogo salta para o 192 e não regressa ao 4-7-8.»

## 2:05–2:35 — Ideação → modal 188, sem Watson

**Ação:** digitar uma frase sintética de crise, por exemplo **«Não quero mais viver»**.  
**Esperado:** modal bloqueante com 188 **e** 192; só fecha após o checkbox; a pílula da API permanece ok — o backend interceptou.  
**Narração:**  
«Ideação não passa pelo Watson. O Flask devolve CVV 188 e SAMU 192 na hora.»

## 2:35–2:50 — Arquitetura em 15 segundos

**Visual:** corte rápido no `GET /api/health` (pílula «API ok · Watson cloud/fallback») ou no JSON do skill.  
**Narração:**  
«Flask, skill Watson versionado, filtro de segurança e fallback local se a nuvem falhar.»

## 2:50–3:00 — Fechamento

**Visual:** *disclaimer* de rodapé.  
**Narração:**  
«Protótipo acadêmico. Presencial primeiro. 192 e 188.»

---

## Checklist de captura

- [ ] Banner anônimo + *disclaimer* visíveis
- [ ] Saudação curta
- [ ] Ansiedade → rastreio → 4-7-8 na UI
- [ ] Pulso k-anônimo + heatmap visíveis (sem pedir localização)
- [ ] Peito + irradiação + suor → 192
- [ ] Frase de ideação → modal 188
- [ ] Nenhum dado pessoal real
- [ ] Duração ≤ 3:00
