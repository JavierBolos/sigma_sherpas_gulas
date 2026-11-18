import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app
from mcp_sherpas import get_case_data
from story_generator import (
    SCENE_FIELDS,
    STORY_FIELDS,
    StoryGenerationError,
    _goal_theme,
    build_story_payload,
)


CASES_DIR = Path(__file__).parent / "cases"
TIMOTHY_CASE = CASES_DIR / "timothy-melanie-weah"


def _fit_words(text, word_limits):
    words = text.split()
    target = max(word_limits["min"], min(word_limits["max"], len(words)))
    filler = "La familia revisa los supuestos y mantiene abiertas sus decisiones.".split()
    while len(words) < target:
        words.extend(filler[: target - len(words)])
    return " ".join(words[:target])


class FakeCompletions:
    def __init__(self):
        self.last_request = None

    async def create(self, **kwargs):
        self.last_request = json.loads(kwargs["messages"][1]["content"])
        word_limits = self.last_request["word_limits"]
        narration = _fit_words(
            "El plan conecta cada acontecimiento familiar con decisiones documentadas "
            "y mantiene abiertas las prioridades que requieren revisión conjunta.",
            word_limits["narration"],
        )
        generated = {
            "intro": narration,
            "narrations": [
                {
                    "id": route["scene_id"],
                    "narration": _fit_words(
                        f"El recorrido destaca {route['emphasis'].lower()} y conecta "
                        "el objetivo familiar con decisiones documentadas por el plan.",
                        word_limits["narration"],
                    ),
                }
                for milestone in self.last_request["timeline"]
                for route in milestone["routes"]
            ],
            "ending_summary": _fit_words(
                "El plan reúne prioridades oficiales y conserva su desglose completo "
                "para consultarlo cuando la familia lo necesite.",
                word_limits["ending_summary"],
            ),
        }
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(generated, ensure_ascii=False)
                    )
                )
            ]
        )


class NumericFakeCompletions(FakeCompletions):
    async def create(self, **kwargs):
        response = await super().create(**kwargs)
        generated = json.loads(response.choices[0].message.content)
        generated["intro"] = "La jubilación está prevista para 2044."
        response.choices[0].message.content = json.dumps(generated)
        return response


class SupportedNumericFakeCompletions(FakeCompletions):
    async def create(self, **kwargs):
        response = await super().create(**kwargs)
        generated = json.loads(response.choices[0].message.content)
        limits = self.last_request["word_limits"]["narration"]
        generated["intro"] = _fit_words(
            "El objetivo de vivienda de $600,000 aparece en el plan como compromiso "
            "familiar documentado.",
            limits,
        )
        response.choices[0].message.content = json.dumps(
            generated, ensure_ascii=False
        )
        return response


class ExampleCompletions(FakeCompletions):
    INTRO = (
        "Timothy y Melanie tienen una base de ahorro sólida, aunque conviven metas "
        "cercanas, brechas de protección y decisiones de inversión que deben coordinar."
    )
    EDUCATION_ROUTE = {
        2027: (
            "El plan distingue la reserva de emergencia del efectivo excedente y recomienda "
            "usar parte para atender brechas de protección, sin comprometer metas próximas."
        ),
        2028: (
            "El vehículo está registrado como objetivo; Sherpas recomienda valorar el pago "
            "de la tarjeta de alto interés con efectivo que excede las reservas."
        ),
        2030: (
            "La vivienda aparece como meta; el análisis advierte que el flujo es incierto "
            "y pide confirmar gastos antes de comprometer aportaciones."
        ),
        2038: (
            "Se acerca la educación de Liam; el plan registra ahorro educativo inexistente y "
            "recomienda decidir cómo compartir el esfuerzo con otras prioridades."
        ),
        2041: (
            "Después llega la etapa de Josh; la misma brecha educativa sigue abierta, así "
            "que el plan propone coordinar el ahorro sin prometer cobertura."
        ),
        2048: (
            "Al acercarse la jubilación, el plan muestra ingresos proyectados y pide revisar "
            "juntos el riesgo de la cartera; ninguna proyección garantiza el resultado."
        ),
    }
    HOUSING_ROUTE = {
        2027: (
            "El viaje próximo depende de prioridades ya registradas; el plan separa la "
            "reserva necesaria del excedente y señala primero las brechas de protección."
        ),
        2028: (
            "La compra del vehículo figura en el calendario; antes de asignar excedentes, "
            "la recomendación oficial pone sobre la mesa la deuda de alto interés."
        ),
        2030: (
            "La vivienda concentra la atención de este recorrido; sus datos son un objetivo "
            "planificado, no una garantía de compra ni de asequibilidad."
        ),
        2038: (
            "La educación de Liam sigue en la cronología común; el plan pide coordinar su "
            "ahorro con las demás prioridades, sin darla por financiada."
        ),
        2041: (
            "La etapa de Josh completa el horizonte educativo; las fuentes mantienen abierta "
            "la brecha y no garantizan cubrir los costes futuros."
        ),
        2048: (
            "La jubilación cierra la secuencia compartida; el análisis recomienda revisar "
            "el riesgo de la cartera y conservar los supuestos como proyecciones."
        ),
    }
    ENDING = (
        "El plan prioriza protección, deuda, ahorro educativo y revisar la cartera; "
        "el desglose oficial completo puede consultarse si lo necesitáis."
    )

    async def create(self, **kwargs):
        self.last_request = json.loads(kwargs["messages"][1]["content"])
        word_limits = self.last_request["word_limits"]
        narrations = []
        for milestone in self.last_request["timeline"]:
            for route in milestone["routes"]:
                route_text = (
                    self.EDUCATION_ROUTE
                    if route["emphasis"] == "Educación"
                    else self.HOUSING_ROUTE
                )
                narrations.append(
                    {
                        "id": route["scene_id"],
                        "narration": _fit_words(
                            route_text[milestone["year"]],
                            word_limits["narration"],
                        ),
                    }
                )
        generated = {
            "intro": _fit_words(self.INTRO, word_limits["narration"]),
            "narrations": narrations,
            "ending_summary": _fit_words(
                self.ENDING, word_limits["ending_summary"]
            ),
        }
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(generated, ensure_ascii=False)
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self, completions=None):
        self.chat = SimpleNamespace(completions=completions or FakeCompletions())


