# story_generator.py
import os
import re
import json
import base64
from datetime import date
from decimal import Decimal, InvalidOperation
from openai import OpenAI


MODEL = "gpt-5-mini"

THEME_KEYWORDS = {
    "education": ("college", "education", "529", "school", "tuition"),
    "housing": ("home", "house", "housing", "mortgage", "down payment", "real estate"),
    "vehicle": ("vehicle", "car", "auto", "credit card", "high-rate", "debt"),
    "retirement": ("retirement", "retire", "portfolio", "risk", "invested mix", "asset allocation"),
    "vacation": ("vacation", "travel", "trip", "near-term"),
}

FINANCIAL_NARRATIVE_KEYS = (
    "summary_main",
    "summary_recommendations",
    "savings_short_observations",
    "savings_what_to_look_into",
    "assets_short_observations",
    "assets_what_to_look_into",
    "debt_short_observations",
    "debt_what_to_look_into",
    "retirement_short_observations",
    "retirement_what_to_look_into",
)

INVESTMENT_NARRATIVE_KEYS = (
    "summary_main",
    "recommendations_main",
    "portfolio_today_priorities",
    "portfolio_today_what_it_needs_to_do",
    "portfolio_today_verdict",
)

NUMBER_PATTERN = re.compile(r"(?<![\w])(?:[$€£]\s*)?-?\d[\d,]*(?:\.\d+)?(?:\s*%)?")


def _get_llm_client() -> OpenAI | None:
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        return None
    return OpenAI(
        base_url="https://llm-hackathon.sherpaswealth.com/v1",
        api_key=team_key,
        timeout=30.0,
    )


def _format_money(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "$0"
    formatted = f"{abs(value):,.0f}"
    return f"-${formatted}" if value < 0 else f"${formatted}"


def _parse_year(value) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10]).year
    except ValueError:
        return None


