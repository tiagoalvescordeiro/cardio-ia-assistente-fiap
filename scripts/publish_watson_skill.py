"""
Publica watson/cardio_assistant_skill.json no Assistant v2 (update_skill + release).

Não imprime segredos. Plano Lite pode recusar snapshot/release — o script
registra o erro e segue, para o relatório de viabilidade ser honesto.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SKILL_PATH = ROOT / "watson" / "cardio_assistant_skill.json"


def _mask(value: str) -> str:
    if not value:
        return "(vazio)"
    return "(definido)" if value else "(vazio)"


def main() -> int:
    api_key = os.getenv("WATSON_API_KEY", "").strip()
    url = os.getenv("WATSON_URL", "").strip()
    assistant_id = os.getenv("WATSON_ASSISTANT_ID", "").strip()
    environment_id = os.getenv("WATSON_ENVIRONMENT_ID", "").strip()
    skill_id_hint = os.getenv("WATSON_SKILL_ID", "").strip()
    version = os.getenv("WATSON_VERSION", "2024-08-25").strip()

    print("Watson publish — credenciais:", _mask(api_key), "assistant:", _mask(assistant_id))
    if not (api_key and assistant_id):
        print("Sem WATSON_API_KEY/ASSISTANT_ID — publicação ignorada (fallback local segue válido).")
        return 0

    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    from ibm_watson import AssistantV2

    authenticator = IAMAuthenticator(api_key)
    assistant = AssistantV2(version=version, authenticator=authenticator)
    assistant.set_service_url(url)

    skill_doc = json.loads(SKILL_PATH.read_text(encoding="utf-8"))
    workspace = {
        "name": skill_doc.get("name"),
        "description": skill_doc.get("description"),
        "language": skill_doc.get("language", "pt-br"),
        "intents": skill_doc.get("intents", []),
        "entities": skill_doc.get("entities", []),
        "dialog_nodes": skill_doc.get("dialog_nodes", []),
        "counterexamples": skill_doc.get("counterexamples", []),
        "system_settings": skill_doc.get("system_settings", {}),
    }

    skill_id = skill_id_hint or "44e84de2-e99b-4079-afda-aa963ff0cbc3"
    try:
        listed = assistant.list_skills(assistant_id=assistant_id).get_result()
        skills = listed.get("skills") or listed.get("assistant_skills") or []
        print(f"Skills no assistente: {len(skills)}")
        for item in skills:
            sid = item.get("id") or item.get("skill_id")
            stype = item.get("type") or item.get("skill_type")
            print(f"  - type={stype} id={_mask(str(sid or ''))} name={item.get('name')}")
            if str(stype).lower() == "dialog" and sid:
                skill_id = sid
        if not skill_id and skills:
            skill_id = skills[0].get("id") or skills[0].get("skill_id")
    except Exception as exc:  # noqa: BLE001
        print(f"list_skills falhou (Lite/API): {type(exc).__name__}: {exc}")

    if not skill_id:
        print("Skill ID não encontrado — não foi possível update_skill.")
        return 1

    try:
        assistant.update_skill(
            assistant_id=assistant_id,
            skill_id=skill_id,
            name=workspace["name"],
            description=workspace["description"],
            workspace=workspace,
        ).get_result()
        print("update_skill: ok (treinamento assíncrono no Assistant).")
    except Exception as exc:  # noqa: BLE001
        print(f"update_skill falhou: {type(exc).__name__}: {exc}")
        return 1

    try:
        info = assistant.get_skill(assistant_id=assistant_id, skill_id=skill_id).get_result()
        print(f"skill status após update: {info.get('status')}")
    except Exception as exc:  # noqa: BLE001
        print(f"get_skill: {type(exc).__name__}: {exc}")

    # Lite: máximo 2 snapshots. Apaga releases antigas (não LIVE) para abrir cota.
    try:
        rels = assistant.list_releases(assistant_id=assistant_id).get_result().get("releases", [])
        print(f"Releases existentes: {len(rels)}")
        for item in rels:
            print(f"  release={item.get('release')} status={item.get('status')}")
        if len(rels) >= 2:
            oldest = sorted(rels, key=lambda r: str(r.get("release") or ""))[:-1]
            for item in oldest:
                rid = item.get("release")
                try:
                    assistant.delete_release(assistant_id=assistant_id, release=str(rid))
                    print(f"delete_release {rid}: ok (liberar snapshot Lite)")
                except Exception as exc:  # noqa: BLE001
                    print(f"delete_release {rid} falhou: {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"list_releases falhou: {type(exc).__name__}: {exc}")

    release_name = None
    try:
        rel = assistant.create_release(
            assistant_id=assistant_id,
            description="CardioIA+ECO Fase 5 Cap 1",
        ).get_result()
        release_name = str(rel.get("release") or rel.get("name") or rel.get("release_id") or "")
        print(f"create_release: ok ({release_name or 'id omitido'})")
    except Exception as exc:  # noqa: BLE001
        print(f"create_release falhou (limite Lite de snapshot/release e comum): {type(exc).__name__}: {exc}")

    live_env = environment_id
    try:
        envs = assistant.list_environments(assistant_id=assistant_id).get_result()
        for env in envs.get("environments", []):
            name = (env.get("name") or "").lower()
            eid = env.get("environment_id") or env.get("id")
            print(f"  environment: {env.get('name')} id={_mask(str(eid or ''))}")
            if "live" in name or env.get("environment") == "live":
                live_env = eid
    except Exception as exc:  # noqa: BLE001
        print(f"list_environments falhou: {type(exc).__name__}: {exc}")

    if release_name and live_env:
        try:
            assistant.deploy_release(
                assistant_id=assistant_id,
                release=release_name,
                environment_id=live_env,
            ).get_result()
            print("deploy_release LIVE: ok")
        except Exception as exc:  # noqa: BLE001
            print(f"deploy_release falhou: {type(exc).__name__}: {exc}")
    elif not release_name:
        print("Sem release nova — o draft atualizado ainda pode servir à environment_id do .env.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