class FakeQuestionCompletions:
    def __init__(self):
        self.messages = None

    async def create(self, **kwargs):
        self.messages = kwargs["messages"]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="El plan conserva esas recomendaciones oficiales."
                    )
                )
            ]
        )


def _load_case(case_dir):
    financial_health = json.loads(
        (case_dir / "financial-health.json").read_text(encoding="utf-8")
    )
    investment_path = case_dir / "investment-analysis.json"
    investment = (
        json.loads(investment_path.read_text(encoding="utf-8"))
        if investment_path.exists()
        else {}
    )
    persona_path = case_dir / "persona.md"
    persona = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""
    return financial_health, {
        "financial_health_json": financial_health,
        "investment_analysis_json": investment,
        "persona_md": persona,
    }


def _profile():
    return {
        "members": [
            {
                "member_id": "member-1",
                "name": "Alex",
                "role": "adult",
                "interests": ["familia"],
                "aspirations": [],
                "concerns": [],
                "non_negotiables": [],
            }
        ],
        "family_priorities": ["education", "housing", "retirement"],
        "literacy": "beginner",
        "tone": "warm",
        "question": "¿Cómo se relacionan los objetivos con las decisiones del plan?",
    }


def _walk(story, next_scene_id):
    scene_map = {scene["id"]: scene for scene in story["scenes"]}
    visited = set()
    years = []
    current_id = next_scene_id
    while current_id != "ending":
        if current_id in visited:
            raise AssertionError(f"Cycle detected at {current_id}")
        visited.add(current_id)
        scene = scene_map[current_id]
        years.append(scene["year"])
        current_id = scene["next_scene_id"]
    return years


def _route_scene_ids(story, next_scene_id):
    scene_map = {scene["id"]: scene for scene in story["scenes"]}
    ids = []
    while next_scene_id != "ending":
        ids.append(next_scene_id)
        next_scene_id = scene_map[next_scene_id]["next_scene_id"]
    return ids


def _route_word_count(story, start_scene_id):
    scene_map = {scene["id"]: scene for scene in story["scenes"]}
    route_ids = _route_scene_ids(story, start_scene_id)
    return sum(
        len(scene_map[scene_id]["narration"].split())
        for scene_id in ("intro", "choose_topic", *route_ids, "ending")
    )


