# mcp_sherpas.py
import json
import logging
import os
from pathlib import Path
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from fastapi import HTTPException

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "cases"
logger = logging.getLogger(__name__)

def get_mcp_config():
    mcp_url = os.environ.get("MCP_URL", "https://mcp-hackathon.sherpaswealth.com/mcp").strip()
    mcp_token = os.environ.get("MCP_TOKEN", "").strip()
    if not mcp_token:
        raise ValueError("Falta MCP_TOKEN en la configuración local.")
    return mcp_url, {"Authorization": f"Bearer {mcp_token}"}

def extract_mcp_text(result) -> str:
    chunks = []
    for item in result.content:
        if hasattr(item, "text") and item.text:
            chunks.append(item.text)
        else:
            chunks.append(str(item))
    return "\n".join(chunks)

def parse_mcp_json(text: str, part: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"MCP devolvió JSON no válido para {part}.") from error
    if not isinstance(data, dict):
        raise ValueError(f"MCP devolvió un objeto no válido para {part}.")
    return data

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
        if not raw_mcp.get("financial_health"):
            raise ValueError("MCP no devolvió financial-health para el caso solicitado.")
        data = {
            "financial_health_json": parse_mcp_json(
                raw_mcp["financial_health"], "financial-health"
            )
        }
        if raw_mcp.get("investment_analysis"):
            data["investment_analysis_json"] = parse_mcp_json(
                raw_mcp["investment_analysis"], "investment-analysis"
            )
        if raw_mcp.get("persona"):
            data["persona_md"] = raw_mcp["persona"]
        return data, "mcp"
    except Exception as error:
        logger.warning("No se pudo usar el MCP; se consultarán los archivos locales: %s", error)

    local_data = load_from_local_cases(case_id)
    return local_data, "local_case"
