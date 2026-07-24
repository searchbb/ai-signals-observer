from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_site_data import parse_research_objects  # noqa: E402


def test_canonical_object_is_available_without_legacy_database(tmp_path: Path) -> None:
    projection = (
        tmp_path
        / "data"
        / "semantic_pipeline_v2"
        / "research_assets"
        / "projections"
        / "api_read_model.json"
    )
    projection.parent.mkdir(parents=True)
    projection.write_text(
        json.dumps(
            {
                "profiles": {
                    "obj_archetype_agent_platform": {
                        "object": {
                            "id": "obj_archetype_agent_platform",
                            "name": "AI 开发 / Agent 平台",
                            "kind": "archetype",
                            "status": "active",
                            "description": "长期观察 Agent 平台。",
                            "fact_count": 1,
                            "latest_update_at": "2026-07-24T08:00:00Z",
                            "updates_24h": [
                                {
                                    "fact_id": "fact-1",
                                    "statement": "Token 成本下降90%",
                                    "published_at": "2026-07-24T08:00:00Z",
                                    "evidence_id": "article:news-1:evidence",
                                }
                            ],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    objects = parse_research_objects(repo_root=tmp_path)

    assert [item["id"] for item in objects] == ["obj_archetype_agent_platform"]
    assert objects[0]["updates"][0]["event"] == "Token 成本下降90%"
    assert "Token 成本下降90%" in objects[0]["html"]
