import json
import base64
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

MODO_PRUEBA = True  # Ponlo en False cuando vayas a presentar o probar con saldo real de IA/audio

load_dotenv(override=True)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "cases"
if not CASES_DIR.exists():
    for p in BASE_DIR.rglob("cases"):
        if p.is_dir():
            CASES_DIR = p
            break


class ChatRequest(BaseModel):
    case_id: str
    message: str
    history: list[dict] = []
    priorities: list[str] = []
    constraints: str = ""


class VideoQuestionRequest(BaseModel):
    case_id: str
    question: str
    scene_title: str
    scene_metric: str
    scene_narration: str


# ==============================================================================
# CLIENTE OFICIAL MCP DE SHERPAS (sherpas-hackathon-cases)
# ==============================================================================
def get_mcp_config():
    mcp_url = os.environ.get("MCP_URL", "https://mcp-hackathon.sherpaswealth.com/mcp").strip()
    mcp_token = os.environ.get("MCP_TOKEN", "").strip()
    if not mcp_token:
        raise ValueError("Falta MCP_TOKEN en el archivo .env")
    return mcp_url, {"Authorization": f"Bearer {mcp_token}"}


def extract_mcp_text(result) -> str:
    chunks = []
    for item in result.content:
        if hasattr(item, "text") and item.text:
            chunks.append(item.text)
        else:
            chunks.append(str(item))
    return "\n".join(chunks)


async def fetch_case_from_mcp(case_id: str, parts: list[str] | None = None) -> str:
    """Lee en vivo desde el MCP de Sherpas las partes del caso (persona, financial-health, investment-analysis)."""
    if parts is None:
        parts = ["persona", "financial-health", "investment-analysis"]

    mcp_url, headers = get_mcp_config()
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Traemos la cabecera general y cada una de las 3 partes del caso
                header_res = await session.call_tool("get_case", arguments={"caseId": case_id})
                sections = [f"=== RESUMEN DEL CASO ({case_id}) ===\n{extract_mcp_text(header_res)}"]

                for part in parts:
                    part_res = await session.call_tool("get_case", arguments={"caseId": case_id, "part": part})
                    # Limitamos cada bloque a 5000 caracteres para no saturar la ventana de contexto del LLM
                    sections.append(f"\n=== PARTE: {part.upper()} ===\n{extract_mcp_text(part_res)[:5000]}")

                return "\n".join(sections)


def load_local_fallback(case_id: str, max_json_chars: int = 12000) -> str:
    """Respaldo local por si en algún momento falla la red."""
    case_path = CASES_DIR / case_id
    if not case_path.exists():
        raise HTTPException(status_code=404, detail=f"No encuentro la carpeta {case_path}")
    context = ""
    for f in case_path.rglob("*.json"):
        content = json.loads(f.read_text(encoding="utf-8"))
        context += f"\n--- {f.stem} ---\n{json.dumps(content, ensure_ascii=False)[:max_json_chars]}\n"
    for f in case_path.rglob("*.md"):
        content = f.read_text(encoding="utf-8")
        context += f"\n--- {f.stem} ---\n{content[:5000]}\n"
    return context


async def get_case_context(case_id: str, parts: list[str] | None = None) -> str:
    """Prioriza siempre la lectura en directo desde el MCP de Sherpas."""
    try:
        mcp_data = await fetch_case_from_mcp(case_id, parts=parts)
        if mcp_data.strip():
            return mcp_data
    except Exception as e:
        print(f"[AVISO MCP] Error leyendo desde MCP ({e}). Usando respaldo local...")
    return load_local_fallback(case_id)


def get_llm_client() -> OpenAI:
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        raise ValueError("Todavía no has puesto tu TEAM_KEY real en el archivo .env")
    return OpenAI(
        base_url="https://llm-hackathon.sherpaswealth.com/v1",
        api_key=team_key,
        timeout=30.0,
        default_headers={"Accept-Encoding": "identity"},
    )


# ==============================================================================
# ENDPOINTS DE LA APLICACIÓN
# ==============================================================================
@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/mcp-cases")
async def list_mcp_cases():
    """Devuelve en vivo los 4 casos oficiales desde el servidor MCP de Sherpas."""
    try:
        mcp_url, headers = get_mcp_config()
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as http_client:
            async with streamable_http_client(mcp_url, http_client=http_client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool("list_cases", arguments={})
                    return {"status": "OK", "cases": extract_mcp_text(res)}
    except Exception as e:
        return {"status": "Error", "detail": str(e)}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if MODO_PRUEBA:
        return {
            "reply": f"[MODO PRUEBA - $0 gastados] Para {req.case_id}: conectado al MCP de Sherpas. Tu prioridad número 1 es optimizar tu liquidez y reducir deudas de alto interés."
        }

    try:
        context = await get_case_context(req.case_id)
        llm = get_llm_client()

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asesor financiero cercano y práctico. Ayudas a esta familia a entender "
                    "su situación económica sin tecnicismos y a mejorarla paso a paso. Usa solo los datos "
                    "proporcionados desde el MCP de Sherpas, responde en español y da cifras exactas en dólares.\n"
                    + context
                ),
            },
            *req.history[-6:],
            {"role": "user", "content": req.message},
        ]

        reply = llm.chat.completions.create(model="deepseek-flash", messages=messages)
        return {"reply": reply.choices[0].message.content}
    except Exception as e:
        return {"reply": f"⚠️ Error: {str(e)}"}


