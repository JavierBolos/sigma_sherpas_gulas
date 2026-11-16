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


MODO_PRUEBA = True

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

def load_case_text(case_id: str, max_json_chars: int = 12000) -> str:
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
    if not context:
        raise HTTPException(status_code=404, detail=f"La carpeta {case_path} está vacía")
    return context

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

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")

@app.post("/api/chat")
def chat(req: ChatRequest):
    if MODO_PRUEBA:
        return {
            "reply": f"[MODO PRUEBA - $0 gastados] Para {req.case_id}: tu prioridad número 1 es usar $6,800 de tu efectivo para bajar la tarjeta Chase (18% TAE) y subir tu seguro de vida."
        }

    try:
        context = load_case_text(req.case_id, max_json_chars=12000)
        llm = get_llm_client()

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un asesor financiero cercano y práctico. Ayudas a esta familia a entender "
                    "su situación económica sin tecnicismos y a mejorarla paso a paso. Usa solo los datos "
                    "proporcionados, responde en español y da cifras exactas en dólares.\n" + context
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
def generate_video_explainer(req: ChatRequest):
    if MODO_PRUEBA:
        return {
            "scenes": [
                {
                    "title": "El candado de tu tarjeta Chase",
                    "narration": "Estás pagando un 18 por ciento de interés en tu tarjeta mientras tienes 150 mil dólares en efectivo ganando casi nada.",
                    "metric_label": "Deuda cara vs Efectivo",
                    "metric_value": "$18,000 al 18%",
                    "bar_before": 60,
                    "bar_after": 62,
                    "action_tip": "Usa $6,800 de tu efectivo hoy para desbloquear tu puntuación.",
                    "audio_b64": "",
                },
                {
                    "title": "Protección para Liam y Josh",
                    "narration": "Vuestro seguro de vida actual deja un hueco de más de un millón de dólares si ocurre un imprevisto.",
                    "metric_label": "Cobertura recomendada",
                    "metric_value": "+$491,800 mínimos",
                    "bar_before": 62,
                    "bar_after": 73,
                    "action_tip": "Amplía las pólizas justo después de reducir la tarjeta.",
                    "audio_b64": "",
                },
                {
                    "title": "Pon a trabajar tu excedente",
                    "narration": "Moviendo tu reserva a una cuenta competitiva puedes ganar casi diez mil dólares extra al año sin riesgo.",
                    "metric_label": "Ingresos extra anuales",
                    "metric_value": "+$9,808 / año",
                    "bar_before": 73,
                    "bar_after": 78,
                    "action_tip": "Mueve el efectivo a una cuenta remunerada al 4.5%.",
                    "audio_b64": "",
                },
            ]
        }

    try:
        context = load_case_text(req.case_id, max_json_chars=10000)
        llm = get_llm_client()

        prompt = (
            "Crea un guion de vídeo explicativo de 3 escenas muy claras para responder a la duda de esta familia. "
            "Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta, sin markdown ni texto extra:\n"
            '{"scenes": [{"title": "Título corto", "narration": "Texto hablado natural de 2 frases max", '
            '"metric_label": "Etiqueta del dato clave", "metric_value": "$18,000 al 18%", '
            '"bar_before": 60, "bar_after": 78, "action_tip": "Consejo práctico en 1 línea"}]}\n\n'
            f"DATOS FAMILIA:\n{context}"
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
    
class VideoQuestionRequest(BaseModel):
    case_id: str
    question: str
    scene_title: str
    scene_metric: str
    scene_narration: str

@app.post("/api/video-ask")
def ask_during_video(req: VideoQuestionRequest):
    if MODO_PRUEBA:
        answer = (
            f"[MODO PRUEBA] Buena pregunta sobre '{req.scene_title}'. "
            f"Esa cifra de {req.scene_metric} cubre los años clave hasta que vuestros hijos sean independientes "
            "sin que tengáis que tocar vuestros ahorros."
        )
        return {"answer": answer, "audio_b64": ""}

    try:
        context = load_case_text(req.case_id, max_json_chars=10000)
        llm = get_llm_client()

        system_prompt = (
            "El usuario está viendo un vídeo explicativo sobre sus finanzas y lo ha pausado para hacerte una duda en directo. "
            "Responde de forma muy clara, cercana y breve (máximo 3 frases) para que pueda escucharse en voz alta y continuar el vídeo.\n\n"
            f"ESCENA ACTUAL DEL VÍDEO:\n- Título: {req.scene_title}\n- Dato en pantalla: {req.scene_metric}\n- Lo que estabas explicando: {req.scene_narration}\n\n"
            f"DATOS DE LA FAMILIA:\n{context}"
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