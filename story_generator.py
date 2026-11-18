import os
import re
import json
import base64
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI


PRIORITY_LABELS = {
    "education": "education",
    "retirement": "retirement",
    "housing": "housing",
    "security": "financial security",
    "debt": "debt reduction",
    "investments": "investments",
    "other": "other goals",
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
    "pay down revolving card": "paying down the revolving credit card balance",
    "add life cover": "expanding life insurance coverage",
    "raise mortality coverage": "expanding life insurance coverage",
    "add umbrella cover": "adding umbrella liability coverage",
    "lower the withdrawal rate": "lowering the annual withdrawal rate",
    "raise growth allocation toward glide": "adjusting growth asset allocation toward the glide path",
    "reduce growth allocation toward glide": "adjusting growth asset allocation toward the glide path",
    "raise annual savings": "increasing annual savings",
    "close a coverage gap": "closing an insurance coverage gap",
    "reduce single-name concentration": "reducing single-stock concentration",
}

ALLOWED_THEMES = {"family_travel", "early_retirement", "dream_home", "financial_shield"}
PROXY_BASE_URL = "https://llm-hackathon.sherpaswealth.com/v1"
TTS_MODEL = "eleven-flash-v2.5"
TTS_VOICE = "alloy"  # Same voice alias as in app.py (/api/video-ask)


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
        return "your family"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _personal_detail(members):
    labels = (
        ("aspirations", "aspiration"),
        ("concerns", "concern"),
        ("interests", "interest"),
        ("non_negotiables", "non-negotiable priority"),
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
                    subject = f"{name} shared" if name else "You shared"
                    return f"{subject} a key {label}: \"{value[:160]}\"."
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
            "The plan does not specify a dedicated target for this priority, "
            "so the story keeps the focus on your core financial figures.",
            "Questionnaire priority",
            PRIORITY_LABELS.get(priority, "other goals"),
        )

    goal_type = str(goal.get("goalType", "")).upper()
    subtype = str(goal.get("subType", "")).upper()
    amount = _format_money(goal.get("amount"))
    year = _year_from_text(goal.get("value"))
    if goal_type == "RETIREMENT":
        metric_value = str(year) if year else amount
        if year:
            narration = f"The plan sets your target retirement year at {year}."
        elif amount:
            narration = f"The plan records a retirement target of {amount}."
        else:
            narration = "Retirement is included among the core goals in your plan."
        return narration, "Target retirement year" if year else "Retirement goal", metric_value or "Included in plan"

    if goal_type == "COLLEGE":
        narration = (
            f"The plan allocates {amount} toward family education."
            if amount
            else "The plan includes an education goal for the family."
        )
        if "each child" in str(goal.get("value", "")).lower():
            narration = f"The plan allocates {amount} for each child's education."
        return narration, "Education goal", amount or "Included in plan"

    if goal_type == "PURCHASE" and subtype == "REAL_ESTATE_PURCHASE":
        timing = f" by {year}" if year else ""
        amount_text = amount or "an unspecified amount"
        narration = f"The plan includes a home purchase goal of {amount_text}{timing}."
        return narration, "Housing goal", amount or (str(year) if year else "Included in plan")

    if goal_type == "VACATION":
        narration = (
            f"The plan includes a travel goal of {amount}."
            if amount
            else "The plan includes a travel goal."
        )
        return narration, "Travel goal", amount or "Included in plan"

    if goal_type == "PURCHASE":
        timing = f" by {year}" if year else ""
        narration = f"The plan records a purchase goal of {amount}{timing}."
        return narration, "Purchase goal", amount or (str(year) if year else "Included in plan")

    if amount:
        return (
            f"The plan records a {amount} target tied to {PRIORITY_LABELS.get(priority, 'your goals')}.",
            "Plan goal",
            amount,
        )
    return (
        "This goal is actively tracked within your family's financial plan.",
        "Plan goal",
        str(year) if year else "Included in plan",
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
        rate_text = f" at {rate.group(0)}" if rate else ""
        return f"The plan recommends putting {amount} from cash toward the credit card{rate_text}."
    if title in {"add life cover", "raise mortality coverage"} and amount:
        return f"The plan recommends increasing life insurance coverage by {amount}."
    if title == "add umbrella cover" and amount:
        return f"The plan recommends adding {amount} in umbrella liability coverage."
    if title == "lower the withdrawal rate" and amount:
        rate = re.search(r"\d+(?:\.\d+)?%", action)
        rate_text = f" ({rate.group(0)})" if rate else ""
        return f"The plan recommends limiting annual withdrawals to {amount}{rate_text}."
    if title == "raise annual savings" and amount:
        return f"The plan recommends redirecting {amount} per year into savings."
    if title in {"raise growth allocation toward glide", "reduce growth allocation toward glide"} and amount:
        return f"The plan recommends rebalancing your portfolio by roughly {amount}."
    if title == "reduce single-name concentration" and amount:
        return f"The plan recommends trimming single-stock concentration by approximately {amount}."
    if title == "close a coverage gap":
        return "The plan recommends insuring your primary residence to close a coverage gap."
    return ""


def _generate_tts_b64(client: OpenAI, text: str) -> str:
    """Generate MP3 audio in Base64 using eleven-flash-v2.5."""
    clean_text = str(text or "").strip()
    if not clean_text:
        return ""
    try:
        speech_res = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=clean_text,
        )
        return base64.b64encode(speech_res.content).decode("utf-8")
    except Exception as e:
        print("[TTS ERROR in story_generator]:", repr(e))
        return ""


