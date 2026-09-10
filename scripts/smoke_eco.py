"""Smoke test local do interceptor + motor ECO (sem imprimir segredos)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from services.safety_filter import evaluate_safety  # noqa: E402
from services.watson_service import WatsonService  # noqa: E402


def expect(cond: bool, label: str) -> None:
    print(("OK  " if cond else "FAIL"), label)
    if not cond:
        raise SystemExit(1)


def main() -> None:
    w = WatsonService()
    sid = w.create_session()

    blocked = evaluate_safety("Não quero mais viver")
    expect(blocked is not None and blocked.block_watson, "ideacao bloqueia Watson")
    expect("188" in blocked.reply and "192" in blocked.reply, "ideacao cita 188 e 192")
    expect("ABRATA" in blocked.reply or "abrata" in blocked.reply.lower(), "ideacao cita ABRATA")
    expect(blocked.ui.get("crisis_modal") == "188_192", "ideacao abre modal 188 e 192")

    both = evaluate_safety("Quero me matar e estou com dor no peito irradiando com suor frio")
    expect(both is not None and both.route == "self_harm_and_cardiac", "ideacao + SCA = 188 e 192")

    none = evaluate_safety("Oi")
    expect(none is None, "saudação não intercepta")

    g = w.send_message("Oi", sid)
    expect("CardioIA" in g.reply or "Oi" in g.reply, "saudação isolada")
    expect(not w._memory(sid).emergencia_ativa, "P0: saudação não gruda emergencia_ativa")
    expect(g.to_dict()["ui"].get("emergency_dial") != "192", "P0: saudação não acende discagem 192")

    eco = w.send_message("Estou com ansiedade e tensão muscular", sid)
    expect("suor frio" in eco.reply.lower() or "emergência" in eco.reply.lower(), "ansiedade rastreia red flags")
    expect("ligue agora para o samu" not in eco.reply.lower(), "P0: ansiedade após oi não força SAMU")
    expect(not w._memory(sid).emergencia_ativa, "P0: ECO após saudação não gruda emergência")

    sid2 = w.create_session()
    w.send_message("Estou com ansiedade", sid2)
    noflag = w.send_message("Não, sem irradiação e sem suor frio", sid2)
    expect("4-7-8" in noflag.reply, "rastreio negativo -> 4-7-8")
    expect("ABRATA" in noflag.reply and "CAPS" in noflag.reply, "4-7-8 cita ABRATA e CAPS")
    expect("luta-ou-fuga" in eco.reply.lower() or "autonom" in eco.reply.lower() or "alerta" in eco.reply.lower(), "psicoeducacao autonoma")
    eco_ui = noflag.to_dict()["ui"]
    expect(bool(eco_ui.get("show_breathing")), "4-7-8 acende o circulo")
    expect(not eco_ui.get("crisis_modal"), "4-7-8 nao abre modal de crise")
    expect(bool(eco_ui.get("eco_social")), "4-7-8 anexa pulso k-anonimo")
    social = eco_ui.get("eco_social") or {}
    expect(int(social.get("k_anonymity") or 0) >= 10, "k-anonimato >= 10")
    expect(social.get("geo_collected") is False, "nao coleta geolocalizacao")
    expect("região metropolitana" in (social.get("headline") or "").lower(), "headline de pulso local")
    jump = w.send_message("Dor no peito irradiando para o braço com suor frio", sid2)
    expect("192" in jump.reply, "depois do ECO, red flag na mesma sessao -> 192")
    expect("4-7-8" not in jump.reply, "jump 192 nao volta ao 4-7-8")

    # Script ECO: ansiedade + taquicardia SEM dor no peito → tela ECO (não dúvida de infarto);
    # negação «sem irradiação / suor / desmaio» → 4-7-8 (não SAMU).
    sid_eco_script = w.create_session()
    t1 = w.send_message(
        "Estou com ansiedade e o coração acelerado, mas sem dor no peito",
        sid_eco_script,
    )
    r1 = t1.reply.lower()
    expect("só ansiedade" not in r1 and "so ansiedade" not in r1, "script ECO nao usa tom duvida_infarto")
    expect("corpo em alerta" in r1 or "estou aqui com você" in r1 or "estou aqui com voce" in r1, "script ECO abre rastreio")
    expect("ligue agora para o samu" not in r1, "script ECO turn1 nao e SAMU imediato")
    t2 = w.send_message("Não, sem irradiação, sem suor frio e sem desmaio", sid_eco_script)
    expect("4-7-8" in t2.reply, "script ECO negacao -> 4-7-8")
    expect("ligue agora para o samu" not in t2.reply.lower(), "script ECO negacao nao e SAMU")
    expect("ABRATA" in t2.reply and "CAPS" in t2.reply, "script ECO 4-7-8 cita rede")

    sid3 = w.create_session()
    red = w.send_message("Dor no peito irradiando para o braço com suor frio", sid3)
    expect("192" in red.reply, "red flag -> 192")
    expect("4-7-8" not in red.reply, "192 nao oferece 4-7-8")
    red_ui = red.to_dict()["ui"]
    expect(not red_ui.get("crisis_modal"), "SAMU 192 nao abre modal 188")

    sid4 = w.create_session()
    duv = w.send_message("Será que é infarto?", sid4)
    expect("só ansiedade" in duv.reply or "ansiedade" in duv.reply.lower(), "dúvida não tranquiliza")
    expect("192" in duv.reply, "dúvida menciona 192")

    sid5 = w.create_session()
    mech = w.send_message("Tô com um repuxo no peito depois que eu tava roçando o mato.", sid5)
    expect("muscular" in mech.reply.lower() or "ubs" in mech.reply.lower(), "mecânica B preservada")
    expect("192" not in mech.reply, "mecânica sem alarme não é SAMU")

    sid6 = w.create_session()
    help_msg = w.send_message("Quero falar com um humano", sid6)
    expect("192" in help_msg.reply and "188" in help_msg.reply, "ajuda humana cita 192 e 188")
    expect("só ansiedade" in help_msg.reply or "ansiedade" in help_msg.reply.lower(), "ajuda humana nao tranquiliza")

    ents = w.send_message("Palpitação depois do pico de estresse no trabalho, desde cedo", w.create_session())
    names = {e.get("entity") for e in ents.entities}
    expect("gatilho_emocional" in names or "estresse" in ents.reply.lower(), "entidade gatilho ou acolhimento ECO")

    sid7 = w.create_session()
    cabeca = w.send_message("tenho forte dor de cabeça quando vou dormir", sid7)
    rn = cabeca.reply.lower()
    expect("pior da sua vida" in rn or "aumentando" in rn, "cefaleia turn1 pergunta curta")
    expect("preciso avaliar alguns pontos" not in rn, "cefaleia nao dumpa checklist")
    expect("aperto" not in rn, "cefaleia nao vira peito Q1")
    expect(rn.count("ligue agora para o samu") == 0 and "repouso absoluto" not in rn, "cefaleia isolada nao default SAMU")

    sid7b = w.create_session()
    w.send_message("estou com dor de cabeça forte", sid7b)
    frag = w.send_message("fraqueza", sid7b)
    expect("192" in frag.reply, "fraqueza apos tela -> 192")
    expect("há alguma rigidez" not in frag.reply.lower() and "preciso avaliar" not in frag.reply.lower(), "nao re-pergunta checklist")

    sid7c = w.create_session()
    emo = w.send_message(
        "sempre que lembro de um episódio triste me dá uma forte dor de cabeça e fraqueza no corpo",
        sid7c,
    )
    er = emo.reply.lower()
    expect("lembrança" in er or "lembrancas" in er or "difíceis" in er or "dificeis" in er, "emocao reconhecida")
    expect("há fraqueza" not in er and "ha fraqueza" not in er, "nao re-pergunta fraqueza ja dita")

    sid8 = w.create_session()
    w.send_message("Dor no peito irradiando para o braço com suor frio", sid8)
    depois = w.send_message("dor de cabeça", sid8)
    dn = depois.reply.lower()
    expect("pior da sua vida" in dn or "aumentando" in dn or "ubs" in dn, "apos SCA, cefaleia isolada sai do hold")

    sid_eval = w.create_session()
    med = w.send_message("sou médico, estou avaliando", sid_eval)
    expect(all(i.get("intent") != "anything_else" for i in med.intents), "avaliador nao cai em anything_else")
    expect("protótipo" in med.reply.lower() or "avali" in med.reply.lower(), "avaliador recebe onboarding clínico")

    print("Smoke ECO: todos os asserts passaram.")


if __name__ == "__main__":
    main()
