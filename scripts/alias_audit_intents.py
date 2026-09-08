"""Acrescenta aliases de intent/entidade do briefing de auditoria sem quebrar o skill."""

from __future__ import annotations

import json
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "watson" / "cardio_assistant_skill.json"


def _examples(*texts: str) -> list[dict[str, str]]:
    return [{"text": t} for t in texts]


NEW_INTENTS = [
    {
        "intent": "sintoma_cardiaco",
        "description": "Alias de #sintoma_peito / #triagem_dor_peito.",
        "examples": _examples(
            "Sintoma cardíaco, aperto no peito",
            "Acho que é o coração, dor no peito",
            "Queixa cardíaca agora",
            "Desconforto cardíaco no peito",
        ),
    },
    {
        "intent": "red_flags",
        "description": "Alias de #alerta_emergencia — jump SAMU 192.",
        "examples": _examples(
            "Red flag, suor frio e irradiação",
            "Alarme cardíaco com desmaio",
            "Sinais de alerta, peito e suor frio",
        ),
    },
    {
        "intent": "estresse_ansiedade",
        "description": "Alias de #sintoma_ansiedade — rastreio antes de psicoeducação.",
        "examples": _examples(
            "Estresse e ansiedade",
            "Sobrecarga, palpitação de nervoso",
            "Ansiedade por excesso de trabalho",
            "Tensão de estresse sem suor frio",
        ),
    },
    {
        "intent": "ideacao_risco",
        "description": "Alias de #ideacao_crise. Backend intercepta 188+192.",
        "examples": _examples(
            "Estou em risco, quero morrer",
            "Ideação de risco",
            "Risco de me machucar",
        ),
    },
]

NEW_ENTITIES = [
    {
        "entity": "sinais_alerta",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "irradiacao",
                "synonyms": ["irradia", "irradiando", "braço esquerdo", "mandíbula"],
            },
            {
                "type": "synonyms",
                "value": "suor_frio",
                "synonyms": ["suor frio", "suando frio", "diaforese"],
            },
            {
                "type": "synonyms",
                "value": "desmaio",
                "synonyms": ["desmaio", "desmaiei", "síncope"],
            },
        ],
    },
    {
        "entity": "sintomas_somaticos",
        "fuzzy_match": True,
        "values": [
            {"type": "synonyms", "value": "aperto", "synonyms": ["aperto", "opressão"]},
            {"type": "synonyms", "value": "no_garganta", "synonyms": ["nó na garganta"]},
            {"type": "synonyms", "value": "tensao", "synonyms": ["tensão muscular"]},
            {"type": "synonyms", "value": "palpitacao", "synonyms": ["palpitação", "taquicardia"]},
        ],
    },
]


def _or_into(conditions: str, extra: str) -> str:
    if extra in conditions:
        return conditions
    return f"({conditions}) || ({extra})"


def main() -> None:
    skill = json.loads(SKILL.read_text(encoding="utf-8"))
    have_i = {i["intent"] for i in skill["intents"]}
    for intent in NEW_INTENTS:
        if intent["intent"] not in have_i:
            skill["intents"].append(intent)

    have_e = {e["entity"] for e in skill["entities"]}
    for ent in NEW_ENTITIES:
        if ent["entity"] not in have_e:
            skill["entities"].append(ent)

    replacements = {
        "node_ideacao_crise": "#ideacao_risco || #ideacao_crise",
        "node_emergencia_cardio": "#red_flags || #alerta_emergencia",
        "node_peito_start": "#sintoma_cardiaco || #sintoma_peito",
        "node_sintoma_ansiedade": "#estresse_ansiedade || #sintoma_ansiedade",
        "node_duvida_infarto_sim": "@sinais_alerta || @sinal_alerta",
        "node_duvida_infarto_nao": "!@sinais_alerta && !@sinal_alerta",
        "node_sintoma_taquicardia": "!@sinais_alerta && !@sinal_alerta",
        "node_solicitar_respiracao": "!@sinais_alerta && !@sinal_alerta",
        "node_saudacao": "!#sintoma_cardiaco && !#red_flags && !#estresse_ansiedade && !#ideacao_risco",
    }

    for node in skill["dialog_nodes"]:
        nid = node.get("dialog_node")
        cond = node.get("conditions") or ""
        if nid == "node_ideacao_crise" and "#ideacao_risco" not in cond:
            node["conditions"] = _or_into(cond, "#ideacao_risco")
            node["output"]["generic"][0]["values"][0]["text"] = (
                "Sua vida importa. Você não está sozinho. Ligue agora o CVV 188 "
                "(https://cvv.org.br) e o SAMU 192. Rede de apoio: ABRATA e o CAPS do município."
            )
        elif nid == "node_emergencia_cardio" and "#red_flags" not in cond:
            node["conditions"] = _or_into(cond, "#red_flags")
        elif nid == "node_peito_start" and "#sintoma_cardiaco" not in cond:
            node["conditions"] = _or_into(cond, "#sintoma_cardiaco && !$emergencia_ativa")
        elif nid == "node_sintoma_ansiedade" and "#estresse_ansiedade" not in cond:
            node["conditions"] = _or_into(cond, "#estresse_ansiedade && !$emergencia_ativa && !@sinal_alerta && !@sinais_alerta")
            node["output"]["generic"][0]["values"][0]["text"] = (
                "Estou aqui com você. Palpitação e aperto situacional podem ser a resposta "
                "autonômica de luta-ou-fuga — compartilhada pelo corpo, sem ser diagnóstico. "
                "Antes de qualquer hipótese de estresse, precisamos afastar emergência. "
                "Você está com dor no peito que vai para o braço, suor frio ou desmaio agora?"
            )
        elif nid == "node_solicitar_respiracao":
            if "@sinais_alerta" not in cond:
                node["conditions"] = cond.replace("!@sinal_alerta", "!@sinal_alerta && !@sinais_alerta")
            node["output"]["generic"][0]["values"][0]["text"] = (
                "Por agora não vi sinal que peça o SAMU na hora. "
                "Faça a respiração 4-7-8: inspire 4, segure 7, expire 8. "
                "Rede de apoio: CVV 188, ABRATA e o CAPS do município. "
                "Se aparecer irradiação, suor frio ou desmaio, ligue 192."
            )
        elif nid == "node_duvida_infarto_sim" and "@sinais_alerta" not in cond:
            node["conditions"] = cond.replace("@sinal_alerta", "@sinal_alerta || @sinais_alerta")
        elif nid == "node_duvida_infarto_nao" and "@sinais_alerta" not in cond:
            node["conditions"] = cond.replace("!@sinal_alerta", "!@sinal_alerta && !@sinais_alerta")
            node["output"]["generic"][0]["values"][0]["text"] = (
                "Por agora não vi sinal que peça o SAMU. A respiração 4-7-8 é prática física. "
                "Rede: CVV 188, ABRATA e CAPS. Se surgir irradiação, suor frio ou desmaio, 192."
            )
        elif nid == "node_saudacao":
            extra = " && !#sintoma_cardiaco && !#red_flags && !#estresse_ansiedade && !#ideacao_risco"
            if "#sintoma_cardiaco" not in cond:
                node["conditions"] = cond + extra
        elif nid == "node_sintoma_taquicardia" and "@sinais_alerta" not in cond:
            node["conditions"] = cond.replace("!@sinal_alerta", "!@sinal_alerta && !@sinais_alerta")

    del replacements  # silence unused if refactor
    SKILL.write_text(json.dumps(skill, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Aliases ok: {len(skill['intents'])} intents, {len(skill['entities'])} entities")


if __name__ == "__main__":
    main()