def _attach_scene_audios(scenes: list) -> list:
    """Synthesize all 4 scenes in parallel with eleven-flash-v2.5 and populate audio_b64."""
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        return scenes

    client = OpenAI(
        base_url=PROXY_BASE_URL,
        api_key=team_key,
        timeout=25.0,
    )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_generate_tts_b64, client, scene.get("narration", ""))
            for scene in scenes
        ]
        for scene, future in zip(scenes, futures):
            scene["audio_b64"] = future.result()

    return scenes


def _build_llm_scenes(
    case_id: str,
    names: str,
    profile_data: dict,
    case_raw: dict,
    question: str,
    base_scenes: list,
    source_ref: str,
) -> list | None:
    """Generate a cohesive, conversational 4-act financial story in English using gpt-5-mini."""
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        print("[LLM SKIP] TEAM_KEY not configured; using fallback base_scenes.")
        return None

    literacy = str(profile_data.get("literacy", "beginner")).strip().lower()
    tone = str(profile_data.get("tone", "warm")).strip().lower()

    literacy_rules = {
        "beginner": (
            "FINANCIAL LITERACY: BEGINNER. Use everyday, jargon-free English. "
            "Translate every number into what it means for the family's daily peace of mind."
        ),
        "intermediate": (
            "FINANCIAL LITERACY: INTERMEDIATE. Use clear practical concepts such as cash flow, "
            "liquidity, debt interest, emergency fund, and diversification."
        ),
        "advanced": (
            "FINANCIAL LITERACY: ADVANCED. Use precise financial terminology (opportunity cost, APR, "
            "glide path allocation, safe withdrawal rate, concentration risk, coverage gap, and nominal dollars) "
            "while keeping the delivery conversational and natural."
        ),
    }.get(literacy, "")

    tone_rules = (
        "TONE: Direct, crisp, and executive—straight to the point."
        if tone == "direct"
        else "TONE: Warm, empathetic, and conversational, like a trusted advisor sitting across the table."
    )

    fh = case_raw.get("financial_health_json", case_raw)
    compact_fh = {
        k: fh[k]
        for k in ("case", "score", "goals", "projections", "balance_sheet", "cash_flow", "insurance", "recommendations")
        if isinstance(fh, dict) and k in fh
    } or fh

    financial_summary = json.dumps(compact_fh, ensure_ascii=False)[:4500]
    profile_summary = json.dumps(profile_data, ensure_ascii=False)

    system_prompt = (
        "You are a trusted Sherpas Wealth financial advisor recording a personalized 4-scene voiceover story in English for a family.\n"
        f"{literacy_rules}\n{tone_rules}\n\n"
        "RULES FOR A SEAMLESS, NATURAL SPOKEN NARRATIVE:\n"
        "1. LANGUAGE: Write 100% in natural, fluent English (headlines, narrations, metric labels, and metric values).\n"
        "2. CONTINUOUS STORY ARC: All 4 scenes form one single continuous monologue. Start scenes 2, 3, and 4 "
        "with natural conversational transitions linking back to the previous scene (e.g., 'With that baseline clear, "
        "let's look at what matters most to you...', 'Now, if we project this path forward...', "
        "'That is why your smartest first move today is...').\n"
        "3. WRITTEN FOR THE EAR: Speak directly to the family using 'you' and 'your'. Avoid parentheses, slashes "
        "(say '62 out of 100' instead of '62/100'), bullet points, or markdown. Use ONLY real figures from the JSON plan—never invent numbers.\n"
        "4. FOUR-ACT STRUCTURE (50-75 words per scene):\n"
        "   - 'starting_point': Greet the family by name, state where they stand today (health score, core strength, and main blind spot or drag).\n"
        "   - 'family_priority': Connect their top priority and 'non_negotiables' to their real numbers, and directly answer their questionnaire question.\n"
        "   - 'plan_projection': Explain their long-term net worth projection and what happens if they stay the course versus fixing weak spots.\n"
        "   - 'first_step': Highlight the highest-impact move from 'top_moves', how much it raises their score, and the practical benefit.\n\n"
        "Return ONLY a valid JSON object with the key 'scenes' containing 4 objects with keys: "
        "'id', 'headline' (max 60 chars), 'narration', 'metric_label', 'metric_value', "
        "'visual_theme' ('family_travel' | 'early_retirement' | 'dream_home' | 'financial_shield')."
    )

    user_prompt = (
        f"FAMILY: {names} ({case_id})\n"
        f"QUESTIONNAIRE QUESTION: {question or 'Focus on their top stated priorities'}\n"
        f"PROFILE & PREFERENCES: {profile_summary}\n"
        f"SHERPAS FINANCIAL PLAN: {financial_summary}"
    )

    try:
        client = OpenAI(
            base_url=PROXY_BASE_URL,
            api_key=team_key,
            timeout=60.0,
        )
        res = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="low",
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
            print("[LLM WARN] Incomplete response, using English fallback.")
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

        print("[LLM OK] Continuous English story generated successfully.")
        return merged_scenes
    except Exception as e:
        print("[LLM ERROR in story_generator]:", repr(e))
        return None


