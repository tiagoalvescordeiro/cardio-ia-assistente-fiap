"""Atualiza skill local: cefaleia turn-based + ECO/fallback mais conversacionais."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "watson" / "cardio_assistant_skill.json"

REPLY_CEF = (
    "Sinto muito por essa dor. "
    "Ela veio de repente, como a pior da sua vida, ou foi aumentando?"
)
REPLY_NEURO = (
    "Obrigado por me falar disso — com esse sinal de alerta, o caminho seguro é "
    "ligar agora para o SAMU (192). Peça para alguém ficar com você e fique em repouso "
    "enquanto aguarda."
)
REPLY_CLEAR = (
    "Entendi — sem esses sinais de alerta por agora. "
    "Descanse, hidrate-se e, se a dor persistir ou piorar, procure a UBS."
)
REPLY_FALLBACK = (
    "Não peguei direito — pode me contar de outro jeito o que está sentindo agora? "
    "Estou aqui com você. Se for emergência, ligue 192."
)
REPLY_ECO = (
    "Estou aqui com você. Entendo o desconforto — o corpo em alerta pode reagir assim, "
    "sem isso ser um diagnóstico. "
    "Antes de qualquer hipótese de estresse: tem dor no peito indo para o braço, suor frio ou desmaio agora?"
)
REPLY_ECO_TACHY = (
    "Estou aqui com você. Entendo o desconforto — palpitação pode ser alerta do corpo, "
    "sem ser diagnóstico. "
    "A palpitação veio com dor no peito irradiando, suor frio ou desmaio?"
)
REPLY_DUVIDA = (
    "Essa dúvida é importante — e eu não vou tratar como «só ansiedade». "
    "A dor irradia para o braço, pescoço ou mandíbula? Tem suor frio ou desmaio agora? "
    "Se sim, ou se não tiver certeza, ligue 192 (SAMU)."
)


def set_text(node: dict, text: str) -> None:
    node["output"] = {
        "generic": [
            {
                "values": [{"text": text}],
                "response_type": "text",
                "selection_policy": "sequential",
            }
        ]
    }


def main() -> None:
    skill = json.loads(SKILL.read_text(encoding="utf-8"))
    nodes = [
        n
        for n in skill["dialog_nodes"]
        if n.get("dialog_node")
        not in {
            "node_cefaleia_alerta",
            "node_cefaleia_negacao",
        }
    ]
    by_id = {n.get("dialog_node"): n for n in nodes}

    cef = by_id["node_queixa_cefaleia"]
    set_text(cef, REPLY_CEF)
    cef["title"] = "Cefaleia — tela (1 pergunta)"
    cef["context"] = {
        "risco": "C",
        "emergencia_ativa": False,
        "triagem_etapa": "done",
        "eco_etapa": "cefaleia_screen",
    }

    child_alerta = {
        "type": "standard",
        "title": "Cefaleia — red flag → 192",
        "output": {
            "generic": [
                {
                    "values": [{"text": REPLY_NEURO}],
                    "response_type": "text",
                    "selection_policy": "sequential",
                }
            ]
        },
        "conditions": (
            "$eco_etapa == 'cefaleia_screen' && "
            "(#afirmacao || input.text.contains('fraqueza') || input.text.contains('rigidez') || "
            "input.text.contains('súbita') || input.text.contains('subita') || "
            "input.text.contains('pior dor') || input.text.contains('de repente') || "
            "input.text.contains('visão') || input.text.contains('visao') || "
            "input.text.contains('talvez') || input.text.contains('não sei'))"
        ),
        "dialog_node": "node_cefaleia_alerta",
        "parent": "node_queixa_cefaleia",
        "next_step": {"behavior": "get_user_input"},
        "context": {
            "emergencia_ativa": True,
            "risco": "A",
            "triagem_etapa": "done",
            "eco_etapa": "done",
        },
    }

    child_nao = {
        "type": "standard",
        "title": "Cefaleia — sem red flag → UBS",
        "output": {
            "generic": [
                {
                    "values": [{"text": REPLY_CLEAR}],
                    "response_type": "text",
                    "selection_policy": "sequential",
                }
            ]
        },
        "conditions": (
            "$eco_etapa == 'cefaleia_screen' && (#negacao || input.text.contains('aumentando') || "
            "input.text.contains('aos poucos') || input.text.contains('gradual'))"
        ),
        "dialog_node": "node_cefaleia_negacao",
        "parent": "node_queixa_cefaleia",
        "previous_sibling": "node_cefaleia_alerta",
        "next_step": {"behavior": "get_user_input"},
        "context": {
            "eco_etapa": "done",
            "risco": "C",
            "emergencia_ativa": False,
            "triagem_etapa": "done",
        },
    }

    out: list[dict] = []
    for n in nodes:
        out.append(n)
        if n.get("dialog_node") == "node_queixa_cefaleia":
            out.append(child_alerta)
            out.append(child_nao)

    for n in out:
        did = n.get("dialog_node")
        if did == "Anything else":
            set_text(n, REPLY_FALLBACK)
        elif did == "node_sintoma_ansiedade":
            set_text(n, REPLY_ECO)
        elif did == "node_sintoma_taquicardia":
            set_text(n, REPLY_ECO_TACHY)
        elif did == "node_duvida_infarto":
            set_text(n, REPLY_DUVIDA)

    skill["dialog_nodes"] = out
    SKILL.write_text(json.dumps(skill, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK skill cefaleia turns")


if __name__ == "__main__":
    main()
