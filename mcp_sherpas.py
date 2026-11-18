# mcp_sherpas.py
import json
import os
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from fastapi import HTTPException

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "cases"

def get_mcp_config():
    mcp_url = os.environ.get("MCP_URL", "https://mcp-hackathon.sherpaswealth.com/mcp").strip()
    mcp_token = os.environ.get("MCP_TOKEN", "").strip()
    return mcp_url, {"Authorization": f"Bearer {mcp_token}"}

def extract_mcp_text(result) -> str:
    chunks = []
    for item in result.content:
        if hasattr(item, "text") and item.text:
            chunks.append(item.text)
        else:
            chunks.append(str(item))
    return "\n".join(chunks)

async def fetch_from_mcp_live(case_id: str) -> dict:
    """Intenta traer el caso completo desde el servidor MCP."""
    mcp_url, headers = get_mcp_config()
    if not headers.get("Authorization"):
        raise ValueError("Falta MCP_TOKEN en .env")

    async with httpx.AsyncClient(headers=headers, timeout=15.0) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Traemos las 3 partes
                fh_res = await session.call_tool("get_case", arguments={"caseId": case_id, "part": "financial-health"})
                inv_res = await session.call_tool("get_case", arguments={"caseId": case_id, "part": "investment-analysis"})
                per_res = await session.call_tool("get_case", arguments={"caseId": case_id, "part": "persona"})
                
                return {
                    "financial_health": extract_mcp_text(fh_res),
                    "investment_analysis": extract_mcp_text(inv_res),
                    "persona": extract_mcp_text(per_res)
                }

def load_from_local_cases(case_id: str) -> dict:
    """Respaldo local leyendo directamente la carpeta cases/."""
    case_path = CASES_DIR / case_id
    if not case_path.exists():
        raise HTTPException(status_code=404, detail=f"No se encontró la carpeta para {case_id}")

    data = {}
    fh_file = case_path / "financial-health.json"
    inv_file = case_path / "investment-analysis.json"
    per_file = case_path / "persona.md"

    if fh_file.exists():
        data["financial_health_json"] = json.loads(fh_file.read_text(encoding="utf-8"))
    if inv_file.exists():
        data["investment_analysis_json"] = json.loads(inv_file.read_text(encoding="utf-8"))
    if per_file.exists():
        data["persona_md"] = per_file.read_text(encoding="utf-8")

    return data

async def get_case_data(case_id: str) -> tuple[dict, str]:
    """
    Obtiene los datos del caso y devuelve (datos, data_status).
    data_status será 'mcp' si se leyó en vivo, o 'local_case' si usó el fallback.
    """
    try:
        raw_mcp = await fetch_from_mcp_live(case_id)
        if raw_mcp.get("financial_health"):
            # Para facilitar la extracción, también leemos el JSON local si existe
            local_fallback = load_from_local_cases(case_id)
            local_fallback["mcp_raw"] = raw_mcp
            return local_fallback, "mcp"
    except Exception as e:
        print(f"[AVISO B] No se pudo conectar al MCP ({e}). Usando datos locales de cases/...")

    local_data = load_from_local_cases(case_id)
    return local_data, "local_case"
