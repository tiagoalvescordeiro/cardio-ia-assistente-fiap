"""Completa intents/entidades da rubrica FIAP no skill local — sem publicar na IBM."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "watson" / "cardio_assistant_skill.json"


def _examples(*texts: str) -> list[dict[str, str]]:
    return [{"text": t} for t in texts]


def _node(
    dialog_node: str,
    title: str,
    conditions: str,
    text: str,
    previous_sibling: str,
    context: dict | None = None,
) -> dict:
    node: dict = {
        "type": "standard",
        "title": title,
        "output": {
            "generic": [
                {
                    "values": [{"text": text}],
                    "response_type": "text",
                    "selection_policy": "sequential",
                }
            ]
        },
        "conditions": conditions,
        "dialog_node": dialog_node,
        "next_step": {"behavior": "get_user_input"},
        "previous_sibling": previous_sibling,
        "context": context or {},
    }
    return node


PAD: dict[str, list[str]] = {
    "sintoma_cardiaco": [
        "Relato de desconforto no peito agora",
        "Sintoma no peito que parece do coração",
        "Queixa de peso no peito, sem diagnóstico",
    ],
    "red_flags": [
        "Irradiação para o braço com suor frio agora",
        "Desmaio e aperto no peito ao mesmo tempo",
        "Mandíbula doendo com suor frio e peito apertado",
    ],
    "estresse_ansiedade": [
        "Palpitação depois do pico de estresse no trabalho",
        "Coração acelerado após briga, sem suor frio",
        "Ansiedade e tensão depois de uma reunião pesada",
    ],
    "ideacao_risco": [
        "Estou em risco emocional e não quero seguir",
        "Preciso de ajuda humana, pensamentos de me machucar",
        "Risco agora, quero apoio do CVV",
    ],
    "alerta_emergencia": [
        "Peito apertando, irradia para a mandíbula, suando frio",
    ],
    "sintoma_peito": [
        "Relato de dor no peito para triagem",
    ],
}


NEW_INTENTS = [
    {
        "intent": "relatar_dor_peito",
        "description": "Alias de #triagem_dor_peito / #sintoma_peito — relato explícito de dor torácica.",
        "examples": _examples(
            "Quero relatar dor no peito",
            "Vim relatar um aperto torácico",
            "Preciso contar que estou com dor no peito",
            "Relato de dor no meio do peito agora",
            "Estou relatando desconforto torácico",
            "Quero registrar essa dor no peito",
            "Cheguei para relatar aperto no peito",
        ),
    },
    {
        "intent": "pedir_ajuda_humana",
        "description": "Pedido de atendimento humano (não é saudação). Encaminha 192/188/UBS — sem tranquilizar.",
        "examples": _examples(
            "Quero falar com um humano",
            "Preciso de um médico de verdade",
            "Pode me passar para um atendente",
            "Quero atendimento humano agora",
            "Me transfere para alguém da equipe",
            "Preciso falar com um profissional de saúde",
            "Não quero só o robô, quero uma pessoa",
        ),
    },
]


NEW_ENTITIES = [
    {
        "entity": "duracao",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "minutos",
                "synonyms": ["há minutos", "agora há pouco", "de repente", "súbito", "começou agora"],
            },
            {
                "type": "synonyms",
                "value": "horas",
                "synonyms": ["há uma hora", "desde cedo", "há horas", "de manhã"],
            },
            {
                "type": "synonyms",
                "value": "dias",
                "synonyms": ["há dias", "essa semana", "já faz dias", "cronico", "crônico"],
            },
        ],
    },
    {
        "entity": "sintoma_associado",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "nausea",
                "synonyms": ["náusea", "enjoo", "enjôo", "vontade de vomitar"],
            },
            {
                "type": "synonyms",
                "value": "tontura",
                "synonyms": ["tontura", "tonto", "cabeça rodando"],
            },
            {
                "type": "synonyms",
                "value": "dispneia",
                "synonyms": ["falta de ar", "ofegante", "dispneia"],
            },
            {
                "type": "synonyms",
                "value": "palpitacao",
                "synonyms": ["palpitação", "coração disparado"],
            },
        ],
    },
    {
        "entity": "gatilho_emocional",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "estresse",
                "synonyms": ["estresse", "estressado", "sobrecarga", "pressão no trabalho"],
            },
            {
                "type": "synonyms",
                "value": "conflito",
                "synonyms": ["briga", "discussão", "conflito", "reunião tensa"],
            },
            {
                "type": "synonyms",
                "value": "luto",
                "synonyms": ["luto", "perda", "falecimento"],
            },
            {
                "type": "synonyms",
                "value": "insonia_contexto",
                "synonyms": ["não dormi", "noite em claro", "insônia por preocupação"],
            },
        ],
    },
]


HELP_COPY = (
    "Claro — este canal é triagem inicial, não substitui pessoa. "
    "Se for emergência cardíaca (aperto, irradiação, suor frio, desmaio), ligue 192 agora. "
    "Se for crise emocional com ideação, ligue 188 (CVV). "
    "Fora disso, UBS, CAPS ou o plantão da instituição. "
    "Na dúvida entre estresse e coração, o presencial vem primeiro — nunca «é só ansiedade»."
)


def _upsert_intent(intents: list[dict], name: str, payload: dict) -> None:
    for item in intents:
        if item.get("intent") == name:
            return
    intents.append(payload)


def _pad_examples(intents: list[dict]) -> None:
    for item in intents:
        name = item.get("intent")
        extra = PAD.get(name) or []
        seen = {ex.get("text") for ex in item.get("examples") or []}
        for text in extra:
            if text not in seen:
                item.setdefault("examples", []).append({"text": text})
                seen.add(text)


def _upsert_entity(entities: list[dict], payload: dict) -> None:
    name = payload["entity"]
    for item in entities:
        if item.get("entity") == name:
            return
    entities.append(payload)


def _ensure_node(nodes: list[dict], node: dict) -> None:
    nid = node["dialog_node"]
    if any(n.get("dialog_node") == nid for n in nodes):
        return
    # Insert before Anything else.
    idx = next((i for i, n in enumerate(nodes) if n.get("dialog_node") == "Anything else"), len(nodes))
    nodes.insert(idx, node)


def main() -> None:
    data = json.loads(SKILL.read_text(encoding="utf-8"))
    intents = data.setdefault("intents", [])
    entities = data.setdefault("entities", [])
    nodes = data.setdefault("dialog_nodes", [])

    for payload in NEW_INTENTS:
        _upsert_intent(intents, payload["intent"], payload)
    _pad_examples(intents)
    for payload in NEW_ENTITIES:
        _upsert_entity(entities, payload)

    help_node = _node(
        "node_pedir_ajuda_humana",
        "Pedido de atendimento humano",
        "#pedir_ajuda_humana && !$emergencia_ativa",
        HELP_COPY,
        "node_solicitar_respiracao",
        context={"pedido_humano": True},
    )
    _ensure_node(nodes, help_node)

    for node in nodes:
        if node.get("dialog_node") == "node_saudacao":
            node["previous_sibling"] = "node_pedir_ajuda_humana"
            cond = node.get("conditions") or ""
            if "#relatar_dor_peito" not in cond:
                cond += " && !#relatar_dor_peito && !#pedir_ajuda_humana"
            node["conditions"] = cond
        if node.get("dialog_node") == "node_peito_start":
            cond = node.get("conditions") or ""
            if "#relatar_dor_peito" not in cond:
                node["conditions"] = cond + " || (#relatar_dor_peito && !$emergencia_ativa)"
        if node.get("dialog_node") == "node_sintoma_ansiedade":
            cond = node.get("conditions") or ""
            if "@gatilho_emocional" not in cond:
                node["conditions"] = (
                    cond + " || (#estresse_ansiedade && @gatilho_emocional && !$emergencia_ativa && !@sinal_alerta)"
                )

    # Importability guard: next_step.behavior must remain get_user_input or jump_to.
    for node in nodes:
        step = node.get("next_step") or {}
        if step and step.get("behavior") not in {"get_user_input", "jump_to", "skip_user_input"}:
            step["behavior"] = "get_user_input"
            node["next_step"] = step

    SKILL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {i["intent"]: len(i.get("examples") or []) for i in intents}
    thin = {k: v for k, v in counts.items() if v < 5}
    print("Skill patched.", SKILL)
    print("Thin intents (<5):", thin or "none")
    print("New entities present:", [e["entity"] for e in entities if e["entity"] in {"duracao", "sintoma_associado", "gatilho_emocional"}])


if __name__ == "__main__":
    main()
