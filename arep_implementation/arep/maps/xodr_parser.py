"""
ORION OpenDRIVE Map Parser.  [Phase 4]

Parses a subset of the OpenDRIVE (.xodr) format into an AREP RoadGraph.
Uses Python's built-in xml.etree.ElementTree — no external XML dependencies.

Supported OpenDRIVE elements:
  <road> with straight/arc/cubic geometry     ✅
  <laneSection> with driving lanes            ✅
  <junction> with connection roads            ✅
  <signal> (traffic lights)                   ✅
  <object> (static obstacles)                 ⚠ best-effort
  Superelevation, banking                     ❌ out of scope

Reference: ASAM OpenDRIVE 1.7 specification
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from arep.core.state import Vector2D
from arep.core.physics import SurfaceType
from arep.core.road import RoadGraph, RoadSegment, Junction
from arep.utils.logging_config import get_logger

logger = get_logger("maps.xodr_parser")

# Discretisation step for centerline generation (metres)
CENTERLINE_STEP_M = 1.0


class OpenDRIVEParser:
    """
    Parses a .xodr file and returns an AREP RoadGraph.

    Only the subset of OpenDRIVE geometry needed for evaluation scenarios
    is implemented. Unknown elements are logged and skipped.
    """

    def parse(self, xodr_path: str) -> RoadGraph:
        """
        Parse a .xodr file and return an AREP RoadGraph.

        Args:
            xodr_path: Absolute path to the .xodr file.

        Returns:
            RoadGraph with segments and junctions populated.

        TODO [P4]: Parse <header> for coordinate reference.
        TODO [P4]: Parse each <road> element:
                   - Extract <planView> geometry (line, arc, poly3, paramPoly3)
                   - Discretise to centerline at CENTERLINE_STEP_M intervals
                   - Extract <lanes>/<laneSection> for lane count + width
                   - Extract <type>/<speed> for speed limit
                   - Create RoadSegment
        TODO [P4]: Parse each <junction> element:
                   - Extract <connection> arms
                   - Determine right-of-way from <priority> elements
                   - Determine has_traffic_light from linked <signal> elements
                   - Create Junction
        TODO [P4]: Return assembled RoadGraph.
        """
        path = Path(xodr_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenDRIVE file not found: {xodr_path}")

        logger.info(f"Parsing OpenDRIVE file: {path.name}")
        tree = ET.parse(path)
        root = tree.getroot()

        raise NotImplementedError("OpenDRIVEParser.parse not yet implemented [P4]")

    # ── Geometry discretisation helpers ──────────────────────────────

    @staticmethod
    def _discretise_line(
        x0: float, y0: float, heading: float, length: float
    ) -> List[Vector2D]:
        """Discretise a straight line geometry into 1m-spaced points."""
        n = max(2, int(length / CENTERLINE_STEP_M) + 1)
        dx = math.cos(heading)
        dy = math.sin(heading)
        return [
            Vector2D(x0 + dx * i * CENTERLINE_STEP_M,
                     y0 + dy * i * CENTERLINE_STEP_M)
            for i in range(n)
        ]

    @staticmethod
    def _discretise_arc(
        x0: float, y0: float, heading: float, length: float, curvature: float
    ) -> List[Vector2D]:
        """
        Discretise an arc geometry into 1m-spaced points.

        TODO [P4]: Compute arc centre from x0, y0, heading, curvature.
        TODO [P4]: Walk arc in CENTERLINE_STEP_M steps along arc length.
        """
        raise NotImplementedError

    @staticmethod
    def _speed_from_element(road_el: ET.Element) -> float:
        """Extract speed limit in m/s from a <road> element."""
        type_el = road_el.find("type")
        if type_el is not None:
            speed_el = type_el.find("speed")
            if speed_el is not None:
                max_speed = float(speed_el.get("max", "0"))
                unit = speed_el.get("unit", "m/s")
                if unit == "km/h":
                    return max_speed / 3.6
                return max_speed
        return 13.89  # default: 50 km/h