def build_story_payload(
    case_id: str,
    profile_data: dict,
    case_raw: dict,
    data_status: str,
    question: str = "",
) -> dict:
    """Build four personalized, fact-grounded story scenes in English from a case plan."""
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
    priority_label = PRIORITY_LABELS.get(priority, "other goals")
    preference_detail = _personal_detail(members)
    goals = financial.get("goals", {}).get("goalsSummary", [])
    selected_goal, goal_priority = _goal_for_priorities(goals, priorities)
    goal_priority_label = PRIORITY_LABELS.get(goal_priority, "other goals")
    goal_narration, goal_metric_label, goal_metric_value = _describe_goal(selected_goal, goal_priority)
    theme = _priority_theme(priority)
    source_ref = f"cases/{case_id}/financial-health.json"

    score_value = f"{score}/100" if score is not None else "Unavailable"
    score_spoken = f"{score} out of 100" if score is not None else "no published score yet"

    score_narration = (
        f"Hello {names}, today your plan starts with a financial health score of {score_spoken}. "
        f"With this snapshot on the table, let's see how it supports your top priority of {priority_label}."
    )
    if preference_detail:
        score_narration += " " + preference_detail

    goal_text = (
        f"Building from that baseline, let's focus on what matters most to you right now: {priority_label}. {goal_narration}"
    )
    if question:
        goal_text += f" Regarding your question about {question[:140]}, we checked how it fits within your actual resources."

    projection = _projection_for_goal(financial, selected_goal)
    if projection and projection.get("net_worth") is not None:
        projection_year = projection.get("year", "projected")
        net_worth = _format_money(projection.get("net_worth"))
        projection_narration = (
            f"If we project your current path out to {projection_year}, your plan estimates a net worth of "
            f"{net_worth}, after accounting for all assets and debts."
        )
        if profile_data.get("literacy") == "advanced":
            projection_narration += " This figure is expressed in nominal dollars for that target year."
        projection_metric_label = f"Projected net worth ({projection_year})"
        projection_metric_value = net_worth
    else:
        projection_narration = f"Staying on this trajectory keeps your benchmark indicator at {score_spoken}."
        projection_metric_label = "Financial health"
        projection_metric_value = score_value

    moves = score_data.get("top_moves", [])
    move = moves[0] if moves and isinstance(moves[0], dict) else {}
    move_title = str(move.get("title", "")).strip()
    move_label = MOVE_LABELS.get(move_title.lower(), move_title or "following the primary recommendation")
    score_before = move.get("score_before", score)
    score_after = move.get("score_after")
    if score_after is not None:
        action_metric_value = f"{score_before} → {score_after}/100"
        action_narration = (
            f"That is why, if you take one concrete step today, the highest-impact move is {move_label}. "
            f"With this single adjustment, your score rises from {score_before} to {score_after} out of 100."
        )
    else:
        action_metric_value = score_value
        action_narration = f"That is why your most effective first step right now is {move_label}."
    action_detail = _describe_move_action(move)
    if action_detail:
        action_narration += " " + action_detail

    base_scenes = [
        {
            "id": "starting_point",
            "kind": "narration",
            "year": 2026,
            "period_label": "Today",
            "visual_theme": theme,
            "headline": f"{names}: your starting point",
            "narration": score_narration,
            "metric_badge": {"label": "Financial health", "value": score_value, "source_ref": source_ref},
            "source_refs": [source_ref],
            "next_scene_id": "family_priority",
            "audio_b64": "",
        },
        {
            "id": "family_priority",
            "kind": "narration",
            "year": None,
            "period_label": "Your priority",
            "visual_theme": _priority_theme(goal_priority),
            "headline": f"A clear target: {goal_priority_label}",
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
            "period_label": "What the plan projects",
            "visual_theme": "early_retirement" if priority == "retirement" else theme,
            "headline": "The horizon your numbers point toward",
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
            "period_label": "Your first step",
            "visual_theme": "financial_shield",
            "headline": "One concrete action from your plan",
            "narration": action_narration,
            "metric_badge": {
                "label": "Score after action",
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

    final_scenes = llm_scenes if llm_scenes is not None else base_scenes
    final_scenes = _attach_scene_audios(final_scenes)

    tracker_moves = []
    for idx, m in enumerate(moves[:3]):
        if isinstance(m, dict):
            raw_t = str(m.get("title", "")).strip()
            tracker_moves.append({
                "id": f"move_{idx}",
                "title": MOVE_LABELS.get(raw_t.lower(), raw_t or "Plan recommendation"),
                "detail": _describe_move_action(m) or str(m.get("action", "")),
                "score_before": m.get("score_before", score),
                "score_after": m.get("score_after", score),
            })

    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "title": f"Financial Story — {names}",
        "data_status": data_status,
        "disclaimer": "Scenes grounded in the family's actual Sherpas financial plan.",
        "start_scene_id": "starting_point",
        "scenes": final_scenes,
        "tracker": {
            "base_score": score or 0,
            "moves": tracker_moves,
        },
    }