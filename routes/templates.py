import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from config import TEMPLATES_DIR
router = APIRouter(prefix="/templates", tags=["templates"])

os.makedirs(TEMPLATES_DIR, exist_ok=True)


def _path(name: str) -> str:
    # Ensure .json extension
    if not name.endswith(".json"):
        name = name + ".json"
    return os.path.join(TEMPLATES_DIR, name)


def _safe_name(name: str) -> str:
    return os.path.basename(name)


class TemplateBody(BaseModel):
    content: Any  # raw JSON object


@router.get("")
def list_templates():
    files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
    return {"templates": files}


@router.get("/{name}")
def get_template(name: str):
    path = _path(_safe_name(name))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    with open(path) as f:
        return json.load(f)


@router.post("")
def create_template(name: str, body: TemplateBody):
    path = _path(_safe_name(name))
    if os.path.exists(path):
        raise HTTPException(status_code=409, detail="Template already exists")
    with open(path, "w") as f:
        json.dump(body.content, f, indent=2)
    return {"name": os.path.basename(path)}


@router.put("/{name}")
def update_template(name: str, body: TemplateBody):
    path = _path(_safe_name(name))
    with open(path, "w") as f:
        json.dump(body.content, f, indent=2)
    return {"name": os.path.basename(path)}


@router.delete("/{name}")
def delete_template(name: str):
    path = _path(_safe_name(name))
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    os.remove(path)
    return {"deleted": os.path.basename(path)}
