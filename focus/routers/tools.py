from fastapi import APIRouter

from focus.tools.builtin import ALL_TOOLS

router = APIRouter()


@router.get("/tools")
async def list_tools():
    return [
        {
            "name": t.name,
            "description": t.description,
            "params": [{"name": p.name, "type": p.type} for p in t.params],
            "writes": t.writes,
            "multimodal": t.multimodal,
        }
        for t in ALL_TOOLS
    ]
