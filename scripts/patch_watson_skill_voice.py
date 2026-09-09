"""Atualiza tom CardioIA no skill local: acolhimento + triagem, sem gíria regional."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "watson" / "cardio_assistant_skill.json"

REPLACEMENTS: dict[str, str] = {
    (
        "Olha só, fica calmo que eu tô aqui contigo, visse? Não tenta levantar de vez "
        "se estiver tonto. Tenta o comando de voz: diga em voz alta \"Ok Google, ligar "
        "para 192\" ou \"Eí Siri, ligar para o SAMU\". Se o aparelho estiver longe, "
        "chama um vizinho e não faz esforço."
    ): (
        "Estou aqui com você. Não tente levantar de vez se estiver tonto. "
        "Use o comando de voz: diga em voz alta \"Ok Google, ligar para 192\" "
        "ou \"Ei Siri, ligar para o SAMU\". Se o aparelho estiver longe, "
        "chame alguém próximo e não faça esforço."
    ),
    (
        "Olha só, fica parado e não tenta fazer esforço, visse? Isso exige avaliação "
        "médica imediata. Usa o comando de voz do celular agora pra chamar o "
        "**192 (SAMU)** ou grita por socorro pra quem estiver perto. Mantenha "
        "repouso absoluto."
    ): (
        "Fique parado e não tente fazer esforço. Isso exige avaliação médica imediata. "
        "Use o comando de voz do celular agora para ligar o **192 (SAMU)** "
        "ou peça socorro a quem estiver perto. Mantenha repouso absoluto."
    ),
    (
        "Não posso indicar medicação por aqui. Para sua segurança, não tome nada por "
        "conta própria agora; procure o postinho ou a emergência para avaliação. "
        "Isso exige avaliação médica imediata. Ligue agora para o SAMU (192) ou peça "
        "para alguém te levar à emergência. Mantenha repouso absoluto."
    ): (
        "Não posso indicar medicação por aqui. Para sua segurança, não tome nada por "
        "conta própria agora; procure a UBS ou a emergência para avaliação. "
        "Isso exige avaliação médica imediata. Ligue agora para o SAMU (192) ou peça "
        "para alguém levá-lo à emergência. Mantenha repouso absoluto."
    ),
    (
        "Mantenha repouso absoluto. Se ainda não ligou, ligue agora para o SAMU (192). "
        "Não faz esforço e não dirige."
    ): (
        "Mantenha repouso absoluto. Se ainda não ligou, ligue agora para o SAMU (192). "
        "Não faça esforço e não dirija."
    ),
    (
        "Não posso indicar medicação por aqui. Para sua segurança, não tome nada por "
        "conta própria agora; procure o postinho ou a emergência para avaliação."
    ): (
        "Não posso indicar medicação por aqui. Para sua segurança, não tome nada por "
        "conta própria agora; procure a UBS ou a emergência para avaliação."
    ),
    (
        "Tudo certo então. Fica em repouso e, se a dor voltar ou piorar, procura a UBS, "
        "combinado? Te cuida!"
    ): (
        "Tudo certo. Fique em repouso e, se a dor voltar ou piorar, procure a UBS. "
        "Cuide-se."
    ),
    (
        "Pois então, compreendi certinho. Como esse repuxo começou logo depois do "
        "esforço roçando o quintal e dói mais quando você vira o corpo, isso tem toda "
        "a característica de dor muscular, e não de um evento no coração. Fica "
        "tranquilo, visse? Mantém repouso e, se não melhorar nos próximos dias, "
        "procura o postinho do seu bairro."
    ): (
        "Compreendi. Como esse repuxo começou logo depois do esforço e dói mais quando "
        "você vira o corpo, isso tem característica de dor muscular — sem ser um "
        "diagnóstico. Mantenha repouso e, se não melhorar nos próximos dias, procure "
        "a UBS."
    ),
    "Essa dor piora quando tu vira o tronco ou respira fundo?": (
        "Essa dor piora quando você vira o tronco ou respira fundo?"
    ),
    "Tá com suor frio ou falta de ar agora?": (
        "Você está com suor frio ou falta de ar agora?"
    ),
    (
        "Capaz que vamos deixar passar — me conta de outro jeito o que está sentindo. "
        "Posso orientar triagem de dor no peito, acolhimento de estresse e respiração "
        "4-7-8. Se for emergência cardíaca, liga 192 (SAMU). Em crise emocional com "
        "ideação, 188 (CVV)."
    ): (
        "Não tenho certeza se compreendi exatamente o seu sintoma. Você poderia me "
        "explicar com outras palavras o que está sentindo no momento? Estou aqui para "
        "orientar sobre dores no peito, ansiedade ou lembrar de medicações. Se for uma "
        "emergência, não hesite em ligar 192."
    ),
    (
        "Entendi a dor de cabeça — por agora, isolada, não peço o SAMU. Me diga: ela "
        "começou de repente e é a pior da sua vida? Tem rigidez de nuca, fraqueza de um "
        "lado, fala enrolada ou alteração visual? Se algum desses sinais estiver "
        "presente, ligue 192. Caso contrário, repouse, hidrate e, se persistir ou "
        "piorar, procure a UBS."
    ): (
        "Sinto muito que esteja com essa dor tão intensa, sei o quanto é debilitante. "
        "Para sua segurança, preciso avaliar alguns pontos: essa dor começou de "
        "repente e é a pior que você já sentiu? Há alguma rigidez na nuca, alteração "
        "visual ou fraqueza? Se houver qualquer um desses sinais, ligue 192 (SAMU) "
        "agora. Caso contrário, descanse, hidrate-se e busque uma UBS se não melhorar."
    ),
    (
        "Oi, tudo bem? Eu sou a CardioIA — triagem inicial, sem diagnosticar e sem "
        "receitar. Pode me contar o que está sentindo.\n\nEste assistente não "
        "substitui atendimento médico. Em emergências, ligue 192 (SAMU)."
    ): (
        "Olá, tudo bem? Eu sou a CardioIA — triagem e acolhimento inicial, sem "
        "diagnosticar e sem receitar. Pode me contar o que está sentindo.\n\n"
        "Este assistente não substitui atendimento médico. Em emergências, ligue "
        "192 (SAMU)."
    ),
    (
        "Oi. Eu sou a CardioIA — triagem inicial, sem diagnosticar e sem receitar. "
        "Pode me contar o que está sentindo.\n\nEste assistente não substitui "
        "atendimento médico. Em emergências, ligue 192 (SAMU)."
    ): (
        "Olá. Eu sou a CardioIA — triagem e acolhimento inicial, sem diagnosticar e "
        "sem receitar. Pode me contar o que está sentindo.\n\nEste assistente não "
        "substitui atendimento médico. Em emergências, ligue 192 (SAMU)."
    ),
    (
        "Estou aqui com você. Palpitação e aperto situacional podem ser a resposta "
        "autonômica de luta-ou-fuga — compartilhada pelo corpo, sem ser diagnóstico. "
        "Antes de qualquer hipótese de estresse, precisamos afastar emergência. Você "
        "está com dor no peito que vai para o braço, suor frio ou desmaio agora?"
    ): (
        "Estou aqui com você. Entendo o desconforto. Palpitação e aperto situacional "
        "podem ser a mesma resposta do corpo — o sistema nervoso autônomo em "
        "luta-ou-fuga — e isso é compartilhado, não um diagnóstico. Antes de qualquer "
        "hipótese de estresse, precisamos afastar sinais de emergência. Você está com "
        "dor no peito que vai para o braço, suor frio ou desmaio agora?"
    ),
    (
        "Estou aqui com você. Palpitação pode ser resposta de alerta do sistema "
        "nervoso — sem ser diagnóstico. Antes, precisamos afastar emergência "
        "cardíaca. A palpitação veio com dor no peito irradiando, suor frio ou "
        "desmaio?"
    ): (
        "Estou aqui com você. Entendo o desconforto. Palpitação pode ser resposta de "
        "alerta do sistema nervoso — sem ser diagnóstico. Antes, precisamos afastar "
        "emergência cardíaca. A palpitação veio com dor no peito irradiando, suor "
        "frio ou desmaio?"
    ),
    (
        "Por agora não vi sinal que peça o SAMU na hora. Faça a respiração 4-7-8: "
        "inspire 4, segure 7, expire 8. Rede de apoio: CVV 188, ABRATA e o CAPS do "
        "município. Se aparecer irradiação, suor frio ou desmaio, ligue 192."
    ): (
        "Por agora não identifiquei sinal que peça o SAMU na hora — isso não descarta "
        "avaliação presencial se a dúvida persistir. A respiração 4-7-8 (inspire 4, "
        "segure 7, expire 8) é prática física, não tratamento. Rede de apoio: CVV "
        "188, ABRATA e o CAPS do município. Se aparecer irradiação, suor frio ou "
        "desmaio, ligue 192."
    ),
}

OLD_EMERG = "Ligue agora para o SAMU (192) ou peça para alguém te levar à emergência."
NEW_EMERG = "Ligue agora para o SAMU (192) ou peça para alguém levá-lo à emergência."

SLANG_MARKERS = (
    "visse",
    "capaz que",
    "postinho",
    "tu vira",
    "tá com",
    "pois então",
    "olha só",
    "te cuida",
    "tô aqui",
    "não faz esforço",
)


def main() -> None:
    skill = json.loads(SKILL.read_text(encoding="utf-8"))
    count = 0
    for node in skill["dialog_nodes"]:
        if node.get("dialog_node") == "node_despedida" and node.get("title") == "Despedida regional":
            node["title"] = "Despedida"
        for generic in (node.get("output") or {}).get("generic") or []:
            for value in generic.get("values") or []:
                text = value.get("text")
                if not text:
                    continue
                if text in REPLACEMENTS:
                    value["text"] = REPLACEMENTS[text]
                    count += 1
                elif OLD_EMERG in text:
                    value["text"] = text.replace(OLD_EMERG, NEW_EMERG)
                    count += 1

    slang_hits: list[tuple[str, str]] = []
    for node in skill["dialog_nodes"]:
        for generic in (node.get("output") or {}).get("generic") or []:
            for value in generic.get("values") or []:
                text = value.get("text") or ""
                low = text.lower()
                if any(marker in low for marker in SLANG_MARKERS):
                    slang_hits.append((str(node.get("dialog_node")), text[:140]))

    SKILL.write_text(json.dumps(skill, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK skill voice — replaced {count} texts; remaining slang={len(slang_hits)}")
    for node_id, snippet in slang_hits:
        print(f"  - {node_id}: {snippet}")


if __name__ == "__main__":
    main()