def _safe_int(value, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        matches = re.findall(r"-?\d+", value)
        if matches:
            return int(matches[-1])
    return default


def _split_source_items(text: str) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    chunks = re.split(r"(?m)(?=^\s*[-*]\s+)", text.strip())
    items = [re.sub(r"^\s*[-*]\s+", "", c.strip()) for c in chunks if c.strip()]
    if len(items) == 1 and "\n\n" in items[0]:
        items = [p.strip() for p in items[0].split("\n\n") if p.strip()]
    return items


def _extract_persona_sections(persona_md: str) -> list[dict]:
    if not isinstance(persona_md, str) or not persona_md.strip():
        return []
    sections = re.split(r"(?m)^##\s+", persona_md)
    relevant_prefixes = (
        "D1:",
        "D2:",
        "D3:",
        "D4:",
        "D5:",
        "D6:",
        "Transition alerts",
        "Subjective concerns",
        "Objective concerns",
        "Tensions",
    )
    fragments = []
    total_chars = 0
    for section in sections[1:]:
        heading, sep, body = section.partition("\n")
        heading = heading.strip()
        body = body.strip()
        if not sep or not heading or not any(heading.startswith(p) for p in relevant_prefixes):
            continue
        excerpt = body[:750]
        if total_chars + len(excerpt) > 3200:
            excerpt = excerpt[: max(0, 3200 - total_chars)]
        if not excerpt:
            break
        fragments.append({"source_ref": f"persona.md#{heading}", "text": excerpt})
        total_chars += len(excerpt)
    return fragments


def _build_yearly_ladder(fh: dict, published_score: int, scale: int, moves: list[dict]) -> list[dict]:
    """
    Constructs a chronological year-by-year escalation ladder from projections.yearly
    and chartGoals, pairing each milestone year with a concrete Sherpas decision.
    """
    goals_obj = fh.get("goals", {}) or {}
    chart_goals = goals_obj.get("chartGoals", []) if isinstance(goals_obj.get("chartGoals"), list) else []
    goals_summary = goals_obj.get("goalsSummary", []) if isinstance(goals_obj.get("goalsSummary"), list) else []
    projections_yearly = (
        (fh.get("projections", {}) or {}).get("yearly", [])
        if isinstance((fh.get("projections", {}) or {}).get("yearly"), list)
        else []
    )

    proj_by_year = {}
    sorted_proj_rows = []
    for idx, row in enumerate(projections_yearly):
        if isinstance(row, dict) and isinstance(row.get("year"), int):
            entry = {
                "year": row["year"],
                "age_client": row.get("age_client"),
                "net_worth": row.get("net_worth_todays_dollars"),
                "investable_assets": row.get("investable_assets"),
                "total_debts": row.get("total_debts"),
                "source_ref": f"financial-health.json#projections.yearly[{idx}]",
            }
            proj_by_year[row["year"]] = entry
            sorted_proj_rows.append(entry)
    sorted_proj_rows.sort(key=lambda r: r["year"])

    # Group non-bankruptcy goals by year
    goals_by_year = {}
    for idx, g in enumerate(chart_goals):
        if not isinstance(g, dict):
            continue
        g_type = str(g.get("goalType") or "").upper()
        if "BANKRUPTCY" in g_type:
            continue
        yr = _parse_year(g.get("date"))
        if yr is None:
            continue
        matched_amount = None
        for s in goals_summary:
            if isinstance(s, dict) and str(s.get("goalType") or "").upper() == g_type:
                if isinstance(s.get("amount"), (int, float)):
                    matched_amount = s["amount"]
                    break
        goals_by_year.setdefault(yr, []).append({
            "name": str(g.get("name") or g_type.title()),
            "goal_type": g_type,
            "amount": matched_amount,
            "source_ref": f"financial-health.json#goals.chartGoals[{idx}]",
        })

    # Choose up to 4 chronological checkpoint years (starting year + milestone years + long-term horizon)
    candidate_years = sorted(goals_by_year.keys())
    if sorted_proj_rows:
        first_yr = sorted_proj_rows[0]["year"]
        last_yr = sorted_proj_rows[-1]["year"]
        if first_yr not in candidate_years:
            candidate_years.insert(0, first_yr)
        if len(candidate_years) < 3 and len(sorted_proj_rows) >= 3:
            mid_yr = sorted_proj_rows[len(sorted_proj_rows) // 2]["year"]
            if mid_yr not in candidate_years:
                candidate_years.append(mid_yr)
        if last_yr not in candidate_years and len(candidate_years) < 4:
            candidate_years.append(last_yr)
    candidate_years = sorted(dict.fromkeys(candidate_years))[:4]

    if not candidate_years:
        candidate_years = [2026, 2030, 2035]

    ladder = []
    for i, yr in enumerate(candidate_years):
        # Find exact or nearest projection row
        proj = proj_by_year.get(yr)
        if proj is None and sorted_proj_rows:
            proj = min(sorted_proj_rows, key=lambda r: abs(r["year"] - yr))

        yr_goals = goals_by_year.get(yr, [])
        linked_move = moves[i % len(moves)] if moves else None

        # Progressive score escalation along the timeline
        step_score = (
            linked_move["score_after"]
            if linked_move
            else min(scale, published_score + (i + 1) * 3)
        )
        # Ensure monotonically non-decreasing visual score along years
        if ladder and step_score < ladder[-1]["projected_score"]:
            step_score = min(scale, ladder[-1]["projected_score"] + 2)

        nw_val = proj["net_worth"] if proj and isinstance(proj.get("net_worth"), (int, float)) else None
        inv_val = proj["investable_assets"] if proj and isinstance(proj.get("investable_assets"), (int, float)) else None
        debt_val = proj["total_debts"] if proj and isinstance(proj.get("total_debts"), (int, float)) else None

        ladder.append({
            "step_index": i + 1,
            "year": yr,
            "age_client": proj.get("age_client") if proj else None,
            "goals": yr_goals,
            "goal_names": [g["name"] for g in yr_goals],
            "decision_title": linked_move["title"] if linked_move else "Stay Consistent With Plan",
            "decision_detail": linked_move["detail"] if linked_move else "",
            "projected_score": step_score,
            "net_worth": nw_val,
            "net_worth_formatted": _format_money(nw_val) if nw_val is not None else None,
            "investable_assets": inv_val,
            "investable_assets_formatted": _format_money(inv_val) if inv_val is not None else None,
            "total_debts": debt_val,
            "total_debts_formatted": _format_money(debt_val) if debt_val is not None else None,
            "source_ref": (
                yr_goals[0]["source_ref"]
                if yr_goals
                else (proj["source_ref"] if proj else "financial-health.json#projections.yearly")
            ),
        })

    return ladder


def _extract_detailed_evidence(case_raw: dict, priorities: list[str]) -> dict:
    fh = case_raw.get("financial_health_json", {}) or {}
    ia = case_raw.get("investment_analysis_json", {}) or {}
    persona_md = case_raw.get("persona_md", "") or ""

    score_obj = fh.get("score", {}) or {}
    published_score = _safe_int(score_obj.get("published_score"), 70)
    scale = _safe_int(score_obj.get("scale"), 100)

    fh_narrative = fh.get("narrative", {}) or {}
    ia_narrative = ia.get("narrative", {}) or {}

    active_terms = []
    for p in priorities:
        active_terms.extend(THEME_KEYWORDS.get(str(p).lower(), (str(p).lower(),)))

    financial_fragments = []
    for key in FINANCIAL_NARRATIVE_KEYS:
        raw_val = fh_narrative.get(key, "")
        items = _split_source_items(raw_val)
        if not items:
            continue
        matched = [
            it for it in items
            if any(t in it.lower() for t in active_terms)
        ] or items[:2]
        for item in matched[:2]:
            financial_fragments.append({
                "source_ref": f"financial-health.json#narrative.{key}",
                "text": item[:1000],
            })

    investment_fragments = []
    for key in INVESTMENT_NARRATIVE_KEYS:
        raw_val = ia_narrative.get(key, "")
        items = _split_source_items(raw_val)
        for item in items[:2]:
            investment_fragments.append({
                "source_ref": f"investment-analysis.json#narrative.{key}",
                "text": item[:1000],
            })

    persona_fragments = _extract_persona_sections(persona_md)

    top_moves = fh.get("top_moves")
    if not isinstance(top_moves, list) or not top_moves:
        top_moves = (score_obj.get("top_moves") if isinstance(score_obj.get("top_moves"), list) else [])

    normalized_moves = []
    running_score = published_score
    for idx, mv in enumerate(top_moves[:4]):
        if isinstance(mv, dict):
            title = str(mv.get("title") or mv.get("move") or mv.get("name") or f"Action Step {idx + 1}")
            detail = str(mv.get("description") or mv.get("detail") or mv.get("impact") or "")
            s_before = _safe_int(mv.get("score_before"), running_score)
            s_after = _safe_int(mv.get("score_after"), min(scale, s_before + 3))
            running_score = s_after
            normalized_moves.append({
                "id": f"move_{idx + 1}",
                "title": title,
                "detail": detail,
                "score_before": s_before,
                "score_after": s_after,
            })

    if not normalized_moves:
        rec_items = _split_source_items(fh_narrative.get("summary_recommendations", ""))
        for idx, rec in enumerate(rec_items[:4]):
            clean_rec = rec.strip().rstrip(".")
            short_title = clean_rec[:65] + ("..." if len(clean_rec) > 65 else "")
            s_before = running_score
            s_after = min(scale, s_before + 3)
            running_score = s_after
            normalized_moves.append({
                "id": f"move_{idx + 1}",
                "title": short_title,
                "detail": clean_rec,
                "score_before": s_before,
                "score_after": s_after,
            })

    if len(normalized_moves) < 2 and investment_fragments:
        inv_text = investment_fragments[0]["text"].strip().rstrip(".")
        s_before = running_score
        s_after = min(scale, s_before + 3)
        normalized_moves.append({
            "id": f"move_{len(normalized_moves) + 1}",
            "title": "Align Portfolio Risk & Allocation",
            "detail": inv_text[:220],
            "score_before": s_before,
            "score_after": s_after,
        })

    yearly_ladder = _build_yearly_ladder(fh, published_score, scale, normalized_moves)
    best_after_score = max(
        [m["score_after"] for m in normalized_moves] + [l["projected_score"] for l in yearly_ladder],
        default=min(scale, published_score + 6),
    )

    return {
        "published_score": published_score,
        "scale": scale,
        "best_after_score": best_after_score,
        "yearly_ladder": yearly_ladder,
        "financial_fragments": financial_fragments,
        "investment_fragments": investment_fragments,
        "persona_fragments": persona_fragments,
        "normalized_moves": normalized_moves,
        "summary_main": fh_narrative.get("summary_main", ""),
        "summary_recommendations": fh_narrative.get("summary_recommendations", ""),
    }


def _pick_visual_theme(priorities: list[str]) -> str:
    joined = " ".join(str(p).lower() for p in priorities)
    if any(k in joined for k in ("housing", "home", "house", "real_estate")):
        return "dream_home"
    if any(k in joined for k in ("retirement", "retire")):
        return "early_retirement"
    if any(k in joined for k in ("vacation", "travel")):
        return "family_travel"
    return "financial_shield"


def _canonical_number(value: str) -> str | None:
    cleaned = re.sub(r"[$€£%\s]", "", value).replace(",", "")
    try:
        return format(Decimal(cleaned).normalize(), "f")
    except InvalidOperation:
        return None


def _collect_allowed_numbers(evidence: dict) -> set[str]:
    allowed = set()
    blob = json.dumps(evidence, ensure_ascii=False)
    for m in NUMBER_PATTERN.finditer(blob):
        c = _canonical_number(m.group(0))
        if c is not None:
            allowed.add(c)
    for n in range(1, 15):
        allowed.add(str(n))
    return allowed


def _sanitize_unverified_numbers(text: str, allowed_numbers: set[str]) -> str:
    if not allowed_numbers:
        return text

    def _replace(match):
        token = match.group(0)
        canon = _canonical_number(token)
        if canon in allowed_numbers:
            return token
        return ""

    cleaned = NUMBER_PATTERN.sub(_replace, text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _synthesize_tts(llm: OpenAI | None, text: str) -> str:
    if llm is None or not text.strip():
        return ""
    try:
        speech = llm.audio.speech.create(
            model="eleven-flash-v2.5",
            voice="alloy",
            input=text,
        )
        return base64.b64encode(speech.content).decode("utf-8")
    except Exception as err:
        print("[TTS ERROR in story_generator]:", repr(err))
        return ""


def build_story_payload(
    case_id: str,
    profile_data: dict,
    case_raw: dict,
    data_status: str,
    question: str = "",
) -> dict:
    """
    Builds a chronological year-by-year financial escalation story showing how the family's
    plan scales across milestone years as they execute Sherpas' recommended decisions.
    """
    members = profile_data.get("members", [])
    names = [m.get("name", "").strip() for m in members if isinstance(m, dict) and m.get("name", "").strip()]
    family_label = " & ".join(names) if names else case_id.replace("-", " ").title()
    priorities = profile_data.get("family_priorities", []) or []
    literacy = profile_data.get("literacy", "intermediate")
    tone = profile_data.get("tone", "warm")

    evidence = _extract_detailed_evidence(case_raw, priorities)
    visual_theme = _pick_visual_theme(priorities)
    allowed_numbers = _collect_allowed_numbers(evidence)
    moves = evidence["normalized_moves"]
    ladder = evidence["yearly_ladder"]

    first_year = ladder[0]["year"]
    last_year = ladder[-1]["year"]

    fallback_texts = {
        "intro": (
            f"Today, {family_label} begins with a Sherpas financial health score of "
            f"{evidence['published_score']} out of {evidence['scale']}. Let's follow your annual plan from "
            f"{first_year} to {last_year} to see how each smart decision scales your household wealth."
        ),
        "choice": (
            f"Your roadmap spans {len(ladder)} key milestone years from {first_year} to {last_year}. "
            "Choose whether to follow the year-by-year progression in order or jump ahead to your long-term outcome."
        ),
        "ending": (
            f"By executing these decisions step by step, your health score scales from "
            f"{evidence['published_score']} toward {evidence['best_after_score']} out of {evidence['scale']}. "
            "Use your Action Tracker below to check off your first move and schedule a calendar reminder."
        ),
    }

    for item in ladder:
        idx = item["step_index"]
        yr = item["year"]
        nw_phrase = (
            f"projected net worth reaches {item['net_worth_formatted']} in today's dollars"
            if item["net_worth_formatted"]
            else f"your financial health score climbs to {item['projected_score']}"
        )
        goal_phrase = (
            f"supporting {', '.join(item['goal_names'])}"
            if item["goal_names"]
            else "strengthening your household balance sheet"
        )
        fallback_texts[f"year_{idx}"] = (
            f"In {yr}, applying the decision to {item['decision_title'].lower()} helps keep your plan scaling, "
            f"{goal_phrase}. By this stage, {nw_phrase} with a health score of {item['projected_score']}."
        )

    llm = _get_llm_client()
    if llm is not None:
        ladder_prompt_data = {
            f"year_{item['step_index']}": {
                "year": item["year"],
                "age_client": item["age_client"],
                "milestones_in_this_year": item["goal_names"],
                "recommended_decision": item["decision_title"],
                "decision_rationale": item["decision_detail"],
                "projected_score": f"{item['projected_score']}/{evidence['scale']}",
                "net_worth_todays_dollars": item["net_worth_formatted"],
                "investable_assets": item["investable_assets_formatted"],
                "total_debts": item["total_debts_formatted"],
            }
            for item in ladder
        }

        prompt_context = {
            "household": family_label,
            "members": [
                {
                    "name": m.get("name"),
                    "role": m.get("role"),
                    "interests": m.get("interests", []),
                    "aspirations": m.get("aspirations", []),
                    "concerns": m.get("concerns", []),
                    "non_negotiables": m.get("non_negotiables", []),
                }
                for m in members
                if isinstance(m, dict)
            ],
            "family_priorities": priorities,
            "literacy_level": literacy,
            "preferred_tone": tone,
            "family_question": question,
            "starting_score": f"{evidence['published_score']}/{evidence['scale']}",
            "final_projected_score": f"{evidence['best_after_score']}/{evidence['scale']}",
            "annual_escalation_timeline": ladder_prompt_data,
            "financial_health_evidence": evidence["financial_fragments"][:6],
            "investment_analysis_evidence": evidence["investment_fragments"][:5],
            "persona_context": evidence["persona_fragments"][:5],
        }

        expected_keys = list(fallback_texts.keys())
        system_prompt = (
            "You are a financial educator and storyteller for Sherpas Wealth, not a licensed advisor. "
            "Guide the family chronologically through their annual financial plan so they clearly see how "
            "each recommended decision compounds and scales their net worth, assets, debt payoff, and health score over time. "
            f"Return ONLY a JSON object with these exact keys: {json.dumps(expected_keys)}.\n"
            "Rules:\n"
            "- Write in natural, clear, motivating English tailored to literacy_level and preferred_tone.\n"
            "- Each narration must be 35 to 55 words (2-3 clear spoken sentences). No markdown or bullet points.\n"
            "- 'intro': Introduce today's baseline score, key strengths, and the core financial tension from persona_context and financial_health_evidence.\n"
            "- 'choice': Invite the family to walk year-by-year through their scaling roadmap or jump to the final horizon.\n"
            "- 'year_1', 'year_2', etc.: For each year in annual_escalation_timeline, connect the prior stage to THIS year's recommended_decision, milestones_in_this_year, and exact projected numbers (net worth, investable assets, debt reduction, and score climb). Note that projections are estimates.\n"
            "- 'ending': Summarize how following the decisions scales their overall score, answer family_question if supported by evidence, and point them to the Action Tracker below.\n"
            "- Strict grounding: Use ONLY numbers, dollar amounts, and years present in the provided JSON evidence. Never invent figures."
        )

        try:
            completion = llm.chat.completions.create(
                model=MODEL,
                reasoning_effort="low",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt_context, ensure_ascii=False)},
                ],
            )
            raw_reply = completion.choices[0].message.content or "{}"
            parsed = json.loads(raw_reply)
            for key in expected_keys:
                candidate = parsed.get(key)
                if isinstance(candidate, str) and len(candidate.split()) >= 12:
                    fallback_texts[key] = _sanitize_unverified_numbers(candidate.strip(), allowed_numbers)
        except Exception as err:
            print("[LLM ERROR in story_generator]:", repr(err))

    first_year_scene_id = "scene_year_1" if ladder else "scene_ending"
    last_year_scene_id = f"scene_year_{len(ladder)}" if ladder else "scene_ending"

    scenes = [
        {
            "id": "scene_intro",
            "kind": "narration",
            "year": None,
            "period_label": "BASELINE · TODAY",
            "visual_theme": visual_theme,
            "headline": f"{family_label}: Your Starting Baseline",
            "narration": fallback_texts["intro"],
            "metric_badge": {
                "label": "Starting Financial Health Score",
                "value": f"{evidence['published_score']}/{evidence['scale']}",
                "source_ref": "financial-health.json#score.published_score",
            },
            "escalation_step": 0,
            "next_scene_id": "scene_choice",
            "choices": [],
            "audio_b64": _synthesize_tts(llm, fallback_texts["intro"]),
        },
        {
            "id": "scene_choice",
            "kind": "choice",
            "year": None,
            "period_label": f"ANNUAL ROADMAP ({first_year}–{last_year})",
            "visual_theme": visual_theme,
            "headline": "How Your Plan Scales Year by Year",
            "narration": fallback_texts["choice"],
            "metric_badge": {
                "label": "Projected Score Escalation",
                "value": f"{evidence['published_score']} → {evidence['best_after_score']}/{evidence['scale']}",
                "source_ref": "financial-health.json#narrative.summary_recommendations",
            },
            "escalation_step": 0,
            "next_scene_id": None,
            "choices": [
                {
                    "id": "choice_year_by_year",
                    "label": f"Follow Year-by-Year Progression ({first_year} → {last_year}) →",
                    "next_scene_id": first_year_scene_id,
                },
                {
                    "id": "choice_jump_final_year",
                    "label": f"Jump to {last_year} Horizon →",
                    "next_scene_id": last_year_scene_id,
                },
            ],
            "audio_b64": _synthesize_tts(llm, fallback_texts["choice"]),
        },
    ]

    for item in ladder:
        idx = item["step_index"]
        yr = item["year"]
        scene_id = f"scene_year_{idx}"
        next_id = f"scene_year_{idx + 1}" if idx < len(ladder) else "scene_ending"

        badge_label = (
            f"{yr} Net Worth (Today's $)"
            if item["net_worth_formatted"]
            else f"{yr} Projected Health Score"
        )
        badge_value = (
            f"{item['net_worth_formatted']} · Score {item['projected_score']}/{evidence['scale']}"
            if item["net_worth_formatted"]
            else f"{item['projected_score']}/{evidence['scale']}"
        )

        goal_subtitle = f" · {', '.join(item['goal_names'])}" if item["goal_names"] else ""
        scenes.append(
            {
                "id": scene_id,
                "kind": "narration",
                "year": yr,
                "period_label": f"YEAR {yr}{goal_subtitle}".upper(),
                "visual_theme": visual_theme,
                "headline": f"{yr}: {item['decision_title']}",
                "narration": fallback_texts[f"year_{idx}"],
                "metric_badge": {
                    "label": badge_label,
                    "value": badge_value,
                    "source_ref": item["source_ref"],
                },
                "escalation_step": idx,
                "next_scene_id": next_id,
                "choices": [],
                "audio_b64": _synthesize_tts(llm, fallback_texts[f"year_{idx}"]),
            }
        )

    scenes.append(
        {
            "id": "scene_ending",
            "kind": "ending",
            "year": None,
            "period_label": "ACTION PLAN & REMINDERS",
            "visual_theme": visual_theme,
            "headline": f"From {evidence['published_score']} to {evidence['best_after_score']}/{evidence['scale']}: Your Next Moves",
            "narration": fallback_texts["ending"],
            "metric_badge": {
                "label": "Final Projected Health Score",
                "value": f"{evidence['best_after_score']}/{evidence['scale']} (+{max(0, evidence['best_after_score'] - evidence['published_score'])} pts)",
                "source_ref": "financial-health.json#score.published_score",
            },
            "escalation_step": len(ladder),
            "next_scene_id": None,
            "choices": [],
            "audio_b64": _synthesize_tts(llm, fallback_texts["ending"]),
        }
    )

    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "title": f"{family_label}'s Annual Financial Escalation",
        "data_status": data_status,
        "disclaimer": "Grounded in your Sherpas annual projections. Future figures are planning estimates, not guarantees.",
        "start_scene_id": "scene_intro",
        "scenes": scenes,
        "escalation_ladder": ladder,
        "tracker": {
            "base_score": evidence["published_score"],
            "scale": evidence["scale"],
            "moves": moves,
        },
    }