"""Injeta intents, entidades e nós ECO no skill clássico — sem apagar a triagem A/B/C."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "watson" / "cardio_assistant_skill.json"


def _examples(*texts: str) -> list[dict[str, str]]:
    return [{"text": t} for t in texts]


def _text_node(
    dialog_node: str,
    title: str,
    conditions: str,
    text: str,
    previous_sibling: str | None,
    *,
    jump: str | None = None,
    context: dict | None = None,
    never_return: bool = False,
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
        "next_step": (
            {"behavior": "jump_to", "dialog_node": jump, "selector": "user_input"}
            if jump
            else {"behavior": "get_user_input"}
        ),
    }
    if previous_sibling:
        node["previous_sibling"] = previous_sibling
    if context:
        node["context"] = context
    if never_return:
        node["digress_out"] = "allow_all_never_return"
    return node


NEW_INTENTS = [
    {
        "intent": "sintoma_peito",
        "description": "Alias ECO de #triagem_dor_peito — aperto/dor torácica (não salta para ansiedade).",
        "examples": _examples(
            "Estou com aperto no peito",
            "Dor no peito agora",
            "Meu peito está apertado",
            "Desconforto no meio do peito",
            "Sinto um peso no peito",
            "Aperto no peito sem suor",
            "Peito apertado desde de manhã",
        ),
    },
    {
        "intent": "sintoma_taquicardia",
        "description": "Palpitação / coração disparado. Sempre rastreia red flags antes de 4-7-8.",
        "examples": _examples(
            "Estou com taquicardia",
            "Meu coração está disparado",
            "Palpitação forte",
            "Coração acelerado em repouso",
            "Sinto o coração batendo muito forte",
            "Taquicardia e tensão",
            "Palpitações à noite",
        ),
    },
    {
        "intent": "sintoma_ansiedade",
        "description": "Queixa psicossomática sem alarme cardíaco confirmado.",
        "examples": _examples(
            "Estou com ansiedade",
            "Acho que é crise de ansiedade",
            "Não consigo dormir de tão tenso",
            "Nó na garganta e tensão muscular",
            "Ataque de pânico",
            "Estou muito ansioso",
            "Insônia e músculo travado",
        ),
    },
    {
        "intent": "duvida_infarto",
        "description": "Medo/dúvida de IAM. Nunca tranquilizar como ansiedade; rastrear red flags.",
        "examples": _examples(
            "Será que é infarto?",
            "Acho que estou infartando",
            "Pode ser infarto?",
            "Tenho medo de ser o coração",
            "Isso é um infarto?",
            "Será que é o coração?",
            "Dúvida se é infarto",
        ),
    },
    {
        "intent": "alerta_emergencia",
        "description": "Alias ECO de #emergencia_cardio — jump SAMU 192.",
        "examples": _examples(
            "É emergência, suor frio e falta de ar",
            "Chama o SAMU",
            "Dor no peito irradiando com suor frio",
            "Desmaiei com dor no peito",
            "Não consigo respirar e o peito aperta",
        ),
    },
    {
        "intent": "solicitar_respiracao",
        "description": "Pedido de 4-7-8. Bloqueado se houver red flag cardíaco.",
        "examples": _examples(
            "Quero fazer a respiração 4-7-8",
            "Me ajuda a respirar",
            "Exercício de respiração",
            "Técnica 4-7-8",
            "Pode me guiar na respiração",
            "Quero o 4-7-8",
        ),
    },
    {
        "intent": "ideacao_crise",
        "description": "Ideação suicida / automutilação. CVV 188. Backend intercepta antes do Watson.",
        "examples": _examples(
            "Quero me matar",
            "Não quero mais viver",
            "Pensamentos suicidas",
            "Vou me cortar",
            "Ideação suicida",
            "Quero morrer",
        ),
    },
]

NEW_ENTITIES = [
    {
        "entity": "sinal_alerta",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "irradiacao",
                "synonyms": [
                    "irradia",
                    "irradiando",
                    "irradiação",
                    "para o braço",
                    "braço esquerdo",
                    "mandíbula",
                    "pescoço",
                ],
            },
            {
                "type": "synonyms",
                "value": "suor_frio",
                "synonyms": ["suor frio", "suando frio", "diaforese", "suadeira fria"],
            },
            {
                "type": "synonyms",
                "value": "desmaio",
                "synonyms": ["desmaio", "desmaiei", "síncope", "perdi os sentidos"],
            },
        ],
    },
    {
        "entity": "sintoma_somatico",
        "fuzzy_match": True,
        "values": [
            {
                "type": "synonyms",
                "value": "aperto",
                "synonyms": ["aperto", "apertando", "opressão", "peso no peito"],
            },
            {
                "type": "synonyms",
                "value": "no_garganta",
                "synonyms": ["nó na garganta", "bolo na garganta", "garganta fechada"],
            },
            {
                "type": "synonyms",
                "value": "tensao",
                "synonyms": ["tensão", "tensão muscular", "músculo travado", "corpo tenso"],
            },
            {
                "type": "synonyms",
                "value": "palpitacao",
                "synonyms": ["palpitação", "palpitações", "coração disparado", "taquicardia"],
            },
        ],
    },
]


def _relink(nodes: list[dict], node_id: str, new_prev: str) -> None:
    for node in nodes:
        if node.get("dialog_node") == node_id:
            node["previous_sibling"] = new_prev
            return
    raise KeyError(node_id)


def _find(nodes: list[dict], node_id: str) -> dict:
    for node in nodes:
        if node.get("dialog_node") == node_id:
            return node
    raise KeyError(node_id)


def patch(skill: dict) -> dict:
    existing = {i["intent"] for i in skill["intents"]}
    for intent in NEW_INTENTS:
        if intent["intent"] not in existing:
            skill["intents"].append(intent)

    existing_ent = {e["entity"] for e in skill["entities"]}
    for ent in NEW_ENTITIES:
        if ent["entity"] not in existing_ent:
            skill["entities"].append(ent)

    nodes = skill["dialog_nodes"]
    already = {n["dialog_node"] for n in nodes}
    if "node_ideacao_crise" in already:
        skill["description"] = (
            "Skill CardioIA + ECO — triagem A/B/C, fork psicossomático, 192/188, 4-7-8."
        )
        return skill

    _relink(nodes, "node_isolamento_sem_telefone", "node_ideacao_crise")

    ideacao = _text_node(
        "node_ideacao_crise",
        "ECO — ideação / CVV 188",
        "#ideacao_crise || input.text.contains('quero me matar') || input.text.contains('não quero mais viver') || input.text.contains('quero morrer')",
        "Sua vida importa. Você não está sozinho. Procure agora o CVV — ligue 188 (24 horas, gratuito e sigiloso) ou acesse https://cvv.org.br. Se também houver dor no peito com suor frio ou desmaio, ligue 192 (SAMU).",
        "node_aplica_negacoes",
        never_return=True,
        context={"emergencia_ativa": True, "triagem_etapa": "done", "risco": "A"},
    )

    _relink(nodes, "node_peito_q2_so_peito_root", "node_duvida_infarto")
    duvida = _text_node(
        "node_duvida_infarto",
        "ECO — dúvida de infarto (nunca «só ansiedade»)",
        "#duvida_infarto && !$emergencia_ativa",
        "Essa dúvida é importante — e eu não vou tratar como «só ansiedade». Me diga com clareza: a dor irradia para o braço, pescoço ou mandíbula? Tem suor frio ou desmaio agora? Se qualquer um desses sinais estiver presente, ou se você não tiver certeza, ligue 192 (SAMU) agora.",
        "node_emergencia_cardio",
        context={"eco_etapa": "screen_redflags", "eco_path": True, "risco": "C", "triagem_etapa": "eco_screen"},
    )
    duvida_sim = _text_node(
        "node_duvida_infarto_sim",
        "Dúvida infarto — sim/incerto → SAMU",
        "$eco_etapa == 'screen_redflags' && (#afirmacao || @sinal_alerta || input.text.contains('talvez') || input.text.contains('não sei'))",
        "Na dúvida, o atendimento presencial vem primeiro. Ligue agora para o SAMU (192). Mantenha repouso absoluto.",
        "node_duvida_infarto",
        jump="node_emergencia_hold",
        never_return=True,
        context={"emergencia_ativa": True, "risco": "A", "triagem_etapa": "done", "eco_etapa": "done"},
    )
    # previous_sibling of node_dor_mecanica already set to node_duvida_infarto;
    # children of duvida need parent, not root sibling. Keep sim as sibling after duvida
    # and insert before mecanica by updating mecanica prev to duvida_sim? 
    # Safer: duvida_sim is child of duvida.
    duvida_sim["parent"] = "node_duvida_infarto"
    duvida_sim.pop("previous_sibling", None)
    duvida_nao = _text_node(
        "node_duvida_infarto_nao",
        "Dúvida infarto — red flags negados → 4-7-8 com ressalva",
        "$eco_etapa == 'screen_redflags' && #negacao && !@sinal_alerta",
        "Por agora não vi sinal que peça o SAMU na hora — isso não descarta avaliação presencial se a dúvida persistir. Se quiser, faça a respiração 4-7-8: inspire em 4, segure em 7, expire em 8. Se aparecer irradiação, suor frio ou desmaio, ligue 192 imediatamente.",
        None,  # type: ignore[arg-type]
        context={"eco_etapa": "done", "risco": "B", "triagem_etapa": "done"},
    )
    duvida_nao["parent"] = "node_duvida_infarto"
    duvida_nao["previous_sibling"] = "node_duvida_infarto_sim"

    _relink(nodes, "node_saudacao", "node_solicitar_respiracao")
    eco_ans = _text_node(
        "node_sintoma_ansiedade",
        "ECO — ansiedade (rastreio antes de psicoeducação)",
        "#sintoma_ansiedade && !$emergencia_ativa && !@sinal_alerta",
        "Estou aqui com você. O corpo responde ao estresse com taquicardia, aperto e tensão — é a resposta neurobiológica de alerta, não um diagnóstico. Antes de qualquer hipótese de ansiedade, precisamos afastar sinais de emergência. Você está com dor no peito que vai para o braço, suor frio ou desmaio agora?",
        "node_agendamento_consulta",
        context={"eco_path": True, "eco_etapa": "screen_redflags", "risco": "C", "triagem_etapa": "eco_screen"},
    )
    eco_taq = _text_node(
        "node_sintoma_taquicardia",
        "ECO — taquicardia (rastreio primeiro)",
        "#sintoma_taquicardia && !$emergencia_ativa && !@sinal_alerta",
        "Estou aqui com você. Palpitação pode ser resposta de alerta do sistema nervoso — sem ser diagnóstico. Antes, precisamos afastar emergência cardíaca. A palpitação veio com dor no peito irradiando, suor frio ou desmaio?",
        "node_sintoma_ansiedade",
        context={"eco_path": True, "eco_etapa": "screen_redflags", "risco": "C", "triagem_etapa": "eco_screen"},
    )
    eco_resp = _text_node(
        "node_solicitar_respiracao",
        "ECO — 4-7-8 (bloqueado se red flag)",
        "#solicitar_respiracao && !$emergencia_ativa && !@sinal_alerta && $risco != 'A'",
        "Por agora não vi sinal que peça o SAMU na hora — isso não descarta avaliação presencial se a dúvida persistir. Se quiser, faça a respiração 4-7-8: inspire em 4, segure em 7, expire em 8. Se aparecer irradiação, suor frio ou desmaio, ligue 192 imediatamente.",
        "node_sintoma_taquicardia",
        context={"eco_path": True, "eco_etapa": "done"},
    )

    # #sintoma_peito e #alerta_emergencia entram nas condições já existentes.
    peito = _find(nodes, "node_peito_start")
    peito["conditions"] = f"({peito['conditions']}) || (#sintoma_peito && !$emergencia_ativa)"

    emerg = _find(nodes, "node_emergencia_cardio")
    emerg["conditions"] = f"({emerg['conditions']}) || #alerta_emergencia"

    saud = _find(nodes, "node_saudacao")
    saud["conditions"] = (
        saud["conditions"]
        + " && !#sintoma_peito && !#sintoma_ansiedade && !#sintoma_taquicardia"
        + " && !#duvida_infarto && !#alerta_emergencia && !#solicitar_respiracao && !#ideacao_crise"
    )

    fallback = _find(nodes, "Anything else")
    fallback["output"]["generic"][0]["values"][0]["text"] = (
        "Capaz que vamos deixar passar — me conta de outro jeito o que está sentindo. "
        "Posso orientar triagem de dor no peito, acolhimento de estresse e respiração 4-7-8. "
        "Se for emergência cardíaca, liga 192 (SAMU). Em crise emocional com ideação, 188 (CVV)."
    )

    insert_at = next(i for i, n in enumerate(nodes) if n["dialog_node"] == "node_isolamento_sem_telefone")
    nodes.insert(insert_at, ideacao)

    insert_mec = next(i for i, n in enumerate(nodes) if n["dialog_node"] == "node_dor_mecanica")
    nodes.insert(insert_mec, duvida)
    # children after parent
    insert_after_duvida = next(i for i, n in enumerate(nodes) if n["dialog_node"] == "node_duvida_infarto") + 1
    nodes.insert(insert_after_duvida, duvida_sim)
    nodes.insert(insert_after_duvida + 1, duvida_nao)

    insert_sau = next(i for i, n in enumerate(nodes) if n["dialog_node"] == "node_saudacao")
    nodes.insert(insert_sau, eco_ans)
    nodes.insert(insert_sau + 1, eco_taq)
    nodes.insert(insert_sau + 2, eco_resp)

    skill["description"] = (
        "Skill CardioIA + ECO — triagem A/B/C, fork psicossomático, jump 192, CVV 188, 4-7-8."
    )
    skill["name"] = "CardioIA Assistente Cardiológico + ECO"
    return skill


def main() -> None:
    skill = json.loads(SKILL.read_text(encoding="utf-8"))
    patched = patch(skill)
    SKILL.write_text(json.dumps(patched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Skill atualizado: {SKILL} ({len(patched['intents'])} intents, {len(patched['dialog_nodes'])} nós)")


if __name__ == "__main__":
    main()
