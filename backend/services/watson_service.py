"""
Integração IBM Watson Assistant v2 com fallback local baseado em regras.

Quando WATSON_API_KEY / WATSON_ASSISTANT_ID não estão definidos (ou a chamada
falha), o serviço espelha os intents e o fluxo do skill
`watson/cardio_assistant_skill.json`, permitindo demonstração offline.

A anamnese é adaptativa (1–2 perguntas por turno). Equivalentes isquêmicos
(epigástrio / barriga alta) entram em ramo próprio — não são descartados
como queixa gastrointestinal.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, fields
from typing import Any

from config import DISCLAIMER, settings

logger = logging.getLogger(__name__)

INTENT_SAUDACAO = "saudacao"
INTENT_RELATAR = "relatar_sintoma"
INTENT_TRIAGEM = "triagem_dor_peito"
INTENT_ABDOMINAL = "queixa_abdominal"
INTENT_PRESSAO = "pressao_arterial"
INTENT_LEMBRETE = "lembrete_medicamento"
INTENT_AGENDAMENTO = "agendamento_consulta"
INTENT_EMERGENCIA = "emergencia_cardio"
INTENT_AFIRMACAO = "afirmacao"
INTENT_NEGACAO = "negacao"
INTENT_MEDICACAO = "pedido_medicacao"
INTENT_DESPEDIDA = "despedida"
INTENT_FALLBACK = "anything_else"
# ECO / FIAP Cap. 1 — aliases e intents psicossomáticos (não substituem a triagem A/B/C)
INTENT_SINTOMA_PEITO = "sintoma_peito"
INTENT_SINTOMA_CARDIACO = "sintoma_cardiaco"
INTENT_TAQUICARDIA = "sintoma_taquicardia"
INTENT_ANSIEDADE = "sintoma_ansiedade"
INTENT_ESTRESSE = "estresse_ansiedade"
INTENT_DUVIDA_INFARTO = "duvida_infarto"
INTENT_ALERTA_ECO = "alerta_emergencia"
INTENT_RED_FLAGS = "red_flags"
INTENT_RESPIRACAO = "solicitar_respiracao"
INTENT_IDEACAO = "ideacao_crise"
INTENT_IDEACAO_RISCO = "ideacao_risco"
INTENT_RELATAR_DOR_PEITO = "relatar_dor_peito"
INTENT_AJUDA_HUMANA = "pedir_ajuda_humana"
INTENT_CEFALEIA = "queixa_cefaleia"

CHEST_INTENTS = {INTENT_TRIAGEM, INTENT_RELATAR, INTENT_SINTOMA_PEITO, INTENT_SINTOMA_CARDIACO, INTENT_RELATAR_DOR_PEITO}
ECO_INTENTS = {INTENT_ANSIEDADE, INTENT_ESTRESSE, INTENT_TAQUICARDIA, INTENT_RESPIRACAO}
EMERGENCY_INTENTS = {INTENT_EMERGENCIA, INTENT_ALERTA_ECO, INTENT_RED_FLAGS}
IDEACAO_INTENTS = {INTENT_IDEACAO, INTENT_IDEACAO_RISCO}

# --- Respostas canônicas (skill Watson + fallback devem coincidir) ---

REPLY_SAUDACAO = (
    "Olá, tudo bem? Eu sou a CardioIA — triagem e acolhimento inicial, "
    "sem diagnosticar e sem receitar. Pode me contar o que está sentindo. "
    f"{DISCLAIMER}"
)

REPLY_CHEST_COM_QUALIDADE = (
    "Essa dor vai para o braço e costas, ou fica só no peito?"
)

REPLY_CHEST_Q1 = "Essa dor é aperto, queimação ou pontada?"

REPLY_CHEST_Q2 = "Essa dor vai para o braço e costas, ou fica só no peito?"

REPLY_MSK_Q = (
    "Essa dor piora quando você aperta o lugar, mexe o tronco ou respira fundo?"
)

REPLY_MSK_ESFORCO_Q = "Essa dor piora quando você vira o tronco ou respira fundo?"

REPLY_MECANICA = (
    "Compreendi. Como esse repuxo começou logo depois do esforço e dói mais "
    "quando você vira o corpo, isso tem característica de dor muscular — "
    "sem ser um diagnóstico. "
    "Mantenha repouso e, se não melhorar nos próximos dias, procure a UBS."
)

REPLY_AUTONOMIC_Q = "Você está com suor frio ou falta de ar agora?"

REPLY_CENARIO_B = (
    "Entendido. Dor que piora na palpação, no movimento ou na respiração funda "
    "deixa menos provável um evento cardíaco agudo agora — sem ser diagnóstico. "
    "Se persistir, procure a UBS. Não precisa de ambulância neste momento."
)

REPLY_ABD_Q1 = "Essa dor é mais na boca do estômago, em cima, ou mais para baixo?"

REPLY_ABD_QUEIMACAO_NAUSEA = (
    "Essa queimação é mais na boca do estômago, em cima, ou embaixo?"
)

REPLY_SAMU_EPIGASTRIO = (
    "Isso exige avaliação médica imediata. "
    "Ligue agora para o SAMU (192) ou peça para alguém levá-lo à emergência. "
    "Mantenha repouso absoluto."
)

REPLY_EMERGENCIA_IMOVEL = (
    "Fique parado e não tente fazer esforço. "
    "Isso exige avaliação médica imediata. "
    "Use o comando de voz do celular agora para ligar o **192 (SAMU)** "
    "ou peça socorro a quem estiver perto. "
    "Mantenha repouso absoluto."
)

REPLY_EMERGENCIA = (
    "Isso exige avaliação médica imediata. "
    "Ligue agora para o SAMU (192) ou peça para alguém levá-lo à emergência. "
    "Mantenha repouso absoluto."
)

REPLY_EMERGENCIA_HOLD = (
    "Mantenha repouso absoluto. Se ainda não ligou, ligue agora para o SAMU (192). "
    "Não faça esforço e não dirija."
)

REPLY_ISOLAMENTO = (
    "Estou aqui com você. Não tente levantar de vez se estiver tonto. "
    "Use o comando de voz: diga em voz alta \"Ok Google, ligar para 192\" "
    "ou \"Ei Siri, ligar para o SAMU\". "
    "Se o aparelho estiver longe, chame alguém próximo e não faça esforço."
)

REPLY_SEM_ALARME_PEITO = (
    "Por agora não identifiquei sinal que peça o SAMU na hora. "
    "Isso não descarta avaliação presencial se a dúvida persistir. "
    "Se quiser, a respiração 4-7-8 pode ajudar na tensão: inspire 4, segure 7, expire 8. "
    "Se for para o braço, vier suor frio ou falta de ar, ligue 192."
)

REPLY_SEM_ALARME_ABD = (
    "Entendi. Por agora não identifiquei sinais que peçam o SAMU na hora. "
    "Se a dor subir para o peito, vier suor frio ou falta de ar, ligue 192."
)

REPLY_MEDICACAO = (
    "Não posso indicar medicação por aqui. "
    "Para sua segurança, não tome nada por conta própria agora; "
    "procure a UBS ou a emergência para avaliação."
)

REPLY_MEDICACAO_EMERGENCIA = f"{REPLY_MEDICACAO} {REPLY_EMERGENCIA}"

REPLY_DESPEDIDA = (
    "Tudo certo. Fique em repouso e, se a dor voltar ou piorar, procure a UBS. Cuide-se."
)

REPLY_FALLBACK = (
    "Não peguei direito — pode me contar de outro jeito o que está sentindo agora? "
    "Estou aqui com você. Se for emergência, ligue 192."
)

# --- ECO: acolhimento vicário + psicoeducação (nunca substitui red-flag) ---

REPLY_DUVIDA_INFARTO = (
    "Essa dúvida é importante — e eu não vou tratar como «só ansiedade». "
    "A dor irradia para o braço, pescoço ou mandíbula? Tem suor frio ou desmaio agora? "
    "Se sim, ou se não tiver certeza, ligue 192 (SAMU)."
)

REPLY_ECO_SCREEN = (
    "Estou aqui com você. Entendo o desconforto — o corpo em alerta pode reagir assim, "
    "sem isso ser um diagnóstico. "
    "Antes de qualquer hipótese de estresse: tem dor no peito indo para o braço, suor frio ou desmaio agora?"
)

REPLY_ECO_478 = (
    "Por agora não vi sinal que peça o SAMU na hora — se a dúvida continuar, "
    "avaliação presencial ainda vale. "
    "A respiração 4-7-8 (inspire 4, segure 7, expire 8) é prática física. "
    "Rede: CVV 188, ABRATA e o CAPS do município. Se surgir irradiação, suor frio ou desmaio, 192."
)

REPLY_IDEACAO = (
    "Sua vida importa. Você não está sozinho. "
    "Ligue agora o CVV 188 (24h, gratuito, sigiloso — https://cvv.org.br) "
    "e o SAMU 192 se houver qualquer risco imediato. "
    "Rede de apoio: ABRATA (https://www.abrata.org.br) e o CAPS do seu município."
)

# Cefaleia: turn-based (nunca checklist + 192 + UBS na mesma bolha).
REPLY_CEFALEIA = (
    "Sinto muito por essa dor. "
    "Ela veio de repente, como a pior da sua vida, ou foi aumentando?"
)

REPLY_CEFALEIA_CLEAR = (
    "Entendi — sem esses sinais de alerta por agora. "
    "Descanse, hidrate-se e, se a dor persistir ou piorar, procure a UBS."
)

REPLY_CEFALEIA_NEURO = (
    "Obrigado por me falar disso — com esse sinal de alerta, o caminho seguro é "
    "ligar agora para o SAMU (192). Peça para alguém ficar com você e fique em repouso "
    "enquanto aguarda."
)

REPLY_CEFALEIA_EMOTION = (
    "Parece que a dor vem junto com lembranças difíceis — isso importa. "
    "A fraqueza que você sente é mais um cansaço pesado no corpo todo, "
    "ou algo súbito de um lado, com fala ou visão diferentes?"
)

REPLY_CEFALEIA_EMOTION_SCREEN = (
    "Parece que a dor vem junto com algo difícil — isso importa. "
    "Ela veio de repente, como a pior da sua vida, ou foi aumentando aos poucos?"
)

REPLY_AJUDA_HUMANA = (
    "Claro — este canal é triagem inicial, não substitui atendimento humano. "
    "Se for emergência cardíaca (aperto, irradiação, suor frio, desmaio), ligue 192 agora. "
    "Se for crise emocional com ideação, ligue 188 (CVV). "
    "Fora disso, UBS, CAPS ou o plantão da instituição. "
    "Na dúvida entre estresse e coração, o presencial vem primeiro — nunca «é só ansiedade»."
)

_CHEST_MARKERS = (
    "peito",
    "torax",
    "toracica",
    "toracico",
    "precordial",
    "retroesternal",
    "esterno",
)
_ABD_MARKERS = (
    "barriga",
    "estomago",
    "epigastr",
    "boca do estomago",
    "abdomen",
    "abdominal",
    "azia",
)
_NUMBNESS_MARKERS = (
    "dormente",
    "formigamento",
    "formigando",
    "adormecido",
    "adormecimento",
    "dormencia",
    "parestesia",
    "nao sinto o braco",
    "braco dormente",
    "braco adormecido",
)
_ALONE_MARKERS = ("sozinho", "sozinha")
_HARD_EMERGENCY_MARKERS = (
    "infarto",
    "samu",
    "ligar 192",
    "192",
    "emergencia",
    "desmaiei",
    "desmaio",
    "parada",
    "nao consigo respirar",
    "sufocando",
    "socorro",
    "ambulancia",
    "ambulância",
)
_CHEST_ALARM_MARKERS = (
    "irradia",
    "irradiando",
    "suor frio",
    "suando",
    "falta de ar",
    "dispneia",
    "dor muito forte",
    "dor forte no peito",
)
_CANNOT_REACH_PHONE_MARKERS = (
    "nao consigo ir ate o telefone",
    "nao alcanco o celular",
    "nao alcanco o telefone",
    "nao alcanco o aparelho",
    "nao tenho como ligar",
    "nao consigo ligar",
    "nao consigo chegar ate o celular",
    "nao consigo chegar no telefone",
    "nao consigo chegar ate o telefone",
    "nao consigo andar ate o telefone",
    "telefone esta longe",
    "celular esta longe",
    "aparelho esta longe",
)
_CANNOT_MOVE_MARKERS = (
    "nao consigo nem levantar",
    "nao consigo me levantar",
    "nao consigo levantar",
    "nao consigo me mexer",
    "nao consigo me mover",
    "nao consigo andar",
    "nao consigo me deslocar",
    "nao levanto",
    "nao consigo nem me levantar",
)

_HUMAN_HELP_MARKERS = (
    "falar com um humano",
    "falar com humano",
    "medico de verdade",
    "médico de verdade",
    "passar para um atendente",
    "atendimento humano",
    "transfere para alguem",
    "transfere para alguém",
    "profissional de saude",
    "profissional de saúde",
    "nao quero so o robo",
    "não quero só o robô",
    "quero uma pessoa",
    "falar com uma pessoa da equipe",
)

_MED_REQUEST_MARKERS = (
    "posso tomar",
    "pode tomar",
    "toma dipirona",
    "tomar dipirona",
    "me indica",
    "indica um",
    "qual remedio",
    "que remedio",
    "analgesico",
    "posso tomar aas",
    "tomar aas",
    "tomar aspirina",
    "me passa um",
    "qual remedio pra dor",
    "qual remedio para a dor",
    "toma buscopan",
    "anti-inflamatorio",
    "anti inflamatorio",
)

_ANXIETY_MARKERS = (
    "ansiedade",
    "ansioso",
    "ansiosa",
    "ataque de panico",
    "crise de ansiedade",
    "estou nervoso",
    "estou nervosa",
    "insonia",
    "nao consigo dormir",
    "tensao muscular",
    "musculo travado",
    "no da garganta",
    "no garganta",
    "bolo na garganta",
)

_TACHY_MARKERS = (
    "taquicardia",
    "coracao disparado",
    "coracao acelerado",
    "palpitacao",
    "palpitacoes",
    "coracao batendo forte",
    "taquicard",
)

_INFARTO_DOUBT_MARKERS = (
    "e infarto",
    "eh infarto",
    "sera infarto",
    "sera que e infarto",
    "acho que e infarto",
    "pode ser infarto",
    "estou infartando",
    "to infartando",
    "e um infarto",
    "duvida de infarto",
    "medo de infarto",
    "medo de ser o coracao",
    "sera que e o coracao",
    "pode ser o coracao",
    "isso e o coracao",
    "e um problema no coracao",
    # NÃO incluir "e o coracao" solto — casa com "ansiedade e o coração acelerado".
)

_BREATHING_REQUEST_MARKERS = (
    "respiracao 4-7-8",
    "respiracao 478",
    "4-7-8",
    "exercicio de respiracao",
    "tecnica de respiracao",
    "me ajuda a respirar",
    "quero respirar",
    "fazer a respiracao",
)

_IDEACAO_MARKERS = (
    "quero me matar",
    "vou me matar",
    "quero morrer",
    "nao quero mais viver",
    "ideacao suicida",
    "me suicidar",
    "me cortar",
    "automutilacao",
)

_FAREWELL_MARKERS = (
    "tchau",
    "obrigado",
    "obrigada",
    "era so isso",
    "era só isso",
    "valeu",
    "ate logo",
    "até logo",
    "tmj",
)
_QUESTIONNAIRE_RE = re.compile(r"1\s*[\)\.:].*2\s*[\)\.:].*3\s*[\)\.:].*4\s*[\)\.:]", re.S | re.I)

_PALPATION_MARKERS = (
    "quando aperto",
    "piora quando aperto",
    "aperto com o dedo",
    "aperto com os dedos",
    "aperto o local",
    "aperto o lugar",
    "aperto a dor",
    "se eu aperto",
    "quando pressiono",
    "pressiono o local",
    "aperto com o dedo",
    "piora quando aperto com o dedo",
)
_PLEURITIC_MARKERS = (
    "respiro fundo",
    "respirar fundo",
    "inspiro fundo",
    "pontada na respiracao",
    "piora quando respiro",
    "ao respirar",
    "na respiracao fundo",
    "mexo o tronco",
    "movimento do tronco",
    "quando me mexo",
    "quando viro o tronco",
    "piora com o movimento",
    "piora no movimento",
)
_MUSCULAR_MARKERS = (
    "e muscular",
    "dor muscular",
    "parece muscular",
    "dor de musculo",
    "musculoesquelet",
)

_GREETING_ONLY_RE = re.compile(
    r"^(oi|ola|opa|hey|hello|e ai|bom dia|boa tarde|boa noite)"
    r"([\s,.!?]+(tudo bem|tudo bom)?)?[\s,.!?]*$"
)

_EFFORT_MARKERS = (
    "rocar",
    "rocando",
    "roco o mato",
    "rocar o mato",
    "quintal",
    "carpir",
    "capin",
    "cortar lenha",
    "cortando lenha",
    "carregar saco",
    "carregando saco",
    "saco de cimento",
    "varrer",
    "varrendo",
    "puxando peso",
    "puxar peso",
    "trabalho bracal",
    "trabalho pesado",
    "movimento brusco",
    "virou o tronco",
    "viro o tronco",
    "virando o tronco",
    "tomou um jeito",
    "tomar um jeito",
    "esforco",
    "depois do esforco",
    "depois que eu tava",
    "depois que eu estava",
)

_MECH_QUALITY_MARKERS = (
    "repuxo",
    "fisgada",
    "fisgou",
    "mau jeito",
    "tomou um jeito",
    "peito puxando",
    "costela",
)

_TRIAGE_NARRATIVE_MARKERS = (
    "dor",
    "doendo",
    "doeu",
    "peito",
    "aperto",
    "repuxo",
    "fisgada",
    "fisgou",
    "pontada",
    "desconforto",
    "mal estar",
    "mal-estar",
    "mau jeito",
    "acidente",
    "caiu",
    "esforco",
    "rocar",
    "rocando",
    "carpir",
    "capin",
    "varrer",
    "lenha",
    "puxando peso",
    "costela",
    "suor",
    "falta de ar",
    "queimac",
    "quintal",
    "mato",
    "virou o tronco",
    "tomou um jeito",
)

_HEADACHE_MARKERS = (
    "dor de cabeca",
    "dores de cabeca",
    "dor na cabeca",
    "cabeca doendo",
    "cabeca doi",
    "cabeca doeu",
    "minha cabeca doi",
    "cefaleia",
    "enxaqueca",
    "migranea",
)

_NEURO_EMERGENCY_MARKERS = (
    "pior dor da vida",
    "pior dor de cabeca",
    "pior cefaleia",
    "rigidez de nuca",
    "nuca dura",
    "nuca engessada",
    "pescoco duro",
    "nao consigo abaixar o queixo",
    "fraqueza de um lado",
    "lado do corpo frouxo",
    "boca torta",
    "fala enrolada",
    "dificuldade para falar",
    "visao dupla",
    "perda de visao",
    "convulsao",
    "convulsoes",
    "paralisia",
    "cefaleia trovoada",
    "dor em trovoada",
)

# Respostas curtas na tela de cefaleia (sem precisar repetir "dor de cabeça").
_CEFALEIA_FLAG_ANSWERS = (
    "fraqueza",
    "fraco",
    "fraca",
    "rigidez",
    "nuca",
    "pior dor",
    "a pior",
    "subita",
    "subito",
    "de repente",
    "visao",
    "enxerg",
    "fala enrolada",
    "boca torta",
    "paralisia",
    "um lado",
    "convulsao",
    "trovoada",
)

_CEFALEIA_CLEAR_NEURO = (
    "fraqueza de um lado",
    "lado do corpo",
    "boca torta",
    "fala enrolada",
    "dificuldade para falar",
    "visao dupla",
    "perda de visao",
    "rigidez de nuca",
    "nuca dura",
    "paralisia",
    "convulsao",
)

_EMOTIONAL_HEADACHE_MARKERS = (
    "triste",
    "tristeza",
    "lembranc",
    "lembro",
    "episodio triste",
    "episódio triste",
    "chorar",
    "chorei",
    "ansios",
    "nervos",
    "estresse",
    "luto",
    "perda",
    "trauma",
    "difícil",
    "dificil",
)

_WEAKNESS_SOFT_MARKERS = (
    "cansaco",
    "cansaço",
    "cansado",
    "cansada",
    "exaust",
    "peso no corpo",
    "corpo pesado",
    "moleza",
    "prostrac",
)

_ISCHEMIC_ALARM_MARKERS = (
    "suor frio",
    "suando",
    "falta de ar",
    "dispneia",
    "aperto",
    "opressao",
    "peso no peito",
    "pressao no peito",
    "irradia",
    "irradiando",
    "mandibula",
    "braço esquerdo",
    "braco esquerdo",
)

_FINDING_TERMS: dict[str, tuple[str, ...]] = {
    "irradiacao": (
        "irradia",
        "irradiacao",
        "irradiando",
        "pro braco",
        "para o braco",
        "dor no braco",
        "braco esquerdo",
        "pescoco",
        "mandibula",
        "queixo",
        "ombro",
        "pras costas",
        "para as costas",
    ),
    "suor": ("suor", "suando", "suadeira", "diaforese"),
    "dispneia": ("falta de ar", "dispneia", "ofegante"),
    "nausea": ("enjoo", "nausea", "vomito"),
    "tontura": ("tontura", "desmaio", "sincope"),
    "peito": ("dor no peito", "dor de peito", "aperto no peito", "peito apertado"),
}

_EXPLICIT_NEGATION_PHRASES: dict[str, tuple[str, ...]] = {
    "irradiacao": (
        "nao irradia",
        "sem irradiacao",
        "sem irradia",
        "nao tem irradiacao",
        "nao sinto dor no braco",
        "nao tenho dor no braco",
        "nao vai pro braco",
        "nao vai para o braco",
        "nao irradia pro braco",
        "sem irradiacao para o braco",
        "nao sinto dor no braco",
        "nao tenho irradiacao",
    ),
    "suor": (
        "nao tenho suor",
        "nao sinto suor",
        "sem suor",
        "nao to suando",
        "nao estou suando",
        "nao ta suando",
        "nenhum suor",
        "nao suando",
        "sem suor frio",
        "nenhuma sudorese",
    ),
    "dispneia": (
        "nao tenho falta de ar",
        "sem falta de ar",
        "nao sinto falta de ar",
        "nao estou com falta de ar",
        "nao to com falta de ar",
        "nenhuma falta de ar",
    ),
    "tontura": (
        "sem desmaio",
        "sem síncope",
        "sem sincope",
        "sem tontura",
        "nao desmaiei",
        "nao tive desmaio",
        "nao tenho desmaio",
        "sem desmaiar",
        "nenhum desmaio",
    ),
    "peito": (
        "sem dor no peito",
        "sem dor de peito",
        "nao tenho dor no peito",
        "nao sinto dor no peito",
        "nao estou com dor no peito",
        "mas sem dor no peito",
        "sem aperto no peito",
    ),
}

_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:,|;|\.\s+|\be\b|\bmas\b|\bporem\b|\bporem\b)\s*")


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    sem_acento = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", sem_acento).strip()


def _has_any(normalized: str, markers: tuple[str, ...]) -> bool:
    return any(_norm(m) in normalized for m in markers)


def _false_negation_clause(clause: str) -> bool:
    """Capacidade/isolamento/dormência não são negação de sintoma."""
    if _has_any(
        clause,
        (
            "nao consigo",
            "nao alcanco",
            "nao tenho como",
            "sem ar",
        ),
    ):
        return True
    if "nao sinto o braco" in clause and "dor" not in clause:
        return True
    if "nao sinto a mao" in clause and "dor" not in clause:
        return True
    return False


def _clause_has_negation(clause: str) -> bool:
    return bool(re.search(r"\b(nao|nem|sem|nunca|nenhuma|nenhum)\b", clause))


def _denied_findings(normalized: str) -> set[str]:
    """Sintomas explicitamente negados (não, nem, sem, nunca, nenhuma)."""
    denied: set[str] = set()
    for finding, phrases in _EXPLICIT_NEGATION_PHRASES.items():
        if any(p in normalized for p in phrases):
            denied.add(finding)
    for clause in _CLAUSE_SPLIT_RE.split(normalized):
        clause = (clause or "").strip()
        if not clause or _false_negation_clause(clause):
            continue
        if not _clause_has_negation(clause):
            continue
        for finding, terms in _FINDING_TERMS.items():
            if any(t in clause for t in terms):
                denied.add(finding)
        if "braco" in clause and "dor" in clause:
            denied.add("irradiacao")
    return denied


def _is_palpavel(normalized: str) -> bool:
    return _has_any(normalized, _PALPATION_MARKERS)


def _is_pleuritica(normalized: str) -> bool:
    return _has_any(normalized, _PLEURITIC_MARKERS)


def _is_muscular_word(normalized: str) -> bool:
    return _has_any(normalized, _MUSCULAR_MARKERS)


def _is_msk(normalized: str) -> bool:
    return _is_palpavel(normalized) or _is_pleuritica(normalized) or _is_muscular_word(normalized)


def _is_ideacao(normalized: str) -> bool:
    return _has_any(normalized, _IDEACAO_MARKERS)


def _is_infarto_doubt(normalized: str) -> bool:
    """Dúvida explícita de IAM — não confundir com taquicardia («e o coração acelerado»)."""
    if _has_any(normalized, ("coracao acelerado", "coracao disparado", "coracao batendo", "palpitacao", "taquicard")):
        # Taquicardia/ansiedade sem léxico de dúvida/IAM ≠ #duvida_infarto.
        if not _has_any(
            normalized,
            (
                "infarto",
                "sera que",
                "pode ser",
                "medo de",
                "duvida",
                "acho que e",
                "estou infartando",
                "to infartando",
            ),
        ):
            return False
    return _has_any(normalized, _INFARTO_DOUBT_MARKERS)


def _is_anxiety_only_language(normalized: str) -> bool:
    return _has_any(normalized, _ANXIETY_MARKERS)


def _is_tachy_language(normalized: str) -> bool:
    return _has_any(normalized, _TACHY_MARKERS)


def _is_breathing_request(normalized: str) -> bool:
    return _has_any(normalized, _BREATHING_REQUEST_MARKERS)


def _looks_like_anxiety_reassurance(reply: str) -> bool:
    n = _norm(reply)
    return _has_any(
        n,
        (
            "so ansiedade",
            "apenas ansiedade",
            "so estresse",
            "e so nervoso",
            "nao e o coracao",
            "nao e infarto",
            "e so stress",
            "e so panico",
        ),
    )


def _is_short_greeting(normalized: str) -> bool:
    compact = normalized.strip()
    return bool(_GREETING_ONLY_RE.match(compact))


def _has_effort_narrative(normalized: str) -> bool:
    return _has_any(normalized, _EFFORT_MARKERS) or (
        "mato" in normalized and _has_any(normalized, ("rocar", "rocando", "capin", "carpir", "quintal"))
    )


def _has_mechanical_quality(normalized: str) -> bool:
    return _has_any(normalized, _MECH_QUALITY_MARKERS)


def _has_ischemic_alarm_text(normalized: str) -> bool:
    return _has_any(normalized, _ISCHEMIC_ALARM_MARKERS)


def _is_headache_complaint(normalized: str) -> bool:
    if _mentions_chest(normalized) or _mentions_abdominal(normalized):
        return False
    if _has_ischemic_alarm_text(normalized):
        return False
    return _has_any(normalized, _HEADACHE_MARKERS)


def _has_clear_neuro_deficit(normalized: str) -> bool:
    return _has_any(normalized, _CEFALEIA_CLEAR_NEURO)


def _mentions_weakness(normalized: str) -> bool:
    return _has_any(normalized, ("fraqueza", "fraco", "fraca", "frouxo", "paralisia"))


def _is_soft_tiredness(normalized: str) -> bool:
    return _has_any(normalized, _WEAKNESS_SOFT_MARKERS) and not _has_clear_neuro_deficit(normalized)


def _has_emotional_headache_context(normalized: str) -> bool:
    return _is_headache_complaint(normalized) and _has_any(normalized, _EMOTIONAL_HEADACHE_MARKERS)


def _cefaleia_answer_is_red_flag(normalized: str) -> bool:
    """Resposta na tela de cefaleia: 'fraqueza', 'rigidez', 'súbita', etc."""
    if _is_no(normalized) and not _mentions_weakness(normalized):
        return False
    if _has_clear_neuro_deficit(normalized):
        return True
    if _is_soft_tiredness(normalized):
        return False
    compact = normalized.strip()
    if compact in {"fraqueza", "fraco", "fraca", "rigidez", "subita", "subito", "sim"}:
        return True
    return _has_any(normalized, _CEFALEIA_FLAG_ANSWERS)


def _has_neuro_emergency_cluster(normalized: str) -> bool:
    if not _is_headache_complaint(normalized) and "cefaleia" not in normalized and "cabeca" not in normalized:
        return False
    if _has_clear_neuro_deficit(normalized) or _has_any(normalized, _NEURO_EMERGENCY_MARKERS):
        return True
    # Fraqueza + cefaleia SEM contexto emocional → alerta (emoção + fraqueza: esclarecer).
    if _mentions_weakness(normalized) and not _has_any(normalized, _EMOTIONAL_HEADACHE_MARKERS):
        return True
    sudden = _has_any(normalized, ("de repente", "subita", "subito", "agora ha pouco", "comecou agora"))
    worst = _has_any(normalized, ("pior dor", "insuportavel", "nunca senti", "10/10", "pior da vida"))
    return bool(sudden and worst and _is_headache_complaint(normalized))


def _is_isolated_headache(normalized: str) -> bool:
    return _is_headache_complaint(normalized) and not _has_neuro_emergency_cluster(normalized)


def _looks_like_cefaleia_reply(reply: str) -> bool:
    n = _norm(reply)
    return any(
        k in n
        for k in (
            "pior da sua vida",
            "foi aumentando",
            "lembrancas dificeis",
            "cansaco pesado",
            "sinais de alerta por agora",
            "sinto muito por essa dor",
            "caminho seguro e ligar",
        )
    )


def _is_triage_narrative(normalized: str) -> bool:
    if _is_isolated_headache(normalized):
        return False
    if _has_effort_narrative(normalized) or _has_mechanical_quality(normalized):
        return True
    return _has_any(normalized, _TRIAGE_NARRATIVE_MARKERS)


def _is_mechanical_immediate(normalized: str) -> bool:
    """Esforço + repuxo/fisgada/mau jeito → cenário B, sem pergunta extra."""
    if _has_ischemic_alarm_text(normalized) and _has_any(
        normalized, ("suor frio", "suando", "falta de ar", "aperto", "peso no peito", "opressao")
    ):
        return False
    quality = _has_mechanical_quality(normalized)
    effort = _has_effort_narrative(normalized) or "mau jeito" in normalized
    return bool(quality and effort)


def _looks_like_greeting_reply(reply: str) -> bool:
    n = _norm(reply)
    if n.startswith("oi, tudo bem") or n.startswith("ola, tudo bem"):
        return True
    if "eu sou a cardioia" in n:
        return True
    if "boas-vindas" in n or "bem-vindo" in n:
        return True
    if "pode me contar o que esta sentindo" in n and "triagem" in n:
        return True
    return False


def _mentions_chest(normalized: str) -> bool:
    """Peito positivo; «sem dor no peito» não conta como queixa torácica."""
    if "peito" in _denied_findings(normalized):
        # Ainda positivo se houver peito fora da negação (ex.: «dor no peito sem irradiação»).
        if _has_any(
            normalized,
            (
                "dor no peito",
                "aperto no peito",
                "peso no peito",
                "pressao no peito",
                "peito apertado",
                "meio do peito",
            ),
        ) and not _has_any(
            normalized,
            (
                "sem dor no peito",
                "nao tenho dor no peito",
                "nao sinto dor no peito",
                "sem aperto no peito",
            ),
        ):
            return True
        return False
    return _has_any(normalized, _CHEST_MARKERS)


def _mentions_abdominal(normalized: str) -> bool:
    return _has_any(normalized, _ABD_MARKERS)


def _mentions_numbness(normalized: str) -> bool:
    if "nao sinto dor" in normalized:
        return False
    return _has_any(normalized, _NUMBNESS_MARKERS)


def _cannot_move(normalized: str) -> bool:
    return _has_any(normalized, _CANNOT_MOVE_MARKERS)


def _cannot_reach_phone(normalized: str) -> bool:
    """Paciente isolado sem acesso ao telefone — não inclui imobilidade isolada."""
    if _has_any(normalized, _CANNOT_REACH_PHONE_MARKERS):
        return True
    phoneish = "telefone" in normalized or "celular" in normalized or "aparelho" in normalized
    blocked = _has_any(
        normalized,
        ("nao consigo", "nao alcanco", "longe", "nao tenho como", "sozinho", "sozinha"),
    )
    return bool(phoneish and blocked)


def _looks_like_isolation_reply(reply: str) -> bool:
    n = _norm(reply)
    return "ok google" in n and "ligar para 192" in n


def _has_samu(reply: str) -> bool:
    n = _norm(reply)
    return "192" in n or "samu" in n


def _reply_treats_denied_as_present(reply: str, memory: SessionMemory) -> bool:
    """True se a fala trata como presente um sintoma que o usuário negou."""
    rn = _norm(reply)
    future = bool(re.search(r"\bse (vier|aparecer|tiver|surgir|ir pro|ir para)\b", rn))
    if memory.negou_suor and re.search(r"como (voce|tu) (esta|ta|estas) com suor|(ta|esta) suando|tem suor frio", rn):
        return True
    if memory.negou_suor and "suor frio" in rn and not future and "nao precisa" not in rn:
        if "como o aperto" in rn or "como voce esta" in rn:
            return True
    if memory.negou_irradiacao and re.search(r"como voce (esta|ta) .*(braco|irradi)", rn):
        return True
    if memory.negou_dispneia and re.search(r"como voce (esta|ta) com falta de ar", rn):
        return True
    return False


def _is_numbered_questionnaire(reply: str) -> bool:
    n = _norm(reply)
    return bool(_QUESTIONNAIRE_RE.search(reply)) or "triade classica" in n


def reply_emergencia() -> str:
    return REPLY_EMERGENCIA


def reply_isolamento_sem_telefone() -> str:
    return REPLY_ISOLAMENTO


def reply_emergencia_imovel() -> str:
    return REPLY_EMERGENCIA_IMOVEL


def _reply_abd_q2(qualidade: str) -> str:
    del qualidade
    return "Esse desconforto sobe para o peito ou para as costas?"


def _is_choice_one(normalized: str) -> bool:
    return normalized in {"1", "1.", "um", "a primeira", "primeira"}


def _is_choice_two(normalized: str) -> bool:
    return normalized in {"2", "2.", "dois", "a segunda", "segunda"}


def _is_yes(normalized: str) -> bool:
    return normalized in {
        "sim",
        "s",
        "ss",
        "uhum",
        "aham",
        "isso",
        "positivo",
        "afirmativo",
        "exato",
        "isso mesmo",
        "isso ai",
        "sim.",
    } or normalized.startswith("sim,") or normalized.startswith("sim ")


def _is_no(normalized: str) -> bool:
    if normalized in {"nao", "n", "nao.", "negativo", "nada", "nada disso"}:
        return True
    # «Não, sem irradiação, sem suor frio e sem desmaio» — não limitar por length curto.
    if normalized.startswith("nao,"):
        return True
    if normalized.startswith("nao ") and _has_any(
        normalized,
        ("sem irradi", "sem suor", "sem desmaio", "sem falta", "nada disso", "nenhum", "nenhuma"),
    ):
        return True
    # Tela ECO: lista de «sem X» (≥2) sem precisar começar com «não».
    sem_hits = sum(
        1
        for p in ("sem irradi", "sem suor", "sem desmaio", "sem falta", "sem tontura")
        if p in normalized
    )
    if sem_hits >= 2 and not _has_any(normalized, ("dor no peito irradi", "peito apert", "estou com dor")):
        return True
    return False


def _is_so_peito(normalized: str) -> bool:
    return _has_any(
        normalized,
        (
            "so no peito",
            "so no meio",
            "fica no peito",
            "fica so no peito",
            "somente no peito",
            "nao irradia",
            "nao vai pro braco",
            "nao vai para o braco",
        ),
    )


def _is_med_request(normalized: str) -> bool:
    return _has_any(normalized, _MED_REQUEST_MARKERS)


def _is_human_help(normalized: str) -> bool:
    return _has_any(normalized, _HUMAN_HELP_MARKERS)


def _is_farewell(normalized: str) -> bool:
    compact = normalized.replace(",", " ").strip()
    if compact in {"tchau", "obrigado", "obrigada", "valeu", "tmj", "ate logo"}:
        return True
    return _has_any(normalized, _FAREWELL_MARKERS) and not _has_any(
        normalized, ("peito", "dor", "suor", "barriga")
    )


def _extract_local(normalized: str) -> str:
    if _has_any(
        normalized,
        (
            "boca do estomago",
            "epigastr",
            "parte de cima",
            "parte alta",
            "barriga alta",
            "em cima",
            "mais na parte de cima",
            "mais pra cima",
        ),
    ):
        return "epigastrio"
    if _has_any(
        normalized,
        (
            "baixo ventre",
            "mais para baixo",
            "mais pra baixo",
            "embaixo",
            "em baixo",
            "parte de baixo",
            "parte baixa",
        ),
    ):
        return "baixo_ventre"
    if "meio do peito" in normalized or "no meio do peito" in normalized:
        return "peito"
    if _mentions_chest(normalized) and "subindo" not in normalized:
        return "peito"
    if "costas" in normalized:
        return "costas"
    return ""


def _extract_qualidade(normalized: str) -> str:
    if _has_any(normalized, ("aperto", "apertando", "opressao", "pesado", "pressao no peito")):
        return "aperto"
    if _has_any(normalized, ("queimac", "azia")):
        return "queimacao"
    if "colica" in normalized:
        return "colica"
    if _has_any(normalized, ("pontada", "fisgada", "agulhada", "repuxo")):
        return "pontada"
    return ""


def _extract_irradiacao(normalized: str, denied: set[str] | None = None) -> str:
    denied = denied if denied is not None else _denied_findings(normalized)
    if "irradiacao" in denied or _has_any(
        normalized,
        (
            "so no meio",
            "so no peito",
            "so no meio do peito",
            "nao irradia",
            "sem irradiacao",
            "ta so no peito",
            "somente no peito",
            "fica no peito",
            "fica so no peito",
            "nao sinto dor no braco",
            "nao tenho dor no braco",
            "nao vai pro braco",
            "nao vai para o braco",
        ),
    ):
        return "nenhuma"
    if _has_any(
        normalized,
        (
            "braco",
            "pescoco",
            "mandibula",
            "queixo",
            "ombro",
        ),
    ):
        return "membro"
    if _has_any(
        normalized,
        (
            "subindo pro peito",
            "sobe pro peito",
            "subindo para o peito",
            "pro peito",
            "pra o peito",
            "para o peito",
            "pras costas",
            "para as costas",
            "pro costas",
            "irradia",
            "irradiando",
        ),
    ):
        return "tronco"
    return ""


def _extract_associados(normalized: str, denied: set[str] | None = None) -> list[str]:
    denied = denied if denied is not None else _denied_findings(normalized)
    found: list[str] = []
    if "suor" not in denied and _has_any(normalized, ("suor", "suando", "suadeira", "diaforese")):
        found.append("sudorese")
    if "nausea" not in denied and _has_any(normalized, ("enjoo", "nausea", "vomito")):
        found.append("nausea")
    if "dispneia" not in denied and _has_any(normalized, ("falta de ar", "dispneia", "ofegante")):
        found.append("dispneia")
    if "tontura" not in denied and _has_any(normalized, ("tontura", "desmaio", "sincope")):
        found.append("tontura")
    if "palpit" in normalized:
        found.append("palpitacao")
    return found


def _merge_csv(current: str, extra: list[str]) -> str:
    items = [x for x in current.split(",") if x]
    for item in extra:
        if item and item not in items:
            items.append(item)
    return ",".join(items)


def _has_assoc(memory: SessionMemory, *names: str) -> bool:
    have = set((memory.sintomas_associados or "").split(","))
    have.discard("")
    return any(name in have for name in names)


@dataclass
class SessionMemory:
    """Estado da sessão: emergência + anamnese adaptativa + matriz A/B/C."""

    emergencia_ativa: bool = False
    triagem_etapa: str = ""
    local_dor: str = ""
    qualidade: str = ""
    irradiacao: str = ""
    sintomas_associados: str = ""
    disclaimer_enviado: bool = False
    negou_irradiacao: bool = False
    negou_suor: bool = False
    negou_dispneia: bool = False
    dor_palpavel: bool = False
    dor_pleuritica: bool = False
    esforco_local: bool = False
    dor_mecanica: bool = False
    risco: str = ""
    eco_etapa: str = ""
    eco_path: bool = False


def _copy_memory(src: SessionMemory, dst: SessionMemory) -> None:
    for item in fields(SessionMemory):
        setattr(dst, item.name, getattr(src, item.name))


class ChatResult:
    """Resposta padronizada do assistente (Watson ou fallback)."""

    def __init__(
        self,
        reply: str,
        session_id: str,
        intents: list[dict[str, Any]] | None = None,
        entities: list[dict[str, Any]] | None = None,
        disclaimer: str = DISCLAIMER,
        source: str = "fallback",
        ui: dict[str, Any] | None = None,
    ) -> None:
        self.reply = reply
        self.session_id = session_id
        self.intents = intents or []
        self.entities = entities or []
        self.disclaimer = disclaimer
        self.source = source
        self.ui = ui or {}

    def to_dict(self) -> dict[str, Any]:
        from services.safety_filter import infer_ui_from_reply

        ui = self.ui or infer_ui_from_reply(self.reply, self.intents)
        return {
            "reply": self.reply,
            "session_id": self.session_id,
            "intents": self.intents,
            "entities": self.entities,
            "disclaimer": self.disclaimer,
            "source": self.source,
            "ui": ui,
        }


class LocalRuleEngine:
    """Motor de regras que replica o dialog tree do skill Watson (pt-BR)."""

    PATTERNS: list[tuple[str, tuple[str, ...]]] = [
        (
            INTENT_ABDOMINAL,
            (
                "dor na barriga",
                "dores na barriga",
                "fortes dores na barriga",
                "barriga doendo",
                "dor no estomago",
                "dor no estômago",
                "boca do estomago",
                "boca do estômago",
                "epigastr",
                "queimacao na barriga",
                "queimação na barriga",
                "queimacao forte na barriga",
                "dor abdominal",
                "dor na barriga alta",
                "parte alta da barriga",
                "azia",
            ),
        ),
        (
            INTENT_TRIAGEM,
            (
                "dor no peito",
                "dor no torax",
                "dor no tórax",
                "aperto no peito",
                "opressao",
                "opressão",
                "queimacao no peito",
                "queimação no peito",
                "dor toracica",
                "dor torácica",
                "peito doendo",
                "peito apertado",
                "peito pesado",
                "precordial",
                "retroesternal",
                "meio do peito",
                "piora quando aperto",
                "pontada na respiracao",
                "e muscular",
                "nao irradia",
                "nao tenho suor frio",
                "repuxo",
                "fisgada",
                "mau jeito",
                "costela",
                "rocar",
                "rocando",
                "carpir",
                "varrer",
            ),
        ),
        (
            INTENT_RELATAR,
            (
                "repuxo",
                "fisgada",
                "mau jeito",
                "rocar",
                "rocando o mato",
                "carpir",
                "capinar",
                "varrer",
                "puxando peso",
                "costela",
                "tomou um jeito",
            ),
        ),
        (
            INTENT_PRESSAO,
            (
                "pressao arterial",
                "pressão arterial",
                "pressao alta",
                "pressão alta",
                "hipertens",
                "minha pressao",
                "minha pressão",
                "pa sistolica",
                "pa sistólica",
                "mmhg",
                "140/90",
                "180/120",
            ),
        ),
        (
            INTENT_LEMBRETE,
            (
                "lembrar",
                "lembrete",
                "medicamento",
                "remedio",
                "remédio",
                "comprimido",
                "posologia",
                "aas",
                "atenolol",
                "enalapril",
                "losartana",
                "estatina",
            ),
        ),
        (
            INTENT_AGENDAMENTO,
            (
                "agendar",
                "marcar consulta",
                "consulta",
                "cardiologista",
                "horario",
                "horário",
                "retorno",
                "disponibilidade",
            ),
        ),
    ]

    ENTITY_SINTOMA = {
        "dor_peito": (
            "dor no peito",
            "aperto no peito",
            "opressao no peito",
            "desconforto no peito",
            "peito doendo",
            "peito pesado",
        ),
        "dispneia": ("falta de ar", "dispneia", "ofegante", "nao consigo respirar", "sufoc"),
        "sudorese": ("suor frio", "sudorese", "suando", "suadeira"),
        "irradiacao": (
            "irradia",
            "irradiando",
            "braco esquerdo",
            "braço esquerdo",
            "para o braco",
            "ombro",
            "mandibula",
            "pescoco",
        ),
        "formigamento": ("formigamento", "formigando", "parestesia"),
        "dormencia": ("dormente", "dormencia", "nao sinto o braco", "braco dormente"),
        "adormecimento": ("adormecimento", "adormecido", "braco adormecido"),
        "palpitacao": ("palpit", "coracao disparado", "taquicardia"),
        "tontura": ("tontura", "desmaio", "síncope", "sincope"),
        "nausea": ("nausea", "náusea", "enjoo", "enjôo", "vomito", "vômito"),
        "mal_estar": ("mal-estar", "mal estar", "mal estar generalizado"),
    }

    ENTITY_LOCAL = {
        "epigastrio": (
            "boca do estomago",
            "epigastr",
            "parte de cima",
            "parte alta",
            "barriga alta",
        ),
        "baixo_ventre": ("baixo ventre", "embaixo", "parte de baixo", "mais para baixo"),
        "peito": ("peito", "torax", "meio do peito"),
        "so_peito": (
            "so no peito",
            "so no meio",
            "fica no peito",
            "fica so no peito",
            "somente no peito",
        ),
        "costas": ("costas",),
        "braco": ("braco", "braço"),
        "mandibula": ("mandibula", "queixo"),
    }

    ENTITY_QUALIDADE = {
        "aperto": ("aperto", "apertando", "opressao", "pesado"),
        "queimacao": ("queimacao", "queimação", "azia"),
        "colica": ("colica", "cólica"),
        "pontada": ("pontada", "fisgada", "repuxo", "agulhada"),
    }

    ENTITY_INTENSIDADE = {
        "leve": ("leve", "fraca", "pouca"),
        "moderada": ("moderada", "media", "média"),
        "intensa": ("intensa", "forte", "muito forte", "insuportavel", "insuportável", "10/10"),
    }

    ENTITY_DURACAO = {
        "minutos": ("ha minutos", "agora ha pouco", "de repente", "subito", "comecou agora"),
        "horas": ("ha uma hora", "desde cedo", "ha horas", "de manha"),
        "dias": ("ha dias", "essa semana", "ja faz dias", "cronico"),
    }

    ENTITY_SINTOMA_ASSOCIADO = {
        "nausea": ("nausea", "enjoo", "vontade de vomitar"),
        "tontura": ("tontura", "tonto", "cabeca rodando"),
        "dispneia": ("falta de ar", "ofegante", "dispneia"),
        "palpitacao": ("palpit", "coracao disparado"),
    }

    ENTITY_GATILHO = {
        "estresse": ("estresse", "estressado", "sobrecarga", "pressao no trabalho"),
        "conflito": ("briga", "discussao", "conflito", "reuniao tensa"),
        "luto": ("luto", "perda", "falecimento"),
        "insonia_contexto": ("nao dormi", "noite em claro"),
        "memoria_triste": (
            "triste",
            "tristeza",
            "lembro",
            "lembranca",
            "lembrança",
            "episodio triste",
            "episódio triste",
        ),
    }

    ENTITY_MEDICAMENTO = (
        "aas",
        "aspirina",
        "dipirona",
        "novalgina",
        "atenolol",
        "propranolol",
        "enalapril",
        "losartana",
        "amlodipino",
        "hidroclorotiazida",
        "furosemida",
        "sinvastatina",
        "atorvastatina",
        "clopidogrel",
        "metformina",
        "insulina",
        "carvedilol",
        "espironolactona",
    )

    def classify(self, message: str, memory: SessionMemory | None = None) -> tuple[str, float, list[dict[str, Any]]]:
        raw = message
        n = _norm(message)
        denied = _denied_findings(n)
        entities = self._extract_entities(raw, n, denied)

        if _is_ideacao(n):
            return INTENT_IDEACAO_RISCO, 0.99, entities
        if _is_med_request(n):
            return INTENT_MEDICACAO, 0.99, entities
        if _is_farewell(n) and (
            not memory or memory.risco == "B" or memory.triagem_etapa in {"", "done"}
        ) and not (memory and memory.emergencia_ativa):
            return INTENT_DESPEDIDA, 0.97, entities

        if memory and memory.triagem_etapa and memory.triagem_etapa not in {"", "done"}:
            if _is_so_peito(n) or _is_no(n):
                entities.append({"entity": "local_dor", "value": "so_peito", "confidence": 0.95})
                return INTENT_NEGACAO, 0.96, entities
            if _is_yes(n):
                return INTENT_AFIRMACAO, 0.96, entities

        if _cannot_reach_phone(n):
            return INTENT_EMERGENCIA, 0.99, entities
        if _has_neuro_emergency_cluster(n):
            return INTENT_EMERGENCIA, 0.97, entities
        if _is_isolated_headache(n):
            return INTENT_CEFALEIA, 0.96, entities
        if _cannot_move(n) and (_mentions_chest(n) or _has_any(n, ("suor", "suando")) or _mentions_abdominal(n)):
            if "suor" not in denied:
                return INTENT_EMERGENCIA, 0.98, entities
        if _mentions_numbness(n):
            return INTENT_EMERGENCIA, 0.97, entities
        abd = bool(memory and str(memory.triagem_etapa or "").startswith("abd"))
        if _mentions_chest(n) and _has_any(n, _CHEST_ALARM_MARKERS) and not abd:
            # Peito + alarme no turno atual vence ECO/triagem já encerrada.
            positive_alarm = False
            if _has_any(n, ("irradia", "irradiando")) and "irradiacao" not in denied:
                positive_alarm = True
            if _has_any(n, ("suor frio", "suando")) and "suor" not in denied:
                positive_alarm = True
            if _has_any(n, ("falta de ar", "dispneia")) and "dispneia" not in denied:
                positive_alarm = True
            if _has_any(n, ("dor muito forte", "dor forte no peito")):
                positive_alarm = True
            if positive_alarm:
                return INTENT_EMERGENCIA, 0.94, entities
        if _has_any(n, _HARD_EMERGENCY_MARKERS) and not abd:
            hard_hits = [_norm(m) for m in _HARD_EMERGENCY_MARKERS if _norm(m) in n]
            only_denied_syncope = hard_hits and all(h in {"desmaio", "desmaiei"} for h in hard_hits) and (
                "tontura" in denied or "desmaio" in denied
            )
            if not only_denied_syncope:
                return INTENT_EMERGENCIA, 0.93, entities

        if memory and memory.eco_etapa == "screen_redflags":
            if _is_yes(n) or _is_no(n) or _has_any(n, ("nao sei", "talvez", "sem irradi", "sem suor", "sem desmaio")):
                return INTENT_AFIRMACAO if _is_yes(n) else INTENT_NEGACAO, 0.96, entities
            if _is_infarto_doubt(n):
                return INTENT_DUVIDA_INFARTO, 0.95, entities

        if memory and memory.eco_etapa in {"cefaleia_screen", "cefaleia_clarify"}:
            if _cefaleia_answer_is_red_flag(n) or _is_yes(n) or _is_soft_tiredness(n) or _is_no(n):
                return INTENT_CEFALEIA, 0.97, entities
            if _is_isolated_headache(n) or _has_neuro_emergency_cluster(n):
                return INTENT_CEFALEIA, 0.96, entities

        # Ansiedade/taquicardia sem peito positivo antes de narrativa genérica / dúvida IAM.
        if _is_breathing_request(n):
            return INTENT_RESPIRACAO, 0.96, entities
        if _is_tachy_language(n) and not _mentions_chest(n):
            return INTENT_TAQUICARDIA, 0.93, entities
        if _is_anxiety_only_language(n) and not _mentions_chest(n) and not _has_ischemic_alarm_text(n):
            return INTENT_ESTRESSE, 0.93, entities

        # Narrativa cotidiana (roçar, carpir, repuxo) = início de triagem, nunca saudação.
        if _is_mechanical_immediate(n):
            return INTENT_RELATAR, 0.98, entities
        if _has_effort_narrative(n) or _has_mechanical_quality(n) or _is_triage_narrative(n):
            if _is_infarto_doubt(n):
                return INTENT_DUVIDA_INFARTO, 0.97, entities
            if _mentions_abdominal(n) and not _mentions_chest(n) and not _has_mechanical_quality(n):
                return INTENT_ABDOMINAL, 0.92, entities
            return INTENT_RELATAR, 0.95, entities

        if _is_infarto_doubt(n):
            return INTENT_DUVIDA_INFARTO, 0.97, entities
        if _is_human_help(n):
            return INTENT_AJUDA_HUMANA, 0.97, entities

        if _is_short_greeting(n):
            return INTENT_SAUDACAO, 0.99, entities

        if memory and memory.triagem_etapa and memory.triagem_etapa not in {"", "done"}:
            if memory.triagem_etapa.startswith("abd"):
                return INTENT_ABDOMINAL, 0.9, entities
            if memory.triagem_etapa.startswith("peito"):
                return INTENT_TRIAGEM, 0.9, entities
            if _is_yes(n):
                return INTENT_AFIRMACAO, 0.9, entities
            if _is_no(n) or _is_so_peito(n):
                return INTENT_NEGACAO, 0.9, entities

        if _is_msk(n) and not _mentions_abdominal(n):
            return INTENT_TRIAGEM, 0.91, entities

        if _mentions_abdominal(n) and not _mentions_chest(n):
            return INTENT_ABDOMINAL, 0.92, entities

        scores: list[tuple[str, float]] = []
        for intent, keywords in self.PATTERNS:
            hits = sum(1 for kw in keywords if _norm(kw) in n)
            if hits:
                scores.append((intent, min(0.99, 0.55 + 0.12 * hits)))

        if re.search(r"\b\d{2,3}\s*/\s*\d{2,3}\b", n):
            scores.append((INTENT_PRESSAO, 0.82))

        if not scores:
            return INTENT_FALLBACK, 0.4, entities

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[0][0], scores[0][1], entities

    def _extract_entities(self, raw: str, normalized: str, denied: set[str] | None = None) -> list[dict[str, Any]]:
        denied = denied if denied is not None else _denied_findings(normalized)
        entities: list[dict[str, Any]] = []
        skip_sintoma = {
            "irradiacao": "irradiacao" in denied,
            "sudorese": "suor" in denied,
            "dispneia": "dispneia" in denied,
            "nausea": "nausea" in denied,
            "tontura": "tontura" in denied,
        }
        for value, keys in self.ENTITY_SINTOMA.items():
            if skip_sintoma.get(value):
                continue
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "sintoma", "value": value, "confidence": 0.9})
        for value, keys in self.ENTITY_LOCAL.items():
            if value == "braco" and "irradiacao" in denied:
                continue
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "local_dor", "value": value, "confidence": 0.9})
        for value, keys in self.ENTITY_QUALIDADE.items():
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "qualidade_dor", "value": value, "confidence": 0.9})
        if _is_palpavel(normalized):
            entities.append({"entity": "caracteristica_msk", "value": "palpavel", "confidence": 0.92})
        if _is_pleuritica(normalized):
            entities.append({"entity": "caracteristica_msk", "value": "pleuritica", "confidence": 0.92})
        if _is_muscular_word(normalized):
            entities.append({"entity": "caracteristica_msk", "value": "muscular", "confidence": 0.9})
        if _is_mechanical_immediate(normalized) or _has_mechanical_quality(normalized):
            entities.append({"entity": "caracteristica_msk", "value": "esforco_localizado", "confidence": 0.93})
        for value, keys in self.ENTITY_INTENSIDADE.items():
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "intensidade", "value": value, "confidence": 0.85})
        for value, keys in self.ENTITY_DURACAO.items():
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "duracao", "value": value, "confidence": 0.84})
        for value, keys in self.ENTITY_SINTOMA_ASSOCIADO.items():
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "sintoma_associado", "value": value, "confidence": 0.84})
        for value, keys in self.ENTITY_GATILHO.items():
            if any(_norm(k) in normalized for k in keys):
                entities.append({"entity": "gatilho_emocional", "value": value, "confidence": 0.84})
        if _has_any(normalized, ("irradia", "irradiando", "braco esquerdo", "mandibula")):
            entities.append({"entity": "sinal_alerta", "value": "irradiacao", "confidence": 0.9})
            entities.append({"entity": "sinais_alerta", "value": "irradiacao", "confidence": 0.9})
        if _has_any(normalized, ("suor frio", "suando frio", "diaforese")):
            entities.append({"entity": "sinal_alerta", "value": "suor_frio", "confidence": 0.9})
            entities.append({"entity": "sinais_alerta", "value": "suor_frio", "confidence": 0.9})
        if _has_any(normalized, ("desmaio", "desmaiei", "sincope")):
            entities.append({"entity": "sinal_alerta", "value": "desmaio", "confidence": 0.9})
            entities.append({"entity": "sinais_alerta", "value": "desmaio", "confidence": 0.9})
        if _has_any(normalized, ("aperto", "apertando", "opressao")):
            entities.append({"entity": "sintoma_somatico", "value": "aperto", "confidence": 0.88})
            entities.append({"entity": "sintomas_somaticos", "value": "aperto", "confidence": 0.88})
        if _has_any(normalized, ("no da garganta", "bolo na garganta", "garganta fechada")):
            entities.append({"entity": "sintoma_somatico", "value": "no_garganta", "confidence": 0.88})
            entities.append({"entity": "sintomas_somaticos", "value": "no_garganta", "confidence": 0.88})
        if _has_any(normalized, ("tensao", "tenso", "musculo travado")):
            entities.append({"entity": "sintoma_somatico", "value": "tensao", "confidence": 0.88})
            entities.append({"entity": "sintomas_somaticos", "value": "tensao", "confidence": 0.88})
        if "palpit" in normalized or "taquicard" in normalized:
            entities.append({"entity": "sintoma_somatico", "value": "palpitacao", "confidence": 0.88})
            entities.append({"entity": "sintomas_somaticos", "value": "palpitacao", "confidence": 0.88})
        if any(_norm(k) in normalized for k in _ALONE_MARKERS):
            entities.append({"entity": "contexto", "value": "isolamento", "confidence": 0.9})
        if _cannot_reach_phone(normalized):
            entities.append({"entity": "barreira_socorro", "value": "nao_alcanca_telefone", "confidence": 0.95})
        elif _cannot_move(normalized):
            entities.append({"entity": "barreira_socorro", "value": "imobilizado", "confidence": 0.95})
        for med in self.ENTITY_MEDICAMENTO:
            if med in normalized:
                entities.append({"entity": "medicamento", "value": med, "confidence": 0.9})
        pa = re.search(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b", raw)
        if pa:
            entities.append(
                {
                    "entity": "pressao_arterial",
                    "value": f"{pa.group(1)}/{pa.group(2)}",
                    "confidence": 0.95,
                }
            )
        return entities

    def _absorb(self, message: str, memory: SessionMemory) -> str:
        n = _norm(message)
        denied = _denied_findings(n)
        if "irradiacao" in denied:
            memory.negou_irradiacao = True
        elif _has_any(n, ("irradia", "irradiando", "pro braco", "para o braco", "braco esquerdo")):
            memory.negou_irradiacao = False
        if "suor" in denied:
            memory.negou_suor = True
        elif _has_any(n, ("suor frio", "suando frio", "suadeira fria")):
            memory.negou_suor = False
        if "dispneia" in denied:
            memory.negou_dispneia = True
        elif _has_any(n, ("falta de ar", "dispneia", "nao consigo respirar")):
            memory.negou_dispneia = False
        if _is_palpavel(n):
            memory.dor_palpavel = True
        if _is_pleuritica(n):
            memory.dor_pleuritica = True
        if _has_effort_narrative(n):
            memory.esforco_local = True
        if _has_mechanical_quality(n):
            memory.dor_mecanica = True

        local = _extract_local(n)
        qualidade = _extract_qualidade(n)
        irradiacao = _extract_irradiacao(n, denied)
        associados = _extract_associados(n, denied)
        if _is_choice_one(n):
            if memory.triagem_etapa == "abd_q1" and not local:
                local = "epigastrio"
            elif memory.triagem_etapa in {"abd_q2", "abd_assoc", "peito_q2"} and not irradiacao:
                irradiacao = "tronco"
            elif memory.triagem_etapa == "peito_q1" and not qualidade:
                qualidade = "aperto"
                local = local or "peito"
        if _is_choice_two(n) and memory.triagem_etapa == "abd_q1" and not local:
            local = "baixo_ventre"
        if local:
            memory.local_dor = local
        if qualidade:
            memory.qualidade = qualidade
        if irradiacao:
            memory.irradiacao = irradiacao
        if memory.negou_irradiacao:
            memory.irradiacao = "nenhuma"
        if associados:
            memory.sintomas_associados = _merge_csv(memory.sintomas_associados, associados)
        have = [x for x in (memory.sintomas_associados or "").split(",") if x]
        if memory.negou_suor:
            have = [x for x in have if x != "sudorese"]
        if memory.negou_dispneia:
            have = [x for x in have if x != "dispneia"]
        memory.sintomas_associados = ",".join(have)
        return n

    def _positive_sudorese(self, n: str, memory: SessionMemory) -> bool:
        denied = _denied_findings(n)
        if "suor" not in denied and _has_any(n, ("suor frio", "suando frio", "suadeira fria", "suando")):
            return True
        if memory.negou_suor:
            return False
        return _has_assoc(memory, "sudorese") or _has_any(n, ("suor", "suando"))

    def _positive_dispneia(self, n: str, memory: SessionMemory) -> bool:
        denied = _denied_findings(n)
        if "dispneia" not in denied and _has_any(n, ("falta de ar", "dispneia", "nao consigo respirar")):
            return True
        if memory.negou_dispneia:
            return False
        return _has_assoc(memory, "dispneia") or _has_any(n, ("falta de ar", "dispneia", "nao consigo respirar"))

    def _positive_irradiacao(self, n: str, memory: SessionMemory) -> bool:
        denied = _denied_findings(n)
        if "irradiacao" not in denied and _has_any(
            n, ("irradia", "irradiando", "pro braco", "para o braco", "braco esquerdo", "mandibula", "pescoco")
        ):
            return True
        if memory.negou_irradiacao or memory.irradiacao == "nenhuma":
            return False
        return memory.irradiacao in {"membro", "tronco"} or _has_any(
            n, ("subindo", "irradia", "braco", "mandibula", "pescoco", "pras costas")
        )

    def _is_scenario_b(self, n: str, memory: SessionMemory) -> bool:
        if self._needs_samu(n, memory):
            return False
        msk = (
            memory.dor_palpavel
            or memory.dor_pleuritica
            or memory.dor_mecanica
            or _is_msk(n)
            or _is_mechanical_immediate(n)
        )
        no_radiation = memory.negou_irradiacao or memory.irradiacao in {"", "nenhuma"}
        no_auto = not self._positive_sudorese(n, memory) and not self._positive_dispneia(n, memory)
        no_nausea = not _has_assoc(memory, "nausea")
        return bool(msk and no_radiation and no_auto and no_nausea)

    def _needs_samu(self, n: str, memory: SessionMemory) -> bool:
        sudorese = self._positive_sudorese(n, memory)
        dispneia = self._positive_dispneia(n, memory)
        tontura = _has_assoc(memory, "tontura") or (
            _has_any(n, ("tontura forte", "desmaio")) and "tontura" not in _denied_findings(n)
        )
        irradiacao = self._positive_irradiacao(n, memory)
        peito = memory.local_dor == "peito" or _mentions_chest(n)
        epigastrio = memory.local_dor == "epigastrio" or "boca do estomago" in n
        aperto = memory.qualidade == "aperto" or _has_any(n, ("aperto", "pesado", "opressao"))
        nausea = _has_assoc(memory, "nausea") or _has_any(n, ("enjoo", "nausea"))
        if _cannot_move(n) and (peito or sudorese or epigastrio):
            return True
        # Misto (MSK + suor + irradiação): A vence.
        if sudorese and irradiacao:
            return True
        if sudorese and (peito or epigastrio) and aperto:
            return True
        if (peito or epigastrio) and irradiacao and (sudorese or dispneia or nausea):
            return True
        if dispneia and (peito or epigastrio or sudorese):
            return True
        if tontura and (peito or sudorese or epigastrio):
            return True
        return False

    def _samu_reply(self, n: str, memory: SessionMemory) -> str:
        memory.emergencia_ativa = True
        abdominal = memory.local_dor == "epigastrio" or _mentions_abdominal(n) or _has_any(
            n, ("subindo", "boca do estomago")
        )
        memory.triagem_etapa = "done"
        memory.risco = "A"
        if _cannot_move(n):
            return REPLY_EMERGENCIA_IMOVEL
        if abdominal:
            return REPLY_SAMU_EPIGASTRIO
        return REPLY_EMERGENCIA

    def reply_for(
        self,
        intent: str,
        message: str,
        entities: list[dict[str, Any]],
        memory: SessionMemory | None = None,
    ) -> str:
        mem = memory or SessionMemory()
        n = self._absorb(message, mem)
        pa_entity = next((e["value"] for e in entities if e["entity"] == "pressao_arterial"), None)

        if _is_so_peito(n) or (_is_no(n) and mem.triagem_etapa in {"peito_q2", "peito_q1"}):
            mem.negou_irradiacao = True
            mem.irradiacao = "nenhuma"

        if _cannot_reach_phone(n):
            mem.emergencia_ativa = True
            mem.risco = "A"
            mem.triagem_etapa = "done"
            return REPLY_ISOLAMENTO

        if _cannot_move(n) and (
            _mentions_chest(n) or _has_any(n, ("suor", "suando")) or _mentions_abdominal(n) or mem.emergencia_ativa
        ):
            mem.emergencia_ativa = True
            mem.triagem_etapa = "done"
            mem.risco = "A"
            return REPLY_EMERGENCIA_IMOVEL

        if intent == INTENT_MEDICACAO or _is_med_request(n):
            if mem.emergencia_ativa or mem.risco == "A":
                mem.emergencia_ativa = True
                mem.triagem_etapa = "done"
                mem.risco = "A"
                return REPLY_MEDICACAO_EMERGENCIA
            return REPLY_MEDICACAO

        # Jump-equivalent: once A, stay A — exceto nova queixa de cefaleia isolada.
        if mem.emergencia_ativa or mem.risco == "A":
            if _is_isolated_headache(n) or (
                _is_headache_complaint(n) and not _has_clear_neuro_deficit(n) and _has_emotional_headache_context(n)
            ):
                mem.emergencia_ativa = False
                mem.risco = "C"
                mem.triagem_etapa = "done"
                return self._start_cefaleia(n, mem)
            mem.emergencia_ativa = True
            mem.triagem_etapa = "done"
            mem.risco = "A"
            if _cannot_reach_phone(n):
                return REPLY_ISOLAMENTO
            if _cannot_move(n):
                return REPLY_EMERGENCIA_IMOVEL
            return REPLY_EMERGENCIA_HOLD if mem.triagem_etapa == "done" else REPLY_EMERGENCIA

        if intent == INTENT_AJUDA_HUMANA or _is_human_help(n):
            if self._eco_has_red_flag(n, mem) or self._needs_samu(n, mem):
                return self._samu_reply(n, mem)
            return REPLY_AJUDA_HUMANA

        if intent == INTENT_DESPEDIDA or _is_farewell(n):
            return REPLY_DESPEDIDA

        if intent in IDEACAO_INTENTS or _is_ideacao(n):
            mem.triagem_etapa = "done"
            mem.risco = "A"
            return REPLY_IDEACAO

        if mem.eco_etapa in {"cefaleia_screen", "cefaleia_clarify"}:
            return self._continue_cefaleia(n, mem)

        if mem.eco_etapa == "screen_redflags":
            return self._continue_eco(n, mem)

        # Ansiedade/taquicardia sem peito positivo: ECO antes de #duvida_infarto.
        if intent in ECO_INTENTS or (
            (_is_anxiety_only_language(n) or _is_tachy_language(n) or _is_breathing_request(n))
            and not _mentions_chest(n)
            and not _has_effort_narrative(n)
        ):
            return self._start_eco(n, mem, intent)

        if intent == INTENT_DUVIDA_INFARTO or _is_infarto_doubt(n):
            return self._start_duvida_infarto(n, mem)

        if intent == INTENT_CEFALEIA or _is_isolated_headache(n) or _has_emotional_headache_context(n):
            return self._start_cefaleia(n, mem)

        if _has_neuro_emergency_cluster(n):
            mem.emergencia_ativa = True
            mem.risco = "A"
            mem.triagem_etapa = "done"
            mem.eco_etapa = "done"
            return REPLY_CEFALEIA_NEURO

        if intent == INTENT_EMERGENCIA:
            # Jump 192 inclusive depois do ECO (etapa done) ou anamnese em curso.
            mem.emergencia_ativa = True
            mem.risco = "A"
            mem.triagem_etapa = "done"
            mem.eco_etapa = "done"
            if _cannot_move(n):
                return REPLY_EMERGENCIA_IMOVEL
            if _mentions_numbness(n):
                return REPLY_EMERGENCIA
            if _has_neuro_emergency_cluster(n):
                return REPLY_CEFALEIA_NEURO
            return REPLY_EMERGENCIA

        etapa = mem.triagem_etapa
        if etapa and etapa not in {"", "done"}:
            return self._continue_triagem(n, mem)

        if intent in {INTENT_AFIRMACAO, INTENT_NEGACAO} and not etapa:
            return REPLY_FALLBACK

        if intent == INTENT_SAUDACAO:
            if _is_triage_narrative(n) and not _is_short_greeting(n):
                return self._start_chest(n, mem)
            mem.disclaimer_enviado = True
            return REPLY_SAUDACAO

        if intent == INTENT_ABDOMINAL or (_mentions_abdominal(n) and not _mentions_chest(n) and not _has_mechanical_quality(n)):
            return self._start_abdominal(n, mem)

        if intent in CHEST_INTENTS or _mentions_chest(n) or _is_mechanical_immediate(n) or _has_effort_narrative(n):
            return self._start_chest(n, mem)

        if intent in EMERGENCY_INTENTS:
            return self._samu_reply(n, mem)

        if intent == INTENT_PRESSAO:
            extra = ""
            if pa_entity:
                try:
                    sbp, dbp = (int(x) for x in pa_entity.split("/"))
                    if sbp >= 180 or dbp >= 120:
                        extra = (
                            f" Os valores ({pa_entity} mmHg) estão na faixa de alerta deste protótipo. "
                            "Se houver dor no peito, falta de ar ou alteração visual, liga 192."
                        )
                    elif sbp >= 140 or dbp >= 90:
                        extra = f" A leitura {pa_entity} mmHg está acima da meta habitual de consultório — leve ao cardiologista."
                    else:
                        extra = f" A leitura {pa_entity} mmHg, isolada, está em faixa habitual. Uma medida não define diagnóstico."
                except ValueError:
                    extra = ""
            return (
                "Vamos com calma na leitura da pressão. "
                "Meça após 5 minutos sentado, braço na altura do coração, e anote PAS/PAD. "
                f"Alerta deste protótipo: PAS ≥ 180, PAD ≥ 120 ou FC > 120 em repouso.{extra}"
            )

        if intent == INTENT_LEMBRETE:
            meds = [e["value"] for e in entities if e["entity"] == "medicamento"]
            med_txt = f" Vi menção a {', '.join(sorted(set(meds)))}." if meds else ""
            return (
                "Posso te ajudar a organizar o lembrete da medicação de uso contínuo."
                f"{med_txt} Horário fixo e alarme no celular ajudam. "
                "Nunca duplique a dose se esquecer a anterior — confirma com teu prescritor."
            )

        if intent == INTENT_AGENDAMENTO:
            return (
                "Pra agendar, o caminho é a central da instituição — neste protótipo não tem agenda de verdade. "
                "Leva lista de remédios, medidas de PA e exames prévios. "
                "Se a queixa for dor no peito com suor frio ou falta de ar, não agenda: liga 192."
            )

        return REPLY_FALLBACK

    def _eco_has_red_flag(self, n: str, memory: SessionMemory) -> bool:
        if self._needs_samu(n, memory):
            return True
        denied = _denied_findings(n)
        if self._positive_irradiacao(n, memory) or self._positive_sudorese(n, memory):
            return True
        # Achado «desmaio» mapeia para finding «tontura» em _denied_findings.
        if ("desmaio" in n or "desmaiei" in n) and "tontura" not in denied and "desmaio" not in denied:
            return True
        return False

    def _start_cefaleia(self, n: str, memory: SessionMemory) -> str:
        """Turn 1: empatia curta + 1–2 perguntas. Sem checklist + 192 + UBS na mesma bolha."""
        memory.emergencia_ativa = False
        memory.risco = "C"
        memory.triagem_etapa = "done"
        memory.eco_path = False

        if _has_clear_neuro_deficit(n) or (
            _has_neuro_emergency_cluster(n) and not _has_emotional_headache_context(n)
        ):
            memory.emergencia_ativa = True
            memory.risco = "A"
            memory.eco_etapa = "done"
            return REPLY_CEFALEIA_NEURO

        if _has_emotional_headache_context(n):
            if _mentions_weakness(n) and not _is_soft_tiredness(n):
                memory.eco_etapa = "cefaleia_clarify"
                memory.sintomas_associados = _merge_csv(memory.sintomas_associados, "fraqueza")
                return REPLY_CEFALEIA_EMOTION
            memory.eco_etapa = "cefaleia_screen"
            return REPLY_CEFALEIA_EMOTION_SCREEN

        memory.eco_etapa = "cefaleia_screen"
        return REPLY_CEFALEIA

    def _continue_cefaleia(self, n: str, memory: SessionMemory) -> str:
        """Turn 2+: absorve achados; não reinicia o template."""
        if _is_soft_tiredness(n) and not _has_clear_neuro_deficit(n):
            memory.eco_etapa = "done"
            memory.risco = "B"
            memory.emergencia_ativa = False
            return (
                "Entendi — parece mais um cansaço ligado ao que você está vivendo do que "
                "um déficit neurológico súbito. Descanse, hidrate-se e, se a dor ou a "
                "fraqueza piorarem ou surgirem fala/visão alteradas, ligue 192. "
                "Se o peso emocional continuar, o CVV 188 também pode acolher."
            )

        if (
            _cefaleia_answer_is_red_flag(n)
            or _has_clear_neuro_deficit(n)
            or _is_yes(n)
            or _has_any(n, ("nao sei", "talvez", "pode ser"))
        ):
            memory.emergencia_ativa = True
            memory.risco = "A"
            memory.eco_etapa = "done"
            memory.triagem_etapa = "done"
            return REPLY_CEFALEIA_NEURO

        if _is_no(n) or _has_any(
            n,
            (
                "foi aumentando",
                "aumentando",
                "aos poucos",
                "gradual",
                "ja tenho ha",
                "ja faz",
                "sem fraqueza",
                "sem rigidez",
                "nada disso",
            ),
        ):
            memory.eco_etapa = "done"
            memory.risco = "C"
            memory.emergencia_ativa = False
            return REPLY_CEFALEIA_CLEAR

        # Ambíguo na tela de alerta → preferir segurança.
        memory.emergencia_ativa = True
        memory.risco = "A"
        memory.eco_etapa = "done"
        return REPLY_CEFALEIA_NEURO

    def _start_duvida_infarto(self, n: str, memory: SessionMemory) -> str:
        """#duvida_infarto: nunca tranquiliza como ansiedade; rastreia red flags."""
        if self._eco_has_red_flag(n, memory) or self._needs_samu(n, memory):
            return self._samu_reply(n, memory)
        if _mentions_chest(n) and _has_ischemic_alarm_text(n):
            return self._samu_reply(n, memory)
        memory.eco_path = True
        memory.eco_etapa = "screen_redflags"
        memory.risco = "C"
        memory.triagem_etapa = memory.triagem_etapa or "eco_screen"
        return REPLY_DUVIDA_INFARTO

    def _start_eco(self, n: str, memory: SessionMemory, intent: str) -> str:
        """Psicossomático só depois de rastreio. Alarme → 192, sem 4-7-8."""
        if self._eco_has_red_flag(n, memory) or self._needs_samu(n, memory):
            return self._samu_reply(n, memory)
        if _mentions_chest(n) and _has_any(n, ("irradia", "suor frio", "desmaio", "falta de ar")):
            return self._samu_reply(n, memory)
        if intent == INTENT_RESPIRACAO or _is_breathing_request(n):
            # Pedido explícito de 4-7-8: ainda recusa se houver alarme no texto.
            if _has_ischemic_alarm_text(n) and _mentions_chest(n):
                return self._samu_reply(n, memory)
            memory.eco_path = True
            memory.eco_etapa = "done"
            memory.risco = memory.risco or "B"
            return REPLY_ECO_478
        memory.eco_path = True
        memory.eco_etapa = "screen_redflags"
        memory.risco = "C"
        memory.triagem_etapa = "eco_screen"
        return REPLY_ECO_SCREEN

    def _continue_eco(self, n: str, memory: SessionMemory) -> str:
        denied = _denied_findings(n)
        # Negação explícita de red flags (ex.: «Não, sem irradiação, sem suor frio e sem desmaio»).
        screen_cleared = (
            _is_no(n)
            or (memory.negou_irradiacao and memory.negou_suor)
            or (
                "irradiacao" in denied
                and "suor" in denied
                and ("tontura" in denied or "desmaio" in denied or "sem desmaio" in n)
            )
        )
        if screen_cleared and not _is_yes(n):
            memory.negou_irradiacao = memory.negou_irradiacao or "irradiacao" in denied
            memory.negou_suor = memory.negou_suor or "suor" in denied
            memory.eco_etapa = "done"
            memory.triagem_etapa = "done"
            memory.risco = "B"
            memory.emergencia_ativa = False
            return REPLY_ECO_478
        if self._eco_has_red_flag(n, memory) or self._needs_samu(n, memory) or _is_yes(n):
            # Sim / incerteza com alarme → presencial. «Não sei» também sobe.
            if _is_yes(n) or self._eco_has_red_flag(n, memory) or self._needs_samu(n, memory):
                return self._samu_reply(n, memory)
        if _has_any(n, ("nao sei", "talvez", "pode ser", "nao tenho certeza", "incerto")):
            return self._samu_reply(n, memory)
        # Resposta ambígua após rastreio de infarto → presencial.
        return self._samu_reply(n, memory)

    def _start_abdominal(self, n: str, memory: SessionMemory) -> str:
        if self._needs_samu(n, memory):
            return self._samu_reply(n, memory)
        queimacao = memory.qualidade == "queimacao" or "queimac" in n
        nausea = _has_assoc(memory, "nausea") or _has_any(n, ("enjoo", "nausea"))
        if queimacao or nausea:
            memory.triagem_etapa = "abd_assoc"
            return REPLY_ABD_QUEIMACAO_NAUSEA
        memory.triagem_etapa = "abd_q1"
        return REPLY_ABD_Q1

    def _start_chest(self, n: str, memory: SessionMemory) -> str:
        if self._needs_samu(n, memory):
            return self._samu_reply(n, memory)
        if _is_mechanical_immediate(n) or (memory.esforco_local and memory.dor_mecanica):
            memory.triagem_etapa = "done"
            memory.risco = "B"
            memory.local_dor = memory.local_dor or "peito"
            memory.dor_mecanica = True
            return REPLY_MECANICA
        if _has_effort_narrative(n) and not _is_msk(n) and not _has_mechanical_quality(n):
            memory.triagem_etapa = "peito_msk"
            memory.risco = "C"
            memory.local_dor = memory.local_dor or "peito"
            memory.esforco_local = True
            return REPLY_MSK_ESFORCO_Q
        if self._is_scenario_b(n, memory):
            memory.triagem_etapa = "done"
            memory.risco = "B"
            memory.local_dor = memory.local_dor or "peito"
            return REPLY_CENARIO_B
        memory.local_dor = memory.local_dor or "peito"
        memory.risco = "C"
        qualidade_conhecida = bool(memory.qualidade)
        if qualidade_conhecida or "meio do peito" in n:
            memory.triagem_etapa = "peito_q2"
            return REPLY_CHEST_COM_QUALIDADE
        memory.triagem_etapa = "peito_q1"
        return REPLY_CHEST_Q1

    def _continue_triagem(self, n: str, memory: SessionMemory) -> str:
        if self._needs_samu(n, memory):
            if memory.triagem_etapa.startswith("abd") or memory.local_dor == "epigastrio":
                memory.emergencia_ativa = True
                memory.triagem_etapa = "done"
                return REPLY_SAMU_EPIGASTRIO
            return self._samu_reply(n, memory)

        etapa = memory.triagem_etapa

        if etapa == "abd_q1":
            if not memory.local_dor and not memory.qualidade and not _is_yes(n) and not _is_choice_one(n) and not _is_choice_two(n):
                return REPLY_ABD_Q1
            if memory.local_dor == "baixo_ventre" and memory.qualidade == "colica" and not _has_assoc(memory, "sudorese", "dispneia"):
                memory.triagem_etapa = "done"
                return REPLY_SEM_ALARME_ABD
            memory.triagem_etapa = "abd_q2"
            return _reply_abd_q2(memory.qualidade)

        if etapa == "abd_q2":
            if _is_no(n) or memory.irradiacao == "nenhuma":
                memory.triagem_etapa = "done"
                return REPLY_SEM_ALARME_ABD
            if _is_yes(n) or memory.irradiacao in {"membro", "tronco"} or _is_choice_one(n):
                memory.emergencia_ativa = True
                memory.triagem_etapa = "done"
                return REPLY_SAMU_EPIGASTRIO
            memory.triagem_etapa = "done"
            return REPLY_SEM_ALARME_ABD

        if etapa == "abd_assoc":
            if self._positive_sudorese(n, memory) or self._positive_dispneia(n, memory):
                memory.emergencia_ativa = True
                memory.triagem_etapa = "done"
                return REPLY_SAMU_EPIGASTRIO
            if memory.local_dor == "baixo_ventre":
                memory.triagem_etapa = "done"
                return REPLY_SEM_ALARME_ABD
            if memory.local_dor == "epigastrio" or _is_choice_one(n) or _is_yes(n):
                memory.local_dor = memory.local_dor or "epigastrio"
                memory.triagem_etapa = "abd_q2"
                return _reply_abd_q2(memory.qualidade or "queimacao")
            if not memory.local_dor:
                return REPLY_ABD_QUEIMACAO_NAUSEA
            memory.triagem_etapa = "done"
            return REPLY_SEM_ALARME_ABD

        if etapa == "peito_q1":
            if not memory.qualidade and not _is_choice_one(n) and not _is_yes(n):
                memory.risco = "C"
                return REPLY_CHEST_Q1
            memory.triagem_etapa = "peito_q2"
            memory.risco = "C"
            return REPLY_CHEST_Q2

        if etapa == "peito_q2":
            if self._is_scenario_b(n, memory):
                memory.triagem_etapa = "done"
                memory.risco = "B"
                return REPLY_CENARIO_B
            if (
                memory.negou_irradiacao
                or memory.irradiacao == "nenhuma"
                or _is_no(n)
                or _is_so_peito(n)
                or "so no meio" in n
            ):
                memory.triagem_etapa = "peito_msk"
                memory.risco = "C"
                return REPLY_MSK_Q
            if memory.irradiacao in {"membro", "tronco"} or _is_yes(n) or _is_choice_one(n):
                if self._positive_sudorese(n, memory) or self._positive_dispneia(n, memory) or _has_assoc(memory, "nausea"):
                    return self._samu_reply(n, memory)
                memory.triagem_etapa = "peito_assoc"
                memory.risco = "C"
                return REPLY_AUTONOMIC_Q
            memory.triagem_etapa = "peito_msk"
            memory.risco = "C"
            return REPLY_MSK_Q

        if etapa == "peito_assoc":
            if self._needs_samu(n, memory) or _is_yes(n):
                return self._samu_reply(n, memory)
            memory.triagem_etapa = "peito_msk"
            memory.risco = "C"
            return REPLY_MSK_Q

        if etapa == "eco_screen":
            return self._continue_eco(n, memory)

        if etapa == "peito_msk":
            if self._needs_samu(n, memory):
                return self._samu_reply(n, memory)
            memory.triagem_etapa = "done"
            if memory.dor_palpavel or memory.dor_pleuritica or memory.dor_mecanica or _is_msk(n) or _is_yes(n) or _has_mechanical_quality(n):
                memory.risco = "B"
                if memory.esforco_local or memory.dor_mecanica or _has_effort_narrative(n) or _has_mechanical_quality(n):
                    return REPLY_MECANICA
                return REPLY_CENARIO_B
            memory.risco = "B"
            return REPLY_SEM_ALARME_PEITO

        return REPLY_FALLBACK


