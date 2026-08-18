from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_site_data import (  # noqa: E402
    parse_news_rows,
    parse_research_objects,
    public_research_evidence_quote,
)
from sync_portal_data import (  # noqa: E402
    discover_recent_sent_mail_news_ids,
    preserve_existing_collections,
)


def test_public_research_evidence_quote_removes_private_provenance_marker() -> None:
    assert public_research_evidence_quote("公开产品数据与客户结果") == (
        "公开产品数据与客户结果"
    )
    assert public_research_evidence_quote(
        "会议纪要作为协作语境进入需求上下文"
    ) == ""


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
                "catalog": {
                    "status": "ready",
                    "schema_version": 4,
                    "read_only": True,
                    "objects": [],
                    "groupings": {},
                },
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
    (projection.parent / "research_briefs.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {
                    "obj_archetype_agent_platform": {
                        "brief_id": "brief-agent",
                        "research_object_id": "obj_archetype_agent_platform",
                        "agenda": {
                            "question": "Agent 使用是否转化为付费工作流？",
                            "rationale": "关注任务完成、留存和单位任务经济。",
                        },
                        "current_judgment": "目前需要把活跃与生产采用分开。",
                        "what_changed": "新增了 Token 成本证据。",
                        "known_claims": [],
                        "open_gaps": ["生产任务完成率"],
                        "next_actions": ["补正式客户和留存"],
                        "counterevidence": ["活跃可能来自试用"],
                        "model_runs": [],
                        "as_of": "2026-07-24T09:00:00Z",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    topic_report = projection.parent.parent / "topic_reports" / "obj_archetype_agent_platform.json"
    topic_report.parent.mkdir(parents=True)
    topic_report.write_text(
        json.dumps(
            {
                "title": "Agent 平台竞争不只取决于模型",
                "central_question": "谁先进入生产？",
                "executive_thesis": "任务控制权与可重复交付共同决定生产成熟度。",
                "path_comparison": [{"path": "工具 Agent"}],
                "audit": {"schema_version": "kfc_topic_report_v2"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    objects = parse_research_objects(repo_root=tmp_path)

    assert [item["id"] for item in objects] == ["obj_archetype_agent_platform"]
    assert objects[0]["updates"][0]["event"] == "Token 成本下降90%"
    assert "Token 成本下降90%" in objects[0]["html"]
    assert objects[0]["researchBrief"]["agenda"]["question"] == (
        "Agent 使用是否转化为付费工作流？"
    )
    assert objects[0]["updatedAt"] == "2026-07-24T09:00:00Z"
    assert objects[0]["topicReport"]["title"] == "Agent 平台竞争不只取决于模型"


def test_required_mail_news_replaces_window_tail_instead_of_expanding_it(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "news_library" / "news_library.sqlite3"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE news_articles(
                article_id TEXT PRIMARY KEY,
                source_id TEXT,
                title_zh TEXT,
                title_original TEXT,
                title_en TEXT,
                canonical_url TEXT,
                published_at TEXT,
                first_seen_at TEXT,
                digest_status TEXT,
                digested_at TEXT,
                last_seen_at TEXT,
                summary_zh TEXT,
                summary_original TEXT,
                digest_result_summary TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO news_articles VALUES(
                ?, 'source', ?, '', '', '', ?, ?, 'keep', '', ?, ?, '', ''
            )
            """,
            [
                (
                    "news-newest",
                    "最新",
                    "2026-07-26T03:00:00Z",
                    "2026-07-26T03:00:00Z",
                    "2026-07-26T03:00:00Z",
                    "最新摘要",
                ),
                (
                    "news-middle",
                    "中间",
                    "2026-07-26T02:00:00Z",
                    "2026-07-26T02:00:00Z",
                    "2026-07-26T02:00:00Z",
                    "中间摘要",
                ),
                (
                    "news-required-old",
                    "邮件旧闻",
                    "2026-07-20T01:00:00Z",
                    "2026-07-20T01:00:00Z",
                    "2026-07-20T01:00:00Z",
                    "邮件链接仍需可打开",
                ),
            ],
        )

    rows, total = parse_news_rows(
        repo_root=tmp_path,
        article_ids=set(),
        limit=2,
        required_news_ids={"news-required-old"},
    )

    assert total == 3
    assert len(rows) == 2
    assert {row["id"] for row in rows} == {
        "news-newest",
        "news-required-old",
    }


def test_recent_sent_mail_news_are_automatically_preserved(tmp_path: Path) -> None:
    root = (
        tmp_path
        / "data"
        / "semantic_pipeline_v2"
        / "investment"
        / "loop_engineering"
        / "hourly_value_mail"
    )
    recent = root / "hourly_value_recent"
    recent.mkdir(parents=True)
    recent_snapshot = recent / "snapshot.json"
    recent_payload = {
        "generated_at": "2026-07-26T01:00:00Z",
        "digest": [
            {"portal_type": "news", "article_id": "news-recent"},
            {"portal_type": "article", "article_id": "article-not-news"},
        ],
    }
    recent_payload["snapshot_hash"] = hashlib.sha256(
        json.dumps(
            recent_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    recent_snapshot.write_text(json.dumps(recent_payload), encoding="utf-8")
    (recent / "manifest.json").write_text(
        json.dumps(
            {
                "status": "sent",
                "snapshot_path": str(recent_snapshot),
            }
        ),
        encoding="utf-8",
    )
    stale = root / "hourly_value_stale"
    stale.mkdir()
    stale_snapshot = stale / "snapshot.json"
    stale_payload = {
        "generated_at": "2026-07-24T00:00:00Z",
        "digest": [{"portal_type": "news", "article_id": "news-stale"}],
    }
    stale_payload["snapshot_hash"] = hashlib.sha256(
        json.dumps(
            stale_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    stale_snapshot.write_text(json.dumps(stale_payload), encoding="utf-8")
    (stale / "manifest.json").write_text(
        json.dumps(
            {
                "status": "sent",
                "snapshot_path": str(stale_snapshot),
            }
        ),
        encoding="utf-8",
    )

    ids = discover_recent_sent_mail_news_ids(
        repo_root=tmp_path,
        current_time=datetime(2026, 7, 26, 2, 0, tzinfo=timezone.utc),
    )

    assert ids == ["news-recent"]


def test_pending_mail_news_are_temporarily_preserved_with_strict_boundaries(
    tmp_path: Path,
) -> None:
    root = (
        tmp_path
        / "data"
        / "semantic_pipeline_v2"
        / "investment"
        / "loop_engineering"
        / "hourly_value_mail"
    )

    def add_run(name: str, status: str, generated_at: str, *, valid: bool = True) -> None:
        run_dir = root / name
        run_dir.mkdir(parents=True)
        snapshot_path = run_dir / "snapshot.json"
        payload = {
            "generated_at": generated_at,
            "digest": [{"portal_type": "news", "article_id": f"news-{name}"}],
        }
        payload["snapshot_hash"] = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if not valid:
            payload["snapshot_hash"] = "corrupt"
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
        (run_dir / "manifest.json").write_text(
            json.dumps({"status": status, "snapshot_path": str(snapshot_path)}),
            encoding="utf-8",
        )

    for status in (
        "publish_failed",
        "publishing",
        "ready_to_send",
        "mail_retry_pending",
    ):
        add_run(status, status, "2026-07-26T01:00:00Z")
    for status in ("preview_ready", "content_policy_superseded", "stale"):
        add_run(status, status, "2026-07-26T01:00:00Z")
    add_run("old-pending", "publish_failed", "2026-07-24T00:00:00Z")
    add_run("corrupt", "publish_failed", "2026-07-26T01:00:00Z", valid=False)

    ids = discover_recent_sent_mail_news_ids(
        repo_root=tmp_path,
        current_time=datetime(2026, 7, 26, 2, 0, tzinfo=timezone.utc),
    )

    assert ids == [
        "news-mail_retry_pending",
        "news-publish_failed",
        "news-publishing",
        "news-ready_to_send",
    ]


def test_preserved_news_fill_but_never_expand_bounded_window(
    tmp_path: Path,
) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(
        json.dumps(
            {
                "collections": {
                    "news": [
                        {
                            "id": "news-old-extra",
                            "updatedAt": "2026-07-26T04:00:00Z",
                        },
                        {
                            "id": "news-current",
                            "updatedAt": "2026-07-26T03:00:00Z",
                        },
                    ]
                },
                "newsMeta": {
                    "totalCount": 100,
                    "mirroredCount": 2,
                    "windowLimit": 2,
                },
                "stats": {"news": 100},
            }
        ),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(
            {
                "collections": {
                    "news": [
                        {
                            "id": "news-current",
                            "updatedAt": "2026-07-26T03:00:00Z",
                        },
                        {
                            "id": "news-required-mail",
                            "updatedAt": "2026-07-20T01:00:00Z",
                        },
                    ]
                },
                "newsMeta": {
                    "totalCount": 101,
                    "mirroredCount": 2,
                    "windowLimit": 2,
                },
                "stats": {"news": 101},
            }
        ),
        encoding="utf-8",
    )

    preserved = preserve_existing_collections(
        before_path=before_path,
        after_path=after_path,
        collection_names=["news"],
    )
    result = json.loads(after_path.read_text(encoding="utf-8"))

    assert preserved == {"news": 0}
    assert [item["id"] for item in result["collections"]["news"]] == [
        "news-current",
        "news-required-mail",
    ]
    assert result["newsMeta"]["mirroredCount"] == 2
    assert result["newsMeta"]["windowLimit"] == 2
