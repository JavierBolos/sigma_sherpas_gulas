import os
import re
import json
from openai import OpenAI


PRIORITY_LABELS = {
    "education": "educación",
    "retirement": "jubilación",
    "housing": "vivienda",
    "security": "seguridad financiera",
    "debt": "reducir deudas",
    "investments": "inversiones",
    "other": "otros objetivos",
}

PRIORITY_THEMES = {
    "education": "family_travel",
    "retirement": "early_retirement",
    "housing": "dream_home",
    "security": "financial_shield",
    "debt": "financial_shield",
    "investments": "early_retirement",
    "other": "family_travel",
}

PRIORITY_GOAL_TYPES = {
    "education": {"COLLEGE", "EDUCATION"},
    "retirement": {"RETIREMENT"},
    "housing": {"PURCHASE"},
    "debt": {"DEBT"},
    "investments": {"INVESTMENT"},
}

MOVE_LABELS = {
    "pay down revolving card": "reducir el saldo de la tarjeta",
    "add life cover": "ampliar la cobertura de vida",
    "raise mortality coverage": "ampliar la cobertura de vida",
    "add umbrella cover": "añadir cobertura de responsabilidad civil",
    "lower the withdrawal rate": "reducir el ritmo de retiros",
    "raise growth allocation toward glide": "ajustar la proporción de inversiones de crecimiento",
    "reduce growth allocation toward glide": "ajustar la proporción de inversiones de crecimiento",
    "raise annual savings": "aumentar el ahorro anual",
    "close a coverage gap": "cerrar una brecha de cobertura",
    "reduce single-name concentration": "reducir la concentración de una inversión",
}

ALLOWED_THEMES = {"family_travel", "early_retirement", "dream_home", "financial_shield"}


