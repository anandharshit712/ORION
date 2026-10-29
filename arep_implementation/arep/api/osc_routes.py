"""
OpenSCENARIO 2.0 import / export over HTTP (Phase 4.4).

    GET  /api/scenarios/{scenario_id}/export/osc   library scenario → .osc text
    POST /api/scenarios/import/osc                 .osc text → parsed scenario

Import is parse-and-validate only. ORION scenarios are files in the library,
and there is no org-scoped scenario storage to put an imported one in, so the
response hands back the scenario (in the YAML shape `ScenarioParser` reads),
every line the reader skipped, and the validator's verdict. Persisting it is a
storage design nobody has made yet.

Both are a reader/writer for ORION's modelled OSC2 subset — see
`arep/scenario/osc_importer.py` — not a conforming OSC2 implementation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from arep.api.auth import get_request_principal
from arep.scenario.osc_exporter import OpenSCENARIOExporter
from arep.scenario.osc_importer import OpenSCENARIOImporter
from arep.scenario.parser import ScenarioParser
from arep.scenario.validator import ScenarioValidator

osc_router = APIRouter(
    prefix="/api/scenarios",
    tags=["Scenarios"],
    dependencies=[Depends(get_request_principal)],
)

# An exported library scenario is about 5 KB. 256 KB is generous for a
# hand-written file and small enough that the line reader's cost is trivial.
MAX_OSC_BYTES = 256 * 1024

# Library ids only (LON-003). The id goes into a glob, so anything else — a
# path, a wildcard — is refused before it gets there.
_SCENARIO_ID_RE = re.compile(r"^[A-Z]{3}-\d{3}$")
_LIBRARY = Path(__file__).resolve().parents[3] / "scenarios"


class OscImportResponse(BaseModel):
    valid: bool
    scenario: Dict[str, Any]
    skipped: List[str]
    validation_errors: List[str]


@osc_router.get("/{scenario_id}/export/osc", response_class=PlainTextResponse)
def export_osc(scenario_id: str) -> PlainTextResponse:
    """A library scenario as OpenSCENARIO 2.0 DSL."""
    if not _SCENARIO_ID_RE.match(scenario_id):
        raise HTTPException(400, f"Not a scenario id: {scenario_id!r} (e.g. LON-003)")
    matches = sorted(_LIBRARY.glob(f"*/{scenario_id}_*.yaml"))
    if not matches:
        raise HTTPException(404, f"Scenario not found: {scenario_id}")

    try:
        scenario, _ = ScenarioParser().parse_file(matches[0])
        osc = OpenSCENARIOExporter().export(scenario)
    except Exception as exc:  # noqa: BLE001 - a scenario that will not load or export
        raise HTTPException(422, f"{scenario_id} cannot be exported: {exc}")

    return PlainTextResponse(
        osc,
        headers={"Content-Disposition": f'attachment; filename="{scenario_id}.osc"'},
    )


@osc_router.post("/import/osc", response_model=OscImportResponse)
async def import_osc(request: Request) -> OscImportResponse:
    """Parse and validate an .osc file sent as the raw request body."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_OSC_BYTES:
        raise HTTPException(413, f"OSC file too large (max {MAX_OSC_BYTES} bytes)")
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_OSC_BYTES:
            raise HTTPException(413, f"OSC file too large (max {MAX_OSC_BYTES} bytes)")

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "OSC file must be UTF-8 text")

    try:
        scenario, skipped = OpenSCENARIOImporter().read(text, source="upload")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    errors = ScenarioValidator().validate(scenario)
    data = scenario.to_dict()
    # to_dict() predates these fields; added so the result re-parses as a
    # scenario file without losing its topology, seed or ranges.
    road = data["environment"]["road"]
    road.setdefault("template", scenario.road.template)
    road.setdefault("template_params", scenario.road.template_params)
    data.setdefault("master_seed", scenario.master_seed)
    data.setdefault("parameterization", scenario.parameterization)

    return OscImportResponse(
        valid=not errors,
        scenario=data,
        skipped=skipped,
        validation_errors=errors,
    )
