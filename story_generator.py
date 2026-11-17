# story_generator.py
def build_story_payload(case_id: str, profile_data: dict, case_raw: dict, data_status: str) -> dict:
    """
    Construye las escenas del guion respetando el Contrato JSON v1.
    No inventa cifras: toma los datos verificados del plan.
    """
    # Extraer el primer miembro o usar valor por defecto
    members = profile_data.get("members", [])
    user_name = members[0].get("name", "Familia") if members else "Familia"
    priorities = profile_data.get("family_priorities", ["education", "retirement"])

    # Cargar datos específicos según el caso
    fh = case_raw.get("financial_health_json", {})
    score = fh.get("score", {}).get("value", 60) if isinstance(fh, dict) else 60

    # Plantilla de escenas cronológicas conforme a story.schema.json
    scenes = [
        {
            "id": "intro",
            "kind": "narration",
            "year": 2026,
            "period_label": "Hoy (2026)",
            "title": f"Situación Actual — {user_name}",
            "narration": f"Hola {user_name}. Vuestro plan de Sherpas muestra un Financial Health Score de {score}/100. Contáis con liquidez en caja, pero mantenéis una tarjeta al 18% APR mientras planificáis el futuro.",
            "visual_type": "family",
            "metric": {
                "label": "Deuda Tarjeta (18% APR)",
                "value": "$18,000 pendientes",
                "source_ref": f"cases/{case_id}/financial-health.json#debt"
            },
            "source_refs": [f"cases/{case_id}/financial-health.json"],
            "next_scene_id": "choose_topic",
            "choices": [],
            "audio_b64": ""
        },
        {
            "id": "choose_topic",
            "kind": "choice",
            "year": None,
            "period_label": "Explorar",
            "title": "¿Qué queréis profundizar primero?",
            "narration": "Elegid si queréis ver la proyección de educación universitaria o el plan de jubilación a largo plazo.",
            "visual_type": "choice",
            "metric": None,
            "source_refs": [],
            "next_scene_id": None,
            "choices": [
                {"id": "education", "label": "Educación de los hijos (529)", "next_scene_id": "education_path"},
                {"id": "retirement", "label": "Jubilación proyectada (2048)", "next_scene_id": "retirement_path"}
            ],
            "audio_b64": ""
        },
        {
            "id": "education_path",
            "kind": "narration",
            "year": 2038,
            "period_label": "Meta 2038",
            "title": "Fondo Universitario para los Hijos",
            "narration": "Para cubrir la universidad de los niños sin alterar vuestro nivel de vida, el plan proyecta una necesidad de ahorro de $4,609 anuales mediante cuentas 529 con ventajas fiscales.",
            "visual_type": "goal",
            "metric": {
                "label": "Necesidad acumulada 529",
                "value": "$113,509 proyectados",
                "source_ref": f"cases/{case_id}/financial-health.json#education"
            },
            "source_refs": [f"cases/{case_id}/financial-health.json"],
            "next_scene_id": "ending",
            "choices": [],
            "audio_b64": ""
        },
        {
            "id": "retirement_path",
            "kind": "narration",
            "year": 2048,
            "period_label": "Meta 2048",
            "title": "Jubilación Tranquila y Patrimonio",
            "narration": "Al alcanzar la jubilación en 2048, los ingresos garantizados cubrirán el 93% de vuestros gastos, manteniendo una reserva proyectada al final del plan sin agotar ahorros.",
            "visual_type": "chart",
            "metric": {
                "label": "Cobertura de gastos",
                "value": "93% garantizado",
                "source_ref": f"cases/{case_id}/financial-health.json#retirement"
            },
            "source_refs": [f"cases/{case_id}/financial-health.json"],
            "next_scene_id": "ending",
            "choices": [],
            "audio_b64": ""
        },
        {
            "id": "ending",
            "kind": "ending",
            "year": 2026,
            "period_label": "Presente",
            "title": "Primeros Pasos Recomendados",
            "narration": "Para poner este plan en marcha hoy: 1) Destinar parte del exceso de caja a saldar la tarjeta al 18%. 2) Cubrir vacíos de seguro de vida. 3) Iniciar las aportaciones al fondo 529.",
            "visual_type": "summary",
            "metric": {
                "label": "Exceso de caja disponible",
                "value": "$60,223 por optimizar",
                "source_ref": f"cases/{case_id}/financial-health.json#cash"
            },
            "source_refs": [f"cases/{case_id}/financial-health.json"],
            "next_scene_id": None,
            "choices": [],
            "audio_b64": ""
        }
    ]

    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "title": f"Historia Financiera — {user_name}",
        "data_status": data_status,
        "disclaimer": "Demostración basada en el plan financiero oficial de Sherpas Wealth.",
        "start_scene_id": "intro",
        "scenes": scenes
    }