def _format_money(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    formatted = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"${formatted}"


def _year_from_text(value):
    match = re.search(r"\b(20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _join_names(members, case_raw):
    names = [
        str(member.get("name", "")).strip()
        for member in members
        if isinstance(member, dict) and str(member.get("name", "")).strip()
    ]
    if not names:
        financial = case_raw.get("financial_health_json", {})
        household = financial.get("case", {}).get("household", [])
        names = [
            str(member.get("first_name", "")).strip()
            for member in household
            if isinstance(member, dict) and str(member.get("first_name", "")).strip()
        ]
    if not names:
        return "Vuestra familia"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " y " + names[-1]


def _personal_detail(members):
    labels = (
        ("aspirations", "aspiración"),
        ("concerns", "preocupación"),
        ("interests", "interés"),
        ("non_negotiables", "prioridad importante"),
    )
    for member in members:
        if not isinstance(member, dict):
            continue
        for field, label in labels:
            values = member.get(field, [])
            if isinstance(values, str):
                values = [values]
            if values:
                value = str(values[0]).strip()
                if value:
                    name = str(member.get("name", ""))
                    subject = f"{name} nos comentó" if name else "Nos comentasteis"
                    return f"{subject} como {label}: «{value[:160]}»."
    return ""


def _priority_theme(priority):
    return PRIORITY_THEMES.get(priority, "family_travel")


def _goal_for_priorities(goals, priorities):
    for priority in priorities:
        goal_types = PRIORITY_GOAL_TYPES.get(priority, set())
        for goal in goals:
            if not isinstance(goal, dict):
                continue
            goal_type = str(goal.get("goalType", "")).upper()
            if goal_type in goal_types:
                if priority != "housing" or goal.get("subType") == "REAL_ESTATE_PURCHASE":
                    return goal, priority
    for goal in goals:
        if isinstance(goal, dict) and (
            _format_money(goal.get("amount")) or _year_from_text(goal.get("value"))
        ):
            goal_type = str(goal.get("goalType", "")).upper()
            subtype = str(goal.get("subType", "")).upper()
            if goal_type == "RETIREMENT":
                return goal, "retirement"
            if goal_type == "COLLEGE":
                return goal, "education"
            if goal_type == "PURCHASE" and subtype == "REAL_ESTATE_PURCHASE":
                return goal, "housing"
            return goal, priorities[0] if priorities else "other"
    return (goals[0], priorities[0] if priorities else "other") if goals else (None, "other")


def _describe_goal(goal, priority):
    if not isinstance(goal, dict):
        return (
            "El plan no incluye una meta específica para esta prioridad; "
            "la historia mantiene el foco en los datos financieros disponibles.",
            "Prioridad del cuestionario",
            PRIORITY_LABELS.get(priority, "otros objetivos"),
        )

    goal_type = str(goal.get("goalType", "")).upper()
    subtype = str(goal.get("subType", "")).upper()
    amount = _format_money(goal.get("amount"))
    year = _year_from_text(goal.get("value"))
    if goal_type == "RETIREMENT":
        metric_value = str(year) if year else amount
        if year:
            narration = f"El plan sitúa el objetivo de jubilación en {year}."
        elif amount:
            narration = f"El plan registra una meta de jubilación de {amount}."
        else:
            narration = "La jubilación figura entre las metas recogidas en vuestro plan."
        return narration, "Año objetivo de jubilación" if year else "Meta de jubilación", metric_value or "Incluida en el plan"

    if goal_type == "COLLEGE":
        narration = (
            f"El plan contempla {amount} para la educación de la familia."
            if amount
            else "El plan contempla una meta educativa para la familia."
        )
        if "each child" in str(goal.get("value", "")).lower():
            narration = f"El plan contempla {amount} para la educación de cada hijo."
        return narration, "Meta de educación", amount or "Incluida en el plan"

    if goal_type == "PURCHASE" and subtype == "REAL_ESTATE_PURCHASE":
        timing = f" para {year}" if year else ""
        amount_text = amount or "una cantidad no especificada"
        narration = f"El plan registra una meta de vivienda de {amount_text}{timing}."
        return narration, "Meta de vivienda", amount or (str(year) if year else "Incluida en el plan")

    if goal_type == "VACATION":
        narration = (
            f"El plan contempla una meta de viaje de {amount}."
            if amount
            else "El plan contempla una meta de viaje."
        )
        return narration, "Meta de viaje", amount or "Incluida en el plan"

    if goal_type == "PURCHASE":
        timing = f" para {year}" if year else ""
        narration = f"El plan registra una meta de compra de {amount}{timing}."
        return narration, "Meta de compra", amount or (str(year) if year else "Incluida en el plan")

    if amount:
        return (
            f"El plan registra una meta de {amount} relacionada con {PRIORITY_LABELS.get(priority, 'vuestros objetivos')}.",
            "Meta del plan",
            amount,
        )
    return (
        "Esta meta figura en el plan financiero de la familia.",
        "Meta del plan",
        str(year) if year else "Incluida en el plan",
    )


def _projection_for_goal(financial, goal):
    projections = financial.get("projections", {}).get("yearly", [])
    if not projections:
        return None
    goal_year = _year_from_text(goal.get("value")) if isinstance(goal, dict) else None
    if goal_year:
        for projection in projections:
            if projection.get("year") == goal_year:
                return projection
    return projections[0]


def _describe_move_action(move):
    title = str(move.get("title", "")).strip().lower()
    action = str(move.get("action", ""))
    amount_match = re.search(r"\$[\d,]+(?:\.\d+)?(?:M)?", action)
    amount = amount_match.group(0) if amount_match else None

    if title == "pay down revolving card" and amount:
        rate = re.search(r"\d+(?:\.\d+)?%", action)
        rate_text = f" al {rate.group(0)}" if rate else ""
        return f"El plan propone destinar {amount} desde el efectivo a la tarjeta{rate_text}."
    if title in {"add life cover", "raise mortality coverage"} and amount:
        return f"El plan recomienda ampliar la cobertura de vida en {amount}."
    if title == "add umbrella cover" and amount:
        return f"El plan recomienda añadir {amount} de cobertura de responsabilidad civil."
    if title == "lower the withdrawal rate" and amount:
        rate = re.search(r"\d+(?:\.\d+)?%", action)
        rate_text = f" ({rate.group(0)})" if rate else ""
        return f"El plan propone limitar los retiros a {amount} al año{rate_text}."
    if title == "raise annual savings" and amount:
        return f"El plan propone redirigir {amount} al año al ahorro."
    if title in {"raise growth allocation toward glide", "reduce growth allocation toward glide"} and amount:
        return f"El plan recomienda ajustar la cartera, con un cambio aproximado de {amount}."
    if title == "reduce single-name concentration" and amount:
        return f"El plan recomienda reducir la concentración de una inversión en aproximadamente {amount}."
    if title == "close a coverage gap":
        return "El plan recomienda asegurar la vivienda principal para cerrar una brecha de cobertura."
    return ""


def _build_llm_scenes(
    case_id: str,
    names: str,
    profile_data: dict,
    case_raw: dict,
    question: str,
    base_scenes: list,
    source_ref: str,
) -> list | None:
    """Genera narraciones críticas, detalladas y adaptadas al nivel técnico usando gpt-5-mini."""
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        return None

    literacy = str(profile_data.get("literacy", "beginner")).strip().lower()
    tone = str(profile_data.get("tone", "warm")).strip().lower()

    literacy_rules = {
        "beginner": (
            "NIVEL FINANCIERO: BÁSICO (beginner). Explica todo con claridad pedagógica, "
            "evitando jerga técnica innecesaria y traduciendo cualquier concepto financiero "
            "a impacto real en el día a día de la familia."
        ),
        "intermediate": (
            "NIVEL FINANCIERO: INTERMEDIO (intermediate). Utiliza terminología financiera "
            "práctica con explicaciones claras: flujo de caja libre, tasa de ahorro, liquidez, "
            "fondo de emergencia, tipo de interés, amortización y diversificación."
        ),
        "advanced": (
            "NIVEL FINANCIERO: AVANZADO (advanced). Emplea análisis financiero riguroso y "
            "tecnicismos precisos: TAE/APR, coste de oportunidad del capital, asignación estratégica "
            "de activos (glide path), ratio deuda-ingresos (DTI), tasa segura de retiro (SWR), "
            "riesgo de concentración idiosincrático, brecha de cobertura actuarialmente estimada "
            "y proyecciones en dólares nominales."
        ),
    }.get(literacy, "")

    tone_rules = (
        "TONO: Directo, analítico y ejecutivo, sin rodeos."
        if tone == "direct"
        else "TONO: Empático y cercano a la familia, pero firmemente objetivo, honesto y crítico con los números."
    )

    # Compactamos los datos del caso para no saturar contexto manteniendo todas las cifras
    financial_summary = json.dumps(case_raw.get("financial_health_json", case_raw), ensure_ascii=False)
    if len(financial_summary) > 18000:
        financial_summary = financial_summary[:18000]

    profile_summary = json.dumps(profile_data, ensure_ascii=False)

    system_prompt = (
        "Eres un asesor financiero patrimonial senior y analista crítico de Sherpas Wealth. "
        "Tu tarea es analizar en profundidad los datos financieros reales de una familia (JSON del plan) "
        "cruzándolos con su cuestionario personal para generar el guion narrado de un vídeo explicativo de 4 escenas.\n\n"
        f"{literacy_rules}\n"
        f"{tone_rules}\n\n"
        "REGLAS ESTRICTAS DE ANÁLISIS Y RIGOR:\n"
        "1. CERO INVENCIONES: Usa EXCLUSIVAMENTE cifras, activos, deudas, porcentajes, años y acciones "
        "que aparezcan literalmente en los datos del plan de Sherpas. Si un dato no está, no lo inventes.\n"
        "2. DIAGNÓSTICO OBJETIVO Y CRÍTICO: No te limites a describir cifras de forma complaciente. "
        "Señala con claridad los puntos débiles, ineficiencias o riesgos del plan actual (por ejemplo: "
        "efectivo ocioso frente a deuda revolving cara, brechas de cobertura de vida o responsabilidad civil, "
        "concentración excesiva en un solo activo, tasa de ahorro insuficiente o desviación respecto al glide path).\n"
        "3. RESPUESTA DIRECTA A LA PREGUNTA Y PRIORIDADES: Responde explícitamente a la pregunta principal "
        "del cuestionario, respeta sus 'non_negotiables' (lo que no quieren sacrificar) y conecta sus "
        "preocupaciones ('concerns') y aspiraciones ('aspirations') con los números reales.\n"
        "4. PAUTAS ACCIONABLES DETALLADAS: En las escenas 3 y 4, detalla qué movimientos exactos deben ejecutar "
        "(basándote en 'top_moves' y el balance/flujo del plan), en qué orden de prioridad, qué impacto numérico "
        "tienen en su puntuación y patrimonio, y qué trade-off o sacrificio conllevan.\n"
        "5. EXTENSIÓN POR ESCENA: Cada 'narration' debe ser rica, detallada y bien argumentada (entre 65 y 110 palabras "
        "por escena, apta para ser locutada en voz alta con fluidez, sin listas con viñetas ni markdown).\n\n"
        "FORMATO DE SALIDA OBLIGATORIO:\n"
        "Devuelve ÚNICAMENTE un objeto JSON válido con la clave 'scenes', que contenga exactamente 4 objetos "
        "correspondientes a los ids ['starting_point', 'family_priority', 'plan_projection', 'first_step']. "
        "Cada objeto debe tener exactamente estas claves:\n"
        "- 'id': string\n"
        "- 'headline': string (titular potente de máximo 65 caracteres)\n"
        "- 'narration': string (explicación detallada y crítica en español, sin markdown)\n"
        "- 'metric_label': string (etiqueta corta de la métrica clave de esa escena)\n"
        "- 'metric_value': string (valor numérico o indicador exacto extraído del plan)\n"
        "- 'visual_theme': string (uno de: 'family_travel', 'early_retirement', 'dream_home', 'financial_shield')"
    )

    user_prompt = (
        f"FAMILIA: {names} (case_id: {case_id})\n"
        f"PREGUNTA PRINCIPAL DEL CUESTIONARIO: {question or 'No especificada; enfócate en sus prioridades principales.'}\n\n"
        f"PERFIL Y PREFERENCIAS DEL CUESTIONARIO:\n{profile_summary}\n\n"
        f"DATOS FINANCIEROS COMPLETOS DEL PLAN (MCP SHERPAS):\n{financial_summary}"
    )

    try:
        client = OpenAI(
            base_url="https://llm-hackathon.sherpaswealth.com",
            api_key=team_key,
            timeout=35.0,
        )
        res = client.chat.completions.create(
            model="gpt-5-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_content = res.choices[0].message.content.strip()
        parsed = json.loads(raw_content)
        ai_scenes = parsed.get("scenes", [])
        if not isinstance(ai_scenes, list) or len(ai_scenes) < 4:
            return None

        by_id = {str(s.get("id", "")).strip(): s for s in ai_scenes if isinstance(s, dict)}
        merged_scenes = []
        for idx, base in enumerate(base_scenes):
            ai_item = by_id.get(base["id"]) or (ai_scenes[idx] if idx < len(ai_scenes) else {})
            headline = str(ai_item.get("headline", "")).strip() or base["headline"]
            narration = str(ai_item.get("narration", "")).strip() or base["narration"]
            metric_label = str(ai_item.get("metric_label", "")).strip() or base["metric_badge"]["label"]
            metric_value = str(ai_item.get("metric_value", "")).strip() or base["metric_badge"]["value"]
            theme = str(ai_item.get("visual_theme", "")).strip()
            if theme not in ALLOWED_THEMES:
                theme = base["visual_theme"]

            merged = dict(base)
            merged["headline"] = headline
            merged["narration"] = narration
            merged["visual_theme"] = theme
            merged["metric_badge"] = {
                "label": metric_label,
                "value": metric_value,
                "source_ref": source_ref,
            }
            merged_scenes.append(merged)

        return merged_scenes
    except Exception:
        return None


def build_story_payload(
    case_id: str,
    profile_data: dict,
    case_raw: dict,
    data_status: str,
    question: str = "",
) -> dict:
    """Build four personalized, fact-grounded story scenes from a case plan."""
    financial = case_raw.get("financial_health_json", {})
    score_data = financial.get("score", {})
    score = score_data.get("published_score")
    if score is None:
        score = score_data.get("value")

    members = profile_data.get("members", [])
    names = _join_names(members, case_raw)
    priorities = [
        str(priority).strip().lower()
        for priority in profile_data.get("family_priorities", [])
        if str(priority).strip()
    ]
    priority = priorities[0] if priorities else "other"
    priority_label = PRIORITY_LABELS.get(priority, "otros objetivos")
    preference_detail = _personal_detail(members)
    goals = financial.get("goals", {}).get("goalsSummary", [])
    selected_goal, goal_priority = _goal_for_priorities(goals, priorities)
    goal_priority_label = PRIORITY_LABELS.get(goal_priority, "otros objetivos")
    goal_narration, goal_metric_label, goal_metric_value = _describe_goal(selected_goal, goal_priority)
    theme = _priority_theme(priority)
    source_ref = f"cases/{case_id}/financial-health.json"

    score_value = f"{score}/100" if score is not None else "Dato no disponible"
    if profile_data.get("tone") == "direct":
        score_narration = (
            f"{names}: puntuación de salud financiera {score_value}. "
            f"Prioridad principal del cuestionario: {priority_label}."
        )
    else:
        score_narration = (
            f"{names}, vuestro plan parte de una puntuación de salud financiera de {score_value}. "
            f"En el cuestionario señalasteis {priority_label} como prioridad principal."
        )
    if preference_detail:
        score_narration += " " + preference_detail

    if profile_data.get("tone") == "direct":
        goal_text = f"Prioridad principal: {priority_label}. {goal_narration}"
    else:
        goal_text = f"Vuestra prioridad principal es {priority_label}. {goal_narration}"
    if question:
        goal_text += f" Sobre vuestra consulta («{question[:140]}»), analizamos su encaje con vuestros recursos."

    projection = _projection_for_goal(financial, selected_goal)
    if projection and projection.get("net_worth") is not None:
        projection_year = projection.get("year", "proyectado")
        net_worth = _format_money(projection.get("net_worth"))
        if profile_data.get("tone") == "direct":
            projection_narration = (
                f"Patrimonio neto estimado para {projection_year}: {net_worth}. "
                "Es la diferencia entre activos y deudas."
            )
        else:
            projection_narration = (
                f"En la proyección de {projection_year}, el plan estima un patrimonio neto de "
                f"{net_worth}. Es la diferencia entre lo que tenéis y lo que debéis."
            )
        if profile_data.get("literacy") == "advanced":
            projection_narration += " La cifra está expresada en dólares nominales del año indicado."
        projection_metric_label = f"Patrimonio neto proyectado ({projection_year})"
        projection_metric_value = net_worth
    else:
        projection_narration = f"El indicador publicado para vuestro plan es {score_value}."
        projection_metric_label = "Salud financiera"
        projection_metric_value = score_value

    moves = score_data.get("top_moves", [])
    move = moves[0] if moves and isinstance(moves[0], dict) else {}
    move_title = str(move.get("title", "")).strip()
    move_label = MOVE_LABELS.get(move_title.lower(), move_title or "seguir la recomendación principal")
    score_before = move.get("score_before", score)
    score_after = move.get("score_after")
    if score_after is not None:
        action_metric_value = f"{score_before} → {score_after}/100"
        if profile_data.get("tone") == "direct":
            action_narration = (
                f"Siguiente paso: {move_label}. "
                f"El plan estima que la puntuación pasaría de {score_before} a {score_after}/100."
            )
        else:
            action_narration = (
                f"El plan destaca como siguiente paso {move_label}. "
                f"Según la proyección del plan, la puntuación pasaría de {score_before} a {score_after}/100."
            )
    else:
        action_metric_value = score_value
        action_narration = f"El plan destaca como siguiente paso {move_label}."
    action_detail = _describe_move_action(move)
    if action_detail:
        action_narration += " " + action_detail

    base_scenes = [
        {
            "id": "starting_point",
            "kind": "narration",
            "year": 2026,
            "period_label": "Hoy",
            "visual_theme": theme,
            "headline": f"{names}: vuestro punto de partida",
            "narration": score_narration,
            "metric_badge": {"label": "Salud financiera", "value": score_value, "source_ref": source_ref},
            "source_refs": [source_ref],
            "next_scene_id": "family_priority",
            "audio_b64": "",
        },
        {
            "id": "family_priority",
            "kind": "narration",
            "year": None,
            "period_label": "Vuestra prioridad",
            "visual_theme": _priority_theme(goal_priority),
            "headline": f"Una meta concreta: {goal_priority_label}",
            "narration": goal_text,
            "metric_badge": {
                "label": goal_metric_label,
                "value": goal_metric_value,
                "source_ref": source_ref,
            },
            "source_refs": [source_ref],
            "next_scene_id": "plan_projection",
            "audio_b64": "",
        },
        {
            "id": "plan_projection",
            "kind": "narration",
            "year": projection.get("year") if projection else None,
            "period_label": "Lo que proyecta el plan",
            "visual_theme": "early_retirement" if priority == "retirement" else theme,
            "headline": "El horizonte que dibujan vuestros datos",
            "narration": projection_narration,
            "metric_badge": {
                "label": projection_metric_label,
                "value": projection_metric_value,
                "source_ref": source_ref,
            },
            "source_refs": [source_ref],
            "next_scene_id": "first_step",
            "audio_b64": "",
        },
        {
            "id": "first_step",
            "kind": "ending",
            "year": 2026,
            "period_label": "Un primer paso",
            "visual_theme": "financial_shield",
            "headline": "Una acción concreta del plan",
            "narration": action_narration,
            "metric_badge": {
                "label": "Puntuación tras la acción",
                "value": action_metric_value,
                "source_ref": source_ref,
            },
            "source_refs": [source_ref],
            "next_scene_id": None,
            "audio_b64": "",
        },
    ]

    llm_scenes = _build_llm_scenes(
        case_id=case_id,
        names=names,
        profile_data=profile_data,
        case_raw=case_raw,
        question=question,
        base_scenes=base_scenes,
        source_ref=source_ref,
    )

    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "title": f"Historia financiera — {names}",
        "data_status": data_status,
        "disclaimer": "Escenas basadas en los datos del plan financiero de la familia.",
        "start_scene_id": "starting_point",
        "scenes": llm_scenes if llm_scenes is not None else base_scenes,
    }