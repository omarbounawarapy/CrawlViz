import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from config import TEMPLATES_DIR
from config.blueprint_schema import BlueprintSchemaError, validate_blueprint
from config.template_names import TEMPLATE_SUFFIX, InvalidTemplateNameError, resolve_template_path

router = APIRouter(prefix="/templates", tags=["templates"])

os.makedirs(TEMPLATES_DIR, exist_ok=True)


def _path(name: str) -> str:
    """The blueprint file for ``name`` (suffix optional); 422 unless it is a plain name."""
    if not name.endswith(TEMPLATE_SUFFIX):
        name = name + TEMPLATE_SUFFIX
    try:
        return str(resolve_template_path(TEMPLATES_DIR, name))
    except InvalidTemplateNameError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class TemplateBody(BaseModel):
    content: Any  # raw JSON object


def _validated(content: Any) -> Any:
    try:
        validate_blueprint(content)
    except BlueprintSchemaError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return content


@router.get("")
def list_templates():
    files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
    return {"templates": files}


@router.get("/{name}")
def get_template(name: str):
    path = _path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    with open(path) as f:
        return json.load(f)


@router.post("")
def create_template(name: str, body: TemplateBody):
    path = _path(name)
    if os.path.exists(path):
        raise HTTPException(status_code=409, detail="Template already exists")
    content = _validated(body.content)
    with open(path, "w") as f:
        json.dump(content, f, indent=2)
    return {"name": os.path.basename(path)}


@router.put("/{name}")
def update_template(name: str, body: TemplateBody):
    path = _path(name)
    content = _validated(body.content)
    with open(path, "w") as f:
        json.dump(content, f, indent=2)
    return {"name": os.path.basename(path)}


@router.delete("/{name}")
def delete_template(name: str):
    path = _path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    os.remove(path)
    return {"deleted": os.path.basename(path)}
