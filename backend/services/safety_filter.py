"""
Filtro de segurança pré-Watson (CardioIA + ECO).

Léxicos em português brasileiro, conservadores: na dúvida clínica,
o atendimento presencial (SAMU 192) prevalece sobre hipótese de estresse.

Dois eixos
----------
1. Ideação suicida / automutilação → **CVV 188 e SAMU 192**. Não chama Watson.
2. Red flags cardíacos (SCA/IAM) → SAMU 192.

Conflito ansiedade + isquemia
-----------------------------
Se houver linguagem de ansiedade **e** irradiação + sudorese (ou outro
alarme cardíaco), a rota é **cardíaca**. Nunca rotular possível SCA
como «só ansiedade».

Listas documentadas abaixo — ampliar com parcimônia (falsos positivos
de 188/192 são preferíveis a um falso negativo de SCA ou de crise).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

DISCLAIMER_ECO = (
    "Este assistente não substitui atendimento médico e não é dispositivo médico. "
    "Em emergências cardíacas, ligue 192 (SAMU). "
    "Em crise emocional com ideação, ligue 188 (CVV)."
)

REPLY_CVV_188 = (
    "Sua vida importa. Você não está sozinho. "
    "Ligue agora o CVV 188 (24 horas, gratuito e sigiloso) — https://cvv.org.br — "
    "e o SAMU 192 se houver qualquer dúvida médica ou risco imediato. "
    "Peça para alguém ficar ao seu lado. "
    "Rede de apoio: ABRATA (https://www.abrata.org.br) e o CAPS do seu município."
)

REPLY_CVV_E_SAMU = (
    "Há sinais de emergência médica e de crise emocional ao mesmo tempo. "
    "Ligue agora 192 (SAMU) e, em paralelo, o CVV 188 (24h, gratuito, sigiloso). "
    "Não fique sozinho. Peça para alguém ficar ao seu lado."
)

REPLY_SAMU_192 = (
    "Isso exige avaliação médica imediata. "
    "Ligue agora para o SAMU (192) ou peça para alguém te levar à emergência. "
    "Mantenha repouso absoluto. Não dirija."
)

# ---------------------------------------------------------------------------
# Léxico — ideação / automutilação (PT-BR)
# Frases compostas primeiro; tokens curtos só quando inequívocos.
# ---------------------------------------------------------------------------
SELF_HARM_PHRASES: tuple[str, ...] = (
    "quero me matar",
    "vou me matar",
    "vou acabar com tudo",
    "vou acabar comigo",
    "quero morrer",
    "nao quero mais viver",
    "nao quero viver",
    "sem vontade de viver",
    "acabar com a vida",
    "tirar a minha vida",
    "tirar minha vida",
    "tirar a vida",
    "ideacao suicida",
    "pensamento suicida",
    "pensamentos suicidas",
    "vontade de me matar",
    "me suicidar",
    "suicidio",
    "suicidar",
    "me cortar",
    "vou me cortar",
    "quero me cortar",
    "automutilacao",
    "auto mutilacao",
    "me machucar de proposito",
    "me ferir",
    "nao aguento mais viver",
    "melhor estar morto",
    "melhor estar morta",
    "plano de me matar",
    "como me matar",
)

# ---------------------------------------------------------------------------
# Léxico — red flags cardíacos (SCA / equivalente isquêmico)
# ---------------------------------------------------------------------------
CARDIAC_HARD_PHRASES: tuple[str, ...] = (
    "infarto",
    "estou infartando",
    "acho que e infarto",
    "samu",
    "ligar 192",
    "chama o samu",
    "desmaiei",
    "desmaio",
    "perdi os sentidos",
    "nao consigo respirar",
    "nao estou conseguindo respirar",
    "sufocando",
    "parada cardiaca",
    "dor muito forte no peito",
    "dor forte no peito",
)

IRRADIATION_MARKERS: tuple[str, ...] = (
    "irradia",
    "irradiando",
    "pro braco",
    "para o braco",
    "pro braco esquerdo",
    "braco esquerdo",
    "mandibula",
    "queixo",
    "pescoco",
    "pras costas",
    "para as costas",
)

DIAPHORESIS_MARKERS: tuple[str, ...] = (
    "suor frio",
    "suando frio",
    "suadeira fria",
    "diaforese",
)

CHEST_MARKERS: tuple[str, ...] = (
    "peito",
    "torax",
    "precordial",
    "retroesternal",
)

ANXIETY_MARKERS: tuple[str, ...] = (
    "ansiedade",
    "ansioso",
    "ansiosa",
    "ataque de panico",
    "crise de ansiedade",
    "so nervoso",
    "so estresse",
    "psicossomatic",
)

Route = Literal["self_harm", "self_harm_and_cardiac", "cardiac", "none"]


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    sem_acento = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", sem_acento).strip()


def _has_any(normalized: str, markers: tuple[str, ...]) -> bool:
    return any(m in normalized for m in markers)


@dataclass
class SafetyDecision:
    """Decisão do interceptor. ``block_watson`` impede a chamada à nuvem."""

    route: Route
    block_watson: bool
    reply: str
    ui: dict[str, Any] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    reason: str = ""

    def to_chat_payload(self, session_id: str) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "session_id": session_id,
            "intents": [{"intent": self._intent_name(), "confidence": 0.99}],
            "entities": [],
            "disclaimer": DISCLAIMER_ECO,
            "source": "safety_filter",
            "ui": self.ui,
            "safety": {
                "route": self.route,
                "block_watson": self.block_watson,
                "matched": self.matched,
                "reason": self.reason,
            },
        }

    def _intent_name(self) -> str:
        if self.route in {"self_harm", "self_harm_and_cardiac"}:
            return "ideacao_risco"
        if self.route == "cardiac":
            return "red_flags"
        return "anything_else"


def _has_irradiation(n: str) -> bool:
    return _has_any(n, IRRADIATION_MARKERS)


def _has_diaphoresis(n: str) -> bool:
    return _has_any(n, DIAPHORESIS_MARKERS) or (
        "suor" in n and "frio" in n and "sem suor" not in n
    )


def has_cardiac_red_flags(text: str) -> tuple[bool, list[str]]:
    """True se houver alarme de SCA. Conservador: irradiação+suor já basta."""
    n = _norm(text)
    matched: list[str] = []
    if _has_any(n, CARDIAC_HARD_PHRASES):
        matched.append("alarme_explicito")
    if _has_irradiation(n):
        matched.append("irradiacao")
    if _has_diaphoresis(n):
        matched.append("suor_frio")
    if "desmaio" in n or "desmaiei" in n:
        matched.append("desmaio")
    chest = _has_any(n, CHEST_MARKERS)

    # Irradiação + sudorese (com ou sem menção a peito) → cardíaco.
    if "irradiacao" in matched and "suor_frio" in matched:
        return True, matched
    if chest and ("irradiacao" in matched or "suor_frio" in matched or "desmaio" in matched):
        return True, matched
    if "alarme_explicito" in matched:
        return True, matched
    if "desmaio" in matched and (chest or "irradiacao" in matched or "suor_frio" in matched):
        return True, matched
    return False, matched


def has_self_harm(text: str) -> tuple[bool, list[str]]:
    n = _norm(text)
    matched = [p for p in SELF_HARM_PHRASES if p in n]
    return bool(matched), matched


def has_anxiety_language(text: str) -> bool:
    return _has_any(_norm(text), ANXIETY_MARKERS)


def evaluate_safety(text: str) -> SafetyDecision | None:
    """
    Avalia a mensagem **antes** do Watson.

    Retorna ``None`` quando a conversa pode seguir (Watson ou fallback).
    Intercepta sempre ideação; intercepta cardíaco só quando o interceptor
    precisa devolver 192 sem nuvem (ideação concorrente). Red flags
    isolados seguem para o diálogo (skill/fallback) — o fork clínico
    continua responsável pelo 192.
    """
    self_harm, harm_hits = has_self_harm(text)
    cardiac, cardio_hits = has_cardiac_red_flags(text)
    anxiety = has_anxiety_language(text)

    # Conflito: ansiedade + irradiação + suor → cardíaco (nunca «só ansiedade»).
    if anxiety and "irradiacao" in cardio_hits and "suor_frio" in cardio_hits:
        cardiac = True

    if self_harm and cardiac:
        return SafetyDecision(
            route="self_harm_and_cardiac",
            block_watson=True,
            reply=REPLY_CVV_E_SAMU,
            ui={
                "show_breathing": False,
                "crisis_modal": "188_192",
                "emergency_dial": "192",
            },
            matched=harm_hits + cardio_hits,
            reason="Ideação e linguagem de emergência cardíaca concorrentes.",
        )

    if self_harm:
        return SafetyDecision(
            route="self_harm",
            block_watson=True,
            reply=REPLY_CVV_188,
            ui={
                "show_breathing": False,
                "crisis_modal": "188_192",
                "emergency_dial": "192",
            },
            matched=harm_hits,
            reason="Léxico de ideação/automutilação — CVV 188 + SAMU 192, sem Watson.",
        )

    # Red flags isolados: não bloqueiam Watson; o diálogo decide o 192.
    return None


def _looks_like_greeting_copy(reply: str) -> bool:
    n = _norm(reply or "")
    if n.startswith("oi, tudo bem") or n.startswith("ola, tudo bem"):
        return True
    if "eu sou a cardioia" in n:
        return True
    return False


def _reply_requests_immediate_samu(reply: str) -> bool:
    """Discagem 192 só quando a fala pede SAMU agora, não no disclaimer da saudação."""
    if _looks_like_greeting_copy(reply):
        return False
    n = _norm(reply or "")
    if "192" not in n and "samu" not in n:
        return False
    return _has_any(
        n,
        (
            "ligue agora para o samu",
            "ligar agora para o samu",
            "ligue agora o samu",
            "isso exige avaliacao medica imediata",
            "se ainda nao ligou",
            "ok google",
            "ei siri",
            "caminho seguro e ligar agora",
            "ligar o 192",
            "ligar para 192",
            "ligar para o samu",
            "mantenha repouso absoluto",
            "nao dirija",
        ),
    )


def infer_ui_from_reply(reply: str, intents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Deriva hints de UI a partir da resposta (fallback/Watson).

    O modal bloqueante é só para ideação. Citar CVV 188 / ABRATA / CAPS
    na psicoeducação 4-7-8 é rede de apoio, não crise.
    """
    n = _norm(reply or "")
    intent_names = {str(i.get("intent") or "") for i in (intents or [])}
    show_breathing = "4-7-8" in (reply or "") or "478" in n or "solicitar_respiracao" in intent_names
    ideation_intent = bool(intent_names & {"ideacao_crise", "ideacao_risco"})
    # Cefaleia isolada cita 192 só como contingência — não acende discagem de crise.
    calm_headache = "queixa_cefaleia" in intent_names
    crisis_192 = _reply_requests_immediate_samu(reply) and not calm_headache
    modal = None
    if ideation_intent:
        modal = "188_192" if crisis_192 else "188"
    dial = None
    if crisis_192:
        dial = "192"
    elif ideation_intent:
        dial = "188"
    ui: dict[str, Any] = {
        "show_breathing": show_breathing,
        "crisis_modal": modal,
        "emergency_dial": dial,
    }
    if show_breathing and not modal:
        from services.eco_social import eco_social_ui

        social = eco_social_ui(True)
        if social:
            ui["eco_social"] = social
    return ui
