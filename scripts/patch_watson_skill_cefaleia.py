"""Adiciona intent/nó de cefaleia isolada no skill local — sem publicar na IBM."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "watson" / "cardio_assistant_skill.json"

REPLY = (
    "Sinto muito que esteja com essa dor tão intensa, sei o quanto é debilitante. "
    "Para sua segurança, preciso avaliar alguns pontos: "
    "essa dor começou de repente e é a pior que você já sentiu? "
    "Há alguma rigidez na nuca, alteração visual ou fraqueza? "
    "Se houver qualquer um desses sinais, ligue 192 (SAMU) agora. "
    "Caso contrário, descanse, hidrate-se e busque uma UBS se não melhorar."
)

CONDITIONS = (
    "(#queixa_cefaleia || input.text.contains('dor de cabeça') || "
    "input.text.contains('dor de cabeca') || input.text.contains('cefaleia') || "
    "input.text.contains('enxaqueca') || input.text.contains('cabeça dói') || "
    "input.text.contains('cabeca doi')) && !input.text.contains('peito') && "
    "!input.text.contains('suor frio') && !input.text.contains('rigidez de nuca') && "
    "!input.text.contains('fala enrolada')"
)


def main() -> None:
    skill = json.loads(SKILL.read_text(encoding="utf-8"))

    intent = {
        "intent": "queixa_cefaleia",
        "description": (
            "Dor de cabeça / cefaleia isolada — triagem calma UBS; "
            "SAMU só com red flags neurológicos."
        ),
        "examples": [
            {"text": t}
            for t in (
                "tenho forte dor de cabeça quando vou dormir",
                "dor de cabeça",
                "estou com cefaleia",
                "minha cabeça dói",
                "cefaleia forte",
                "dor na cabeça há horas",
                "estou com enxaqueca",
                "cabeça doendo sem dor no peito",
            )
        ],
    }
    skill["intents"] = [i for i in skill["intents"] if i.get("intent") != "queixa_cefaleia"]
    skill["intents"].append(intent)

    node = {
        "type": "standard",
        "title": "Cefaleia isolada — triagem calma",
        "output": {
            "generic": [
                {
                    "values": [{"text": REPLY}],
                    "response_type": "text",
                    "selection_policy": "sequential",
                }
            ]
        },
        "conditions": CONDITIONS,
        "dialog_node": "node_queixa_cefaleia",
        "next_step": {"behavior": "get_user_input"},
        "previous_sibling": "node_saudacao",
        "context": {
            "risco": "C",
            "emergencia_ativa": False,
            "triagem_etapa": "done",
        },
    }

    nodes = [n for n in skill["dialog_nodes"] if n.get("dialog_node") != "node_queixa_cefaleia"]
    for n in nodes:
        if n.get("dialog_node") == "Anything else":
            n["previous_sibling"] = "node_queixa_cefaleia"
    nodes.append(node)
    skill["dialog_nodes"] = nodes

    existing = {c.get("text") for c in skill.get("counterexamples", [])}
    for text in (
        "dor de cabeça",
        "tenho forte dor de cabeça quando vou dormir",
        "estou com cefaleia",
        "minha cabeça dói",
    ):
        if text not in existing:
            skill.setdefault("counterexamples", []).append({"text": text})

    SKILL.write_text(json.dumps(skill, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("OK skill cefaleia")


if __name__ == "__main__":
    main()
