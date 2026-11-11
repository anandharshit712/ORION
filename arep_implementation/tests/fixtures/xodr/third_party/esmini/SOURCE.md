# esmini OpenDRIVE samples

Unmodified copies of three maps from the esmini project, used as test fixtures
so the OpenDRIVE parser is exercised against files this project did not write.

- Project: https://github.com/esmini/esmini
- Path: `resources/xodr/`
- Commit: `435f1d39af162a15c6e57c2b2fbc696db85756c3` (latest change to that
  directory when fetched, 2026-11-12)
- Licence: Mozilla Public License 2.0, full text in `LICENSE` beside this file.
  The files are redistributed unmodified; their source is the URL above.

| File | SHA-256 | Why it is here |
| --- | --- | --- |
| `curves.xodr` | `a7288fd5d324a15ab5fc1477c1e24cd84354262eac2d527ff55656d818a7f874` | One 1154 m two-lane road of lines, arcs and clothoids; `XODR-002` drives its S-bend (s = 300 to ~520 m) |
| `e6mini.xodr` | `ae73414de34b41b0685ecb0dd291140eb5daa89ae7c2e8cd4087b35b0d4c6d92` | Divided highway in paramPoly3, with a median the parser approximates (reported in `warnings`) |
| `fabriksgatan_traffic_lights.xodr` | `b9e7f0d3be808445cbd2d7382cee01e1c15f3a5a47da9171fb55877956ba7463` | 16 roads, a four-way junction with three dynamic signals, `laneOffset` and `<object>` the parser reports rather than models |

Do not edit these files. To refresh, download from upstream and update the
commit and hashes here; `tests/test_xodr_third_party.py` checks the hashes.