class StoryGeneratorTests(unittest.TestCase):
    def test_contract_shape_matches_the_v1_mock(self):
        mock = json.loads(
            (Path(__file__).parent / "mock" / "story_response.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(mock), STORY_FIELDS)
        self.assertEqual(set(mock["scenes"][0]), SCENE_FIELDS)

    def test_builds_two_chronological_routes_for_each_local_case(self):
        for case_dir in CASES_DIR.iterdir():
            if not case_dir.is_dir() or not (case_dir / "financial-health.json").exists():
                continue
            with self.subTest(case=case_dir.name):
                financial_health, case_raw = _load_case(case_dir)
                client = FakeClient()
                story = asyncio.run(
                    build_story_payload(
                        case_dir.name,
                        _profile(),
                        case_raw,
                        "local_case",
                        client,
                    )
                )
                scenes = {scene["id"]: scene for scene in story["scenes"]}
                choice = scenes["choose_topic"]
                request = client.chat.completions.last_request

                self.assertEqual(set(story), STORY_FIELDS)
                self.assertEqual(story["schema_version"], "1.0")
                self.assertTrue(all(set(scene) == SCENE_FIELDS for scene in story["scenes"]))
                self.assertEqual(len(choice["choices"]), 2)
                self.assertEqual(
                    request["intro_context"]["question"], _profile()["question"]
                )
                self.assertEqual(
                    request["official_recommendations_for_context_only"],
                    financial_health["narrative"]["summary_recommendations"],
                )

                paths = [
                    _walk(story, option["next_scene_id"])
                    for option in choice["choices"]
                ]
                self.assertEqual(paths[0], paths[1])
                self.assertEqual(paths[0], sorted(paths[0]))
                route_words = _route_word_count(
                    story, choice["choices"][0]["next_scene_id"]
                )
                self.assertGreaterEqual(route_words, 130)
                self.assertLessEqual(route_words, 190)

                expected_goal_refs = {
                    f"financial-health.json#goals.chartGoals[{index}]"
                    for index, goal in enumerate(
                        financial_health["goals"]["chartGoals"]
                    )
                    if _goal_theme(goal) is not None and goal.get("date")
                }
                actual_refs = {
                    reference
                    for scene in story["scenes"]
                    for reference in scene["source_refs"]
                }
                self.assertTrue(expected_goal_refs.issubset(actual_refs))
                self.assertFalse(any("BANKRUPTCY" in ref for ref in actual_refs))

                for year in paths[0]:
                    first = scenes[f"path_a_{year}"]
                    second = scenes[f"path_b_{year}"]
                    self.assertEqual(first["metric"], second["metric"])
                    self.assertEqual(first["source_refs"], second["source_refs"])
                    if first["metric"]:
                        for ref in first["metric"]["source_ref"].split("; "):
                            self.assertIn(ref, first["source_refs"])

                self.assertNotEqual(
                    scenes["ending"]["narration"],
                    financial_health["narrative"]["summary_recommendations"],
                )
                self.assertLessEqual(
                    len(scenes["ending"]["narration"].split()), 20
                )
                self.assertIn(
                    "financial-health.json#narrative.summary_recommendations",
                    scenes["ending"]["source_refs"],
                )

    def test_prompt_contains_relevant_plan_investment_persona_and_projection_context(self):
        _, case_raw = _load_case(TIMOTHY_CASE)
        client = FakeClient()
        asyncio.run(
            build_story_payload(
                TIMOTHY_CASE.name,
                _profile(),
                case_raw,
                "local_case",
                client,
            )
        )
        request = client.chat.completions.last_request
        routes = [
            route
            for milestone in request["timeline"]
            for route in milestone["routes"]
        ]
        recommendations_by_year = {
            milestone["year"]: milestone["routes"][0][
                "official_recommendation_evidence"
            ]
            for milestone in request["timeline"]
        }
        self.assertTrue(any(route["investment_context"] for route in routes))
        self.assertTrue(any(route["persona_context"] for route in routes))
        self.assertTrue(any(route["projection"]["facts"] for route in routes))
        self.assertTrue(
            any(route["official_recommendation_evidence"] for route in routes)
        )
        self.assertIn("near-term", recommendations_by_year[2027][0]["text"])
        self.assertIn("credit card", recommendations_by_year[2028][0]["text"])
        self.assertEqual(recommendations_by_year[2030], [])
        self.assertIn("college", recommendations_by_year[2038][0]["text"])
        self.assertIn("invested mix", recommendations_by_year[2048][0]["text"])
        self.assertTrue(
            any(
                ref.startswith("investment-analysis.json#")
                for scene in (
                    scene
                    for scene in routes
                )
                for ref in scene["source_refs"]
            )
        )

    def test_case_without_children_does_not_get_an_education_choice(self):
        case_dir = CASES_DIR / "michael-carter"
        _, case_raw = _load_case(case_dir)
        story = asyncio.run(
            build_story_payload(
                case_dir.name, _profile(), case_raw, "local_case", FakeClient()
            )
        )
        self.assertNotIn(
            "education",
            {choice["id"] for choice in next(
                scene for scene in story["scenes"] if scene["id"] == "choose_topic"
            )["choices"]},
        )

    def test_rejects_numeric_claims_not_supported_by_the_context(self):
        _, case_raw = _load_case(TIMOTHY_CASE)
        with self.assertRaises(StoryGenerationError):
            asyncio.run(
                build_story_payload(
                    TIMOTHY_CASE.name,
                    _profile(),
                    case_raw,
                    "local_case",
                    FakeClient(NumericFakeCompletions()),
                )
            )

    def test_accepts_a_source_backed_amount_in_generated_narration(self):
        _, case_raw = _load_case(TIMOTHY_CASE)
        story = asyncio.run(
            build_story_payload(
                TIMOTHY_CASE.name,
                _profile(),
                case_raw,
                "local_case",
                FakeClient(SupportedNumericFakeCompletions()),
            )
        )
        self.assertIn("$600,000", story["scenes"][0]["narration"])

    def test_requires_two_supported_focuses(self):
        case_dir = CASES_DIR / "michael-carter"
        _, case_raw = _load_case(case_dir)
        case_raw["financial_health_json"]["goals"]["chartGoals"] = [
            {
                "date": "2027-01-01T00:00:00.000Z",
                "goalType": "RETIREMENT",
                "name": "Retirement",
            }
        ]
        with self.assertRaises(StoryGenerationError):
            asyncio.run(
                build_story_payload(
                    case_dir.name,
                    _profile(),
                    case_raw,
                    "local_case",
                    FakeClient(),
                )
            )

    def test_generates_a_continuous_example_for_timothy_and_melanie(self):
        _, case_raw = _load_case(TIMOTHY_CASE)
        profile = _profile()
        profile["members"] = [
            {
                "member_id": "timothy",
                "name": "Timothy",
                "role": "adult",
                "interests": ["familia"],
                "aspirations": [],
                "concerns": [],
                "non_negotiables": [],
            },
            {
                "member_id": "melanie",
                "name": "Melanie",
                "role": "adult",
                "interests": ["familia"],
                "aspirations": [],
                "concerns": [],
                "non_negotiables": [],
            },
        ]
        story = asyncio.run(
            build_story_payload(
                TIMOTHY_CASE.name,
                profile,
                case_raw,
                "local_case",
                FakeClient(ExampleCompletions()),
            )
        )
        scenes = {scene["id"]: scene for scene in story["scenes"]}
        route = _route_scene_ids(story, scenes["choose_topic"]["choices"][0]["next_scene_id"])
        self.assertEqual(
            [scenes[scene_id]["year"] for scene_id in route],
            [2027, 2028, 2030, 2038, 2041, 2048],
        )
        self.assertGreaterEqual(
            _route_word_count(
                story, scenes["choose_topic"]["choices"][0]["next_scene_id"]
            ),
            130,
        )


class MCPSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_parsed_mcp_data_without_local_case_fallback(self):
        financial_health = {
            "score": {"published_score": 73},
            "narrative": {"summary_main": "Plan source"},
        }
        raw_mcp = {"financial_health": json.dumps(financial_health)}
        with (
            patch("mcp_sherpas.fetch_from_mcp_live", new=AsyncMock(return_value=raw_mcp)),
            patch("mcp_sherpas.load_from_local_cases", side_effect=AssertionError),
        ):
            case_data, data_status = await get_case_data("case")

        self.assertEqual(data_status, "mcp")
        self.assertEqual(case_data["financial_health_json"], financial_health)


class VideoQuestionTests(unittest.TestCase):
    def test_question_context_contains_the_complete_official_recommendations(self):
        financial_health, case_raw = _load_case(TIMOTHY_CASE)
        completions = FakeQuestionCompletions()
        client = FakeClient(completions)
        request = app.VideoQuestionRequest(
            case_id=TIMOTHY_CASE.name,
            question="¿Qué recomendaciones oficiales puedo revisar?",
            scene_title="Protección",
            scene_metric="",
            scene_narration="La escena resume una prioridad.",
        )

        with (
            patch(
                "app.get_case_data",
                new=AsyncMock(return_value=(case_raw, "local_case")),
            ),
            patch("app.get_llm_client", return_value=client),
        ):
            result = asyncio.run(app.ask_during_video(request))

        system_prompt = completions.messages[0]["content"]
        source_context = json.loads(
            system_prompt.split("FUENTES DEL CASO:\n", 1)[1]
        )
        self.assertEqual(result["answer"], "El plan conserva esas recomendaciones oficiales.")
        self.assertIn(
            financial_health["narrative"]["summary_recommendations"],
            source_context["official_recommendations"]["text"],
        )
        self.assertIn(
            "financial-health.json#narrative.summary_recommendations",
            source_context["official_recommendations"]["source_ref"],
        )


if __name__ == "__main__":
    unittest.main()
