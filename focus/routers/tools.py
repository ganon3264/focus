from fastapi import APIRouter

from focus.tools.builtin import get_all_tools, reload_tools

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
        for t in get_all_tools()
    ]


@router.post("/tools/reload")
async def reload_external_tools():
    tools = reload_tools()
    return {"ok": True, "count": len(tools)}
