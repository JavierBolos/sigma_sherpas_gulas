# app.py
import os
import base64
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI

from mcp_sherpas import get_case_data
from story_generator import build_story_payload

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Sherpas Hackathon - Backend Frente B")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos (javascript/css)
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Modelos Pydantic según CONTRATO_JSON_v1
class Member(BaseModel):
    member_id: str
    name: str
    role: str
    interests: List[str] = []
    aspirations: List[str] = []
    concerns: List[str] = []
    non_negotiables: List[str] = []

class Profile(BaseModel):
    members: List[Member]
    family_priorities: List[str]
    literacy: str
    tone: str

class StoryRequest(BaseModel):
    schema_version: str
    case_id: str
    profile: Profile
    question: str

class VideoQuestionRequest(BaseModel):
    case_id: str
    question: str
    scene_title: str
    scene_metric: str = ""
    scene_narration: str = ""

def get_llm_client() -> OpenAI:
    team_key = os.environ.get("TEAM_KEY", "").strip()
    return OpenAI(
        base_url="https://llm-hackathon.sherpaswealth.com",
        api_key=team_key,
        timeout=30.0
    )

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")

@app.post("/api/story")
async def create_story(req: StoryRequest):
    """
    Endpoint principal exigido por el contrato.
    Recibe el cuestionario y devuelve las escenas en JSON.
    """
    if req.case_id not in ["timothy-melanie-weah", "michael-carter", "daniel-emily-johnson", "samantha-lewis"]:
        raise HTTPException(status_code=400, detail=f"case_id '{req.case_id}' no es válido")

    # 1. Obtener datos (MCP en vivo o fallback local)
    case_data, data_status = await get_case_data(req.case_id)

    # 2. Construir la respuesta estructurada
    payload = build_story_payload(
        case_id=req.case_id,
        profile_data=req.profile.dict(),
        case_raw=case_data,
        data_status=data_status
    )

    return payload

@app.post("/api/video-ask")
async def ask_during_video(req: VideoQuestionRequest):
    """
    Responde a dudas en tiempo real durante la reproducción del vídeo.
    """
    team_key = os.environ.get("TEAM_KEY", "")
    
    # Si no hay clave configurada o estamos probando sin saldo
    if not team_key or "pega_aqui" in team_key:
        answer = (
            f"Sobre '{req.scene_title}': esa cifra ({req.scene_metric}) proviene de "
            "vuestro plan financiero de Sherpas para optimizar el ahorro sin perder liquidez."
        )
        return {"answer": answer, "audio_b64": ""}

    try:
        llm = get_llm_client()
        system_prompt = (
            "El usuario está viendo un vídeo explicativo sobre su plan financiero y lo ha pausado para hacer una duda en directo. "
            "Responde en máximo 3 frases, de forma clara, empática y cercana.\n\n"
            f"ESCENA ACTUAL:\n- Título: {req.scene_title}\n- Cifra: {req.scene_metric}\n- Explicación: {req.scene_narration}"
        )

        res = llm.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.question}
            ]
        )
        answer = res.choices[0].message.content.strip()
        # --- Generación de audio TTS (Base64) ---
        
        audio_b64 = ""
        try:
            speech_res = llm.audio.speech.create(
                model="tts-1",
                voice="alloy",  # Voces disponibles: alloy, echo, fable, onyx, nova, shimmer
                input=answer
            )
            audio_b64 = base64.b64encode(speech_res.content).decode("utf-8")
        except Exception:
            # Si el proxy no soporta TTS o falla la petición, devuelve texto normal sin dar error 500
            audio_b64 = ""

        return {"answer": answer, "audio_b64": audio_b64}

    except Exception as e:
        return {"answer": f"Respuesta basada en datos de Sherpas: {req.scene_metric}", "audio_b64": ""}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