class WatsonService:
    """Fachada AssistantV2 + fallback. Mantém sessões em memória para o modo local."""

    def __init__(self) -> None:
        self._engine = LocalRuleEngine()
        self._local_sessions: set[str] = set()
        self._session_memory: dict[str, SessionMemory] = {}
        self._assistant = None
        if settings.watson_enabled:
            self._assistant = self._init_watson()
        else:
            logger.info("Watson desabilitado — usando motor de regras local.")

    def _memory(self, session_id: str) -> SessionMemory:
        mem = self._session_memory.get(session_id)
        if mem is None:
            mem = SessionMemory()
            self._session_memory[session_id] = mem
        return mem

    def _init_watson(self) -> Any | None:
        try:
            from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
            from ibm_watson import AssistantV2

            authenticator = IAMAuthenticator(settings.watson_api_key)
            assistant = AssistantV2(version=settings.watson_version, authenticator=authenticator)
            assistant.set_service_url(settings.watson_url)
            logger.info("Cliente IBM Watson Assistant v2 inicializado.")
            return assistant
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao inicializar Watson (%s). Fallback local ativo.", exc)
            return None

    @staticmethod
    def _runtime_id() -> str:
        return settings.watson_environment_id or settings.watson_assistant_id

    def create_session(self) -> str:
        if self._assistant is not None:
            try:
                response = self._assistant.create_session(assistant_id=self._runtime_id()).get_result()
                session_id = response["session_id"]
                self._session_memory[session_id] = SessionMemory()
                logger.info("Sessão Watson criada.")
                return session_id
            except Exception as exc:  # noqa: BLE001
                logger.warning("create_session Watson falhou (%s); sessão local.", exc)
        session_id = str(uuid.uuid4())
        self._local_sessions.add(session_id)
        self._session_memory[session_id] = SessionMemory()
        return session_id

    def delete_session(self, session_id: str) -> None:
        if self._assistant is not None and session_id not in self._local_sessions:
            try:
                self._assistant.delete_session(
                    assistant_id=self._runtime_id(),
                    session_id=session_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("delete_session Watson falhou: %s", exc)
        self._local_sessions.discard(session_id)
        self._session_memory.pop(session_id, None)

    def send_message(self, message: str, session_id: str | None = None) -> ChatResult:
        text = (message or "").strip()
        if not text:
            sid = session_id or self.create_session()
            return ChatResult(
                reply="Por favor, escreva uma mensagem para que eu possa orientar.",
                session_id=sid,
                intents=[],
                source="fallback",
            )

        sid = session_id or self.create_session()
        memory = self._memory(sid)
        gold = SessionMemory()
        _copy_memory(memory, gold)
        intent, confidence, entities = self._engine.classify(text, gold)
        gold_reply = self._engine.reply_for(intent, text, entities, gold)

        if self._assistant is not None and sid not in self._local_sessions:
            ctx = SessionMemory()
            _copy_memory(memory, ctx)
            self._engine._absorb(text, ctx)
            watson_result = self._send_watson(text, sid, ctx)
            if watson_result is not None:
                chosen = self._prefer_reply(text, watson_result, gold_reply, gold, memory)
                _copy_memory(gold, memory)
                return chosen
            logger.info("Watson indisponível na mensagem; usando fallback na sessão %s.", sid)

        _copy_memory(gold, memory)
        result = ChatResult(
            reply=gold_reply,
            session_id=sid,
            intents=[{"intent": intent, "confidence": round(confidence, 3)}],
            entities=entities,
            source="fallback",
        )
        return self._apply_clinical_guard(text, result, memory)

    def _watson_context(self, memory: SessionMemory) -> dict[str, Any]:
        user_defined = {
            "triagem_etapa": memory.triagem_etapa,
            "local_dor": memory.local_dor,
            "qualidade": memory.qualidade,
            "irradiacao": memory.irradiacao,
            "sintomas_associados": memory.sintomas_associados,
            "emergencia_ativa": memory.emergencia_ativa,
            "disclaimer_enviado": memory.disclaimer_enviado,
            "negou_irradiacao": memory.negou_irradiacao,
            "negou_suor": memory.negou_suor,
            "negou_dispneia": memory.negou_dispneia,
            "dor_palpavel": memory.dor_palpavel,
            "dor_pleuritica": memory.dor_pleuritica,
            "esforco_local": memory.esforco_local,
            "dor_mecanica": memory.dor_mecanica,
            "risco": memory.risco,
            "eco_etapa": memory.eco_etapa,
            "eco_path": memory.eco_path,
        }
        return {"skills": {"main skill": {"user_defined": user_defined}}}

    def _send_watson(self, text: str, session_id: str, memory: SessionMemory) -> ChatResult | None:
        try:
            raw = self._assistant.message(
                assistant_id=self._runtime_id(),
                session_id=session_id,
                input={"message_type": "text", "text": text},
                context=self._watson_context(memory),
            ).get_result()
            reply = self._join_watson_text(raw)
            intents = raw.get("output", {}).get("intents", [])
            entities = raw.get("output", {}).get("entities", [])
            result = ChatResult(
                reply=reply or "",
                session_id=session_id,
                intents=intents,
                entities=entities,
                source="watson",
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("message Watson falhou: %s", exc)
            try:
                raw = self._assistant.message(
                    assistant_id=self._runtime_id(),
                    session_id=session_id,
                    input={"message_type": "text", "text": text},
                ).get_result()
                reply = self._join_watson_text(raw)
                return ChatResult(
                    reply=reply or "",
                    session_id=session_id,
                    intents=raw.get("output", {}).get("intents", []),
                    entities=raw.get("output", {}).get("entities", []),
                    source="watson",
                )
            except Exception as exc2:  # noqa: BLE001
                logger.warning("message Watson (sem contexto) falhou: %s", exc2)
                return None

    def _prefer_reply(
        self,
        text: str,
        watson_result: ChatResult,
        gold_reply: str,
        gold: SessionMemory,
        memory: SessionMemory,
    ) -> ChatResult:
        """Usa Watson se o texto for clinicamente seguro; senão o motor local."""
        watson_result = self._apply_clinical_guard(text, watson_result, memory)
        wr = watson_result.reply or ""
        wn = _norm(wr)
        gn = _norm(gold_reply)
        tn = _norm(text)

        if _is_numbered_questionnaire(wr) or "triade classica" in wn:
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        # Cefaleia isolada: não aceitar peito Q1 nem SAMU do Watson.
        if _is_isolated_headache(tn):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            watson_result.intents = [{"intent": INTENT_CEFALEIA, "confidence": 0.96}]
            return watson_result

        # Banimento do loop de saudação: narrativa de dor/esforço nunca vira "Oi".
        if _looks_like_greeting_reply(wr) and (
            gold.risco in {"A", "B", "C"}
            or (gold.triagem_etapa and gold.triagem_etapa not in {""})
            or _is_triage_narrative(tn)
            or not _is_short_greeting(tn)
        ):
            if not _looks_like_greeting_reply(gold_reply):
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        if gold.emergencia_ativa or gold.risco == "A" or (
            _has_samu(gold_reply) and gold.risco != "B" and "nao precisa" not in gn and "nao precisa de ambulancia" not in gn
        ):
            if not _has_samu(wr) or ("?" in wr and "192" in gn and "ubs" not in wn):
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        if gold.risco in {"B", "C"} and _has_samu(wr) and not gold.emergencia_ativa:
            if "nao precisa" in gn or gold.risco == "B" or gold.risco == "C":
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        if (gold.negou_suor or gold.negou_irradiacao or gold.negou_dispneia) and _reply_treats_denied_as_present(
            wr, gold
        ):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        if _looks_like_isolation_reply(gold_reply) and not _looks_like_isolation_reply(wr):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        # Nunca aceitar tranquilização «é só ansiedade» quando o ouro é 192 ou dúvida de IAM.
        if _looks_like_anxiety_reassurance(wr) and (
            gold.risco == "A"
            or gold.emergencia_ativa
            or _has_samu(gold_reply)
            or _is_infarto_doubt(tn)
            or "duvida" in gn
        ):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        # Jump 192: não voltar para 4-7-8.
        if gold.risco == "A" or gold.emergencia_ativa:
            if "4-7-8" in wn or "inspire em 4" in wn:
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        # ECO: o skill Lite ainda pode mapear ansiedade para cenário B/MSK ou SAMU indevido.
        if gold.eco_path or gold.eco_etapa in {"screen_redflags", "done"} or "4-7-8" in gn:
            gold_eco = any(
                k in gn
                for k in (
                    "4-7-8",
                    "suor frio",
                    "luta-ou-fuga",
                    "corpo em alerta",
                    "autonomo",
                    "so ansiedade",
                    "cvv",
                    "abrata",
                    "antes de qualquer hipotese",
                )
            )
            watson_eco = any(
                k in wn
                for k in (
                    "4-7-8",
                    "suor frio",
                    "luta-ou-fuga",
                    "corpo em alerta",
                    "autonomo",
                    "so ansiedade",
                    "cvv",
                    "abrata",
                    "antes de qualquer hipotese",
                )
            )
            # Ouro ECO (tela ou 4-7-8) vence SAMU/Live errado após negação de red flags.
            if gold_eco and (not watson_eco or (_has_samu(wr) and not gold.emergencia_ativa and gold.risco != "A")):
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        # Skill LIVE (Lite) pode ficar com cópia antiga; preferir voz local atualizada.
        stale_voice = any(
            marker in wn
            for marker in (
                "visse",
                "capaz que",
                "nao peco o samu",
                "fica tranquilo",
                "postinho",
                "pois entao",
                "olha so",
                "te cuida",
                "tu vira",
                "sei o quanto e debilitante",
                "preciso avaliar alguns pontos",
                "nao tenho certeza se compreendi exatamente",
            )
        )
        if stale_voice and gold_reply.strip() and not any(
            marker in gn
            for marker in (
                "visse",
                "capaz que",
                "postinho",
                "pois entao",
                "sei o quanto e debilitante",
                "preciso avaliar alguns pontos",
            )
        ):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        # Cefaleia turn-based: ouro local vence checklist monolítico do skill LIVE.
        if gold.eco_etapa in {"cefaleia_screen", "cefaleia_clarify"} or _looks_like_cefaleia_reply(gold_reply):
            if gold_reply.strip() and (
                not _looks_like_cefaleia_reply(wr)
                or "preciso avaliar alguns pontos" in wn
                or "sei o quanto e debilitante" in wn
            ):
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        # Saudação / ECO: LIVE ainda pode devolver copy anterior sem gíria.
        if (
            "eu sou a cardioia" in wn
            and "acolhimento" in gn
            and "acolhimento" not in wn
            and gold_reply.strip()
        ):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result
        if (
            (gold.eco_path or gold.eco_etapa == "screen_redflags")
            and ("entendo o desconforto" in gn or "corpo em alerta" in gn)
            and "entendo o desconforto" not in wn
            and "corpo em alerta" not in wn
            and gold_reply.strip()
        ):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        fallbackish = (
            "capaz que" in wn
            or "qualquer outra coisa" in wn
            or "nao tenho certeza se compreendi" in wn
            or "nao peguei direito" in wn
        )
        gold_fallback = (
            "capaz que" in gn
            or "nao tenho certeza se compreendi" in gn
            or "nao peguei direito" in gn
        )
        # Preferir gold quando Watson cai em fallback genérico sem resposta específica,
        # ou quando o skill LIVE ainda devolve a voz antiga com gíria.
        if fallbackish and (not gold_fallback or ("capaz que" in wn and "capaz que" not in gn)):
            watson_result.reply = gold_reply
            watson_result.source = "fallback"
            return watson_result

        if memory.triagem_etapa and memory.triagem_etapa not in {"", "done"}:
            if not wr.strip() or fallbackish:
                watson_result.reply = gold_reply
                watson_result.source = "fallback"
                return watson_result

        # Evita disclaimer colado duas vezes.
        if gold.disclaimer_enviado or memory.disclaimer_enviado:
            if DISCLAIMER.lower() in wr.lower() and DISCLAIMER.lower() not in gold_reply.lower():
                watson_result.reply = wr.replace(DISCLAIMER, "").strip()

        if not watson_result.reply.strip():
            watson_result.reply = gold_reply
            watson_result.source = "fallback"

        if DISCLAIMER.lower() in watson_result.reply.lower():
            gold.disclaimer_enviado = True

        return watson_result

    def _apply_clinical_guard(
        self,
        text: str,
        result: ChatResult,
        memory: SessionMemory | None = None,
    ) -> ChatResult:
        n = _norm(text)
        numbness = _mentions_numbness(n)
        chest = _mentions_chest(n)
        top_intent = ""
        if result.intents:
            top_intent = str(result.intents[0].get("intent") or "")
        isolation = _cannot_reach_phone(n)

        if _looks_like_anxiety_reassurance(result.reply) and (
            _is_infarto_doubt(n) or ( _mentions_chest(n) and _has_ischemic_alarm_text(n) )
        ):
            gold = SessionMemory()
            if memory is not None:
                _copy_memory(memory, gold)
            result.reply = self._engine._start_duvida_infarto(n, gold) if _is_infarto_doubt(n) else REPLY_EMERGENCIA
            result.intents = [{"intent": INTENT_DUVIDA_INFARTO if _is_infarto_doubt(n) else INTENT_EMERGENCIA, "confidence": 0.99}]
            if memory is not None:
                _copy_memory(gold, memory)
            return result

        if _looks_like_greeting_reply(result.reply) and _is_triage_narrative(n) and not _is_short_greeting(n):
            gold = SessionMemory()
            if memory is not None:
                _copy_memory(memory, gold)
            intent, _, entities = self._engine.classify(text, gold)
            result.reply = self._engine.reply_for(intent, text, entities, gold)
            result.intents = [{"intent": intent, "confidence": 0.95}]
            if memory is not None:
                _copy_memory(gold, memory)
            return result

        if isolation:
            if not _looks_like_isolation_reply(result.reply):
                result.reply = REPLY_ISOLAMENTO
            result.intents = [{"intent": INTENT_EMERGENCIA, "confidence": 0.99}]
            if memory is not None:
                memory.emergencia_ativa = True
            return result

        if _cannot_move(n) and (chest or _has_any(n, ("suor", "suando")) or _mentions_abdominal(n)):
            rn_imovel = _norm(result.reply)
            if "fica parado" not in rn_imovel and "fique parado" not in rn_imovel:
                result.reply = REPLY_EMERGENCIA_IMOVEL
            result.intents = [{"intent": INTENT_EMERGENCIA, "confidence": 0.99}]
            if memory is not None:
                memory.emergencia_ativa = True
            return result

        if _is_numbered_questionnaire(result.reply):
            gold = SessionMemory()
            if memory is not None:
                _copy_memory(memory, gold)
            intent, _, entities = self._engine.classify(text, gold)
            result.reply = self._engine.reply_for(intent, text, entities, gold)
            if memory is not None:
                _copy_memory(gold, memory)

        force_emergency = False
        if _is_isolated_headache(n):
            force_emergency = False
        elif numbness and not chest:
            force_emergency = True
        elif top_intent == INTENT_TRIAGEM and numbness:
            force_emergency = True
        elif memory and memory.emergencia_ativa and top_intent not in {
            INTENT_MEDICACAO,
            INTENT_CEFALEIA,
        }:
            if not _is_isolated_headache(n):
                force_emergency = True

        if force_emergency:
            if not _looks_like_isolation_reply(result.reply) and not _has_samu(result.reply):
                result.reply = REPLY_EMERGENCIA_HOLD if (memory and memory.triagem_etapa == "done") else REPLY_EMERGENCIA
            result.intents = [{"intent": INTENT_EMERGENCIA, "confidence": 0.99}]
            if memory is not None:
                memory.emergencia_ativa = True
                memory.triagem_etapa = "done"
                memory.risco = "A"

        if memory and memory.emergencia_ativa and not _is_isolated_headache(n):
            rn = _norm(result.reply)
            if "?" in result.reply and "192" not in rn and "samu" not in rn:
                result.reply = REPLY_EMERGENCIA_HOLD
            if "capaz que" in rn or "nao tenho certeza se compreendi" in rn:
                result.reply = REPLY_EMERGENCIA_HOLD

        if _is_isolated_headache(n) or _has_emotional_headache_context(n):
            # Não reinicia checklist se já estamos na tela / esclarecimento.
            if memory is not None and memory.eco_etapa in {"cefaleia_screen", "cefaleia_clarify"}:
                result.intents = [{"intent": INTENT_CEFALEIA, "confidence": 0.96}]
                memory.emergencia_ativa = False
                if memory.risco != "A":
                    memory.risco = memory.risco or "C"
                return result
            if memory is not None and memory.eco_etapa == "done" and memory.risco == "A" and _has_samu(result.reply):
                return result
            if _looks_like_cefaleia_reply(result.reply):
                result.intents = [{"intent": INTENT_CEFALEIA, "confidence": 0.96}]
                if memory is not None:
                    memory.emergencia_ativa = False
                    if memory.risco != "A":
                        memory.risco = memory.risco or "C"
                    if not memory.eco_etapa:
                        memory.eco_etapa = "cefaleia_screen"
                return result
            gold = SessionMemory()
            if memory is not None:
                _copy_memory(memory, gold)
            result.reply = self._engine._start_cefaleia(_norm(text), gold)
            result.intents = [{"intent": INTENT_CEFALEIA, "confidence": 0.96}]
            if memory is not None:
                _copy_memory(gold, memory)
            return result

        if (
            force_emergency
            or top_intent == INTENT_EMERGENCIA
            or _looks_like_isolation_reply(result.reply)
            or _has_samu(result.reply)
        ):
            if memory is not None:
                memory.emergencia_ativa = True
        return result

    @staticmethod
    def _join_watson_text(payload: dict[str, Any]) -> str:
        generic = payload.get("output", {}).get("generic", []) or []
        parts: list[str] = []
        for item in generic:
            if item.get("response_type") == "text":
                parts.append(item.get("text", ""))
            elif "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(p for p in parts if p).strip()