@app.post("/api/video-explainer")
async def generate_video_explainer(req: ChatRequest):
    priorities_text = ", ".join(req.priorities) if req.priorities else "Mejorar salud financiera global"
    constraints_text = req.constraints.strip() if req.constraints else "Ninguna restricción adicional"

    if MODO_PRUEBA:
        # En modo prueba también verificamos que el MCP responde en vivo sin gastar saldo de IA
        mcp_status = "MCP activo"
        try:
            await fetch_case_from_mcp(req.case_id, parts=["persona"])
        except Exception as e:
            mcp_status = f"Respaldo local ({e})"

        return {
            "scenes": [
                {
                    "title": f"1. Diagnóstico ({mcp_status})",
                    "narration": f"Analizando vuestro perfil desde Sherpas y vuestra prioridad de {priorities_text}, detectamos el punto exacto donde estáis perdiendo capacidad de ahorro.",
                    "metric_label": "Prioridad elegida",
                    "metric_value": priorities_text[:30],
                    "bar_before": 58,
                    "bar_after": 65,
                    "action_tip": f"Requisito respetado: {constraints_text}.",
                    "audio_b64": "",
                },
                {
                    "title": "2. Decisión #1: Acción inmediata",
                    "narration": "Eliminando primero los costes financieros más altos liberáis flujo de caja desde este mismo mes sin tocar vuestro colchón de seguridad.",
                    "metric_label": "Ahorro inmediato",
                    "metric_value": "+$6,800 optimizados",
                    "bar_before": 65,
                    "bar_after": 75,
                    "action_tip": "Ejecuta este primer paso esta misma semana.",
                    "audio_b64": "",
                },
                {
                    "title": "3. Decisión #2: Tu vida transformada",
                    "narration": "Con vuestra protección familiar blindada y el excedente trabajando al cuatro y medio por ciento, ganáis tranquilidad y patrimonio cada año.",
                    "metric_label": "Impacto anual estimado",
                    "metric_value": "+$9,808 / año",
                    "bar_before": 75,
                    "bar_after": 86,
                    "action_tip": "Automatiza el plan mensual para consolidar la mejora.",
                    "audio_b64": "",
                },
            ]
        }

    try:
        context = await get_case_context(req.case_id)
        llm = get_llm_client()

        prompt = (
            "Eres un planificador financiero experto. Diseña un guion de vídeo de 3 escenas con las MEJORES DECISIONES "
            "para transformar la vida de esta familia según sus prioridades y requisitos personales.\n"
            f"- PRIORIDADES ELEGIDAS POR LA FAMILIA: {priorities_text}\n"
            f"- REQUISITOS O LÍMITES PERSONALES (OBLIGATORIO RESPETAR): {constraints_text}\n\n"
            "Estructura obligatoria de las 3 escenas:\n"
            "Escena 1: Diagnóstico actual frente a su prioridad (cifras reales de su situación).\n"
            "Escena 2: Decisión #1 (acción inmediata de mayor impacto que cumple sus requisitos).\n"
            "Escena 3: Decisión #2 y transformación a 12 meses (cómo mejora su puntuación, liquidez y tranquilidad).\n\n"
            "Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown ni texto extra:\n"
            '{"scenes": [{"title": "Título corto", "narration": "Texto hablado natural de 2 frases max", '
            '"metric_label": "Etiqueta del dato clave", "metric_value": "$18,000 al 18%", '
            '"bar_before": 60, "bar_after": 78, "action_tip": "Consejo práctico en 1 línea"}]}\n\n'
            f"DATOS DE LA FAMILIA (DESDE MCP SHERPAS):\n{context}"
        )

        res = llm.chat.completions.create(
            model="gemini-3.5-flash-lite",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": req.message},
            ],
        )

        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        storyboard = json.loads(raw)

        for scene in storyboard.get("scenes", []):
            try:
                speech = llm.audio.speech.create(
                    model="eleven-flash-v2.5",
                    voice="alloy",
                    input=scene["narration"],
                )
                scene["audio_b64"] = base64.b64encode(speech.read()).decode("utf-8")
            except Exception:
                scene["audio_b64"] = ""

        return storyboard
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/video-ask")
async def ask_during_video(req: VideoQuestionRequest):
    if MODO_PRUEBA:
        answer = (
            f"[MODO PRUEBA] Buena pregunta sobre '{req.scene_title}'. "
            f"Esa cifra de {req.scene_metric} sale directamente de vuestros datos en Sherpas "
            "para mejorar vuestra estabilidad sin comprometer vuestra liquidez."
        )
        return {"answer": answer, "audio_b64": ""}

    try:
        context = await get_case_context(req.case_id)
        llm = get_llm_client()

        system_prompt = (
            "El usuario está viendo un vídeo explicativo sobre sus finanzas y lo ha pausado para hacerte una duda en directo. "
            "Responde de forma muy clara, cercana y breve (máximo 3 frases) para que pueda escucharse en voz alta y continuar el vídeo.\n\n"
            f"ESCENA ACTUAL DEL VÍDEO:\n- Título: {req.scene_title}\n- Dato en pantalla: {req.scene_metric}\n- Lo que estabas explicando: {req.scene_narration}\n\n"
            f"DATOS DE LA FAMILIA (DESDE MCP SHERPAS):\n{context}"
        )

        res = llm.chat.completions.create(
            model="gemini-3.5-flash-lite",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.question},
            ],
        )
        answer = res.choices[0].message.content.strip()

        audio_b64 = ""
        try:
            speech = llm.audio.speech.create(
                model="eleven-flash-v2.5",
                voice="alloy",
                input=answer,
            )
            audio_b64 = base64.b64encode(speech.read()).decode("utf-8")
        except Exception:
            pass

        return {"answer": answer, "audio_b64": audio_b64}
    except Exception as e:
        return {"answer": f"Error: {str(e)}", "audio_b64": ""}