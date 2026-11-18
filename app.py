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
from typing import List
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
        base_url="https://llm-hackathon.sherpaswealth.com/v1",
        api_key=team_key,
        timeout=30.0
    )

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")

@app.post("/api/story")
async def create_story(req: StoryRequest):
    """
    Main endpoint required by the contract.
    Receives the questionnaire and returns the story scenes in JSON.
    """
    if req.case_id not in ["timothy-melanie-weah", "michael-carter", "daniel-emily-johnson", "samantha-lewis"]:
        raise HTTPException(status_code=400, detail=f"Invalid case_id '{req.case_id}'")

    # 1. Fetch data (live MCP or local fallback)
    case_data, data_status = await get_case_data(req.case_id)

    # 2. Build the structured story payload including the user's question
    try:
        payload = build_story_payload(
            case_id=req.case_id,
            profile_data=req.profile.model_dump(),
            case_raw=case_data,
            data_status=data_status,
            question=req.question
        )
    except TypeError:
        payload = build_story_payload(
            case_id=req.case_id,
            profile_data=req.profile.model_dump(),
            case_raw=case_data,
            data_status=data_status
        )

    return payload

@app.post("/api/video-ask")
async def ask_during_video(req: VideoQuestionRequest):
    """
    Answers live questions in English while the user pauses the interactive video.
    """
    team_key = os.environ.get("TEAM_KEY", "").strip()
    
    # Fallback when TEAM_KEY is missing
    if not team_key or "pega_aqui" in team_key:
        answer = (
            f"Regarding '{req.scene_title}': that figure ({req.scene_metric}) comes directly from "
            "your Sherpas financial plan to optimize savings while protecting liquidity."
        )
        return {"answer": answer, "audio_b64": ""}

    try:
        llm = get_llm_client()
        system_prompt = (
            "You are Sherpas Wealth's trusted financial advisor. The user is watching their personalized "
            "financial story video and paused to ask a live question. Answer in natural, fluent English "
            "in 2 or 3 clear, warm, conversational sentences (under 55 words), grounded strictly in the "
            "current scene context. Do not use markdown, parentheses, or bullet points.\n\n"
            f"CURRENT SCENE:\n- Title: {req.scene_title}\n- Metric: {req.scene_metric}\n- Narration: {req.scene_narration}"
        )

        res = llm.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.question}
            ]
        )
        answer = res.choices[0].message.content.strip()

        # --- TTS generation with ElevenLabs (Base64) ---
        audio_b64 = ""
        try:
            speech_res = llm.audio.speech.create(
                model="eleven-flash-v2.5",
                voice="alloy",
                input=answer
            )
            audio_b64 = base64.b64encode(speech_res.content).decode("utf-8")
        except Exception as tts_err:
            print("[TTS ERROR en /api/video-ask]:", repr(tts_err))
            audio_b64 = ""

        return {"answer": answer, "audio_b64": audio_b64}

    except Exception as err:
        print("[LLM ERROR en /api/video-ask]:", repr(err))
        return {"answer": f"Based on your Sherpas plan data: {req.scene_metric}", "audio_b64": ""}

class CheckinRequest(BaseModel):
    case_id: str
    completed_moves: List[str] = []
    pending_moves: List[str] = []
    current_score: int = 0
    projected_score: int = 0
    user_note: str = ""

@app.post("/api/checkin")
async def family_checkin(req: CheckinRequest):
    """
    Evaluates family progress on their recommended top_moves and gives spoken feedback.
    """
    team_key = os.environ.get("TEAM_KEY", "").strip()
    if not team_key or "pega_aqui" in team_key:
        answer = (
            f"Great progress! Completing {len(req.completed_moves)} action(s) brings your "
            f"projected financial health score from {req.current_score} to {req.projected_score} out of 100."
        )
        return {"feedback": answer, "audio_b64": ""}

    try:
        llm = get_llm_client()
        system_prompt = (
            "You are Sherpas Wealth's financial coach doing a quick progress check-in with a family. "
            "Respond in natural, encouraging English in 2 short sentences (under 45 words), referencing "
            "their completed moves, updated score, and the single most important next action. No markdown."
        )
        user_msg = (
            f"Household: {req.case_id}\n"
            f"Completed actions: {req.completed_moves}\n"
            f"Pending actions: {req.pending_moves}\n"
            f"Score: {req.current_score} -> {req.projected_score}/100\n"
            f"Family update note: {req.user_note or 'Routine check-in'}"
        )
        res = llm.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )
        feedback = res.choices[0].message.content.strip()

        audio_b64 = ""
        try:
            speech_res = llm.audio.speech.create(
                model="eleven-flash-v2.5",
                voice="alloy",
                input=feedback,
            )
            audio_b64 = base64.b64encode(speech_res.content).decode("utf-8")
        except Exception:
            audio_b64 = ""

        return {"feedback": feedback, "audio_b64": audio_b64}
    except Exception:
        return {
            "feedback": f"You are on track: your score rises to {req.projected_score} out of 100.",
            "audio_b64": "",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)