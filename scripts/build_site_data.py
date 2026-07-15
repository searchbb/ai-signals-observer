from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable

import markdown


TOPIC_SECTION_RE = re.compile(r"^## TOPIC: (?P<title>.+)$", re.MULTILINE)
TOPIC_ID_RE = re.compile(r"^- topic_id:\s*(?P<value>.+)$", re.MULTILINE)
FIELD_RE = re.compile(r"^- (?P<key>[a-zA-Z0-9_]+):\s*(?P<value>.+)$", re.MULTILINE)
HEADER_RE = re.compile(r"^#\s+(?P<title>.+)$", re.MULTILINE)
ISSUE_HEADER_RE = re.compile(r"^# Issue Card:\s*(?P<title>.+)$", re.MULTILINE)
MERGED_HEADER_RE = re.compile(r"^# Issue Card:\s*(?P<title>.+)$", re.MULTILINE)
TOPIC_SHADOW_RE = re.compile(r"^## TOPIC_ID:\s*(?P<topic_id>.+)$", re.MULTILINE)
SHADOW_ISSUE_RE = re.compile(
    r"^- issue_card_id:\s*(?P<issue_id>[^|]+)\|\s*articles:\s*(?P<articles>\d+)\s*\|\s*question:\s*(?P<question>.+)$",
    re.MULTILINE,
)


@dataclass
class Topic:
    id: str
    title: str
    status: str
    issue_count_declared: int | None
    article_count: int | None
    last_updated: str | None
    issue_ids: list[str]
    active_issue_ids: list[str]
    related_card_ids: list[str]
    related_research_ids: list[str]


def isoformat_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def render_markdown(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["extra", "fenced_code", "tables", "sane_lists", "toc"],
        output_format="html5",
    )


def section_body(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$" r"(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


def parse_int(value: str | None) -> int | None:
    if value is None or value == "N/A":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_topic_registry(path: Path) -> list[Topic]:
    text = path.read_text(encoding="utf-8")
    matches = list(TOPIC_SECTION_RE.finditer(text))
    topics: list[Topic] = []

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        title = match.group("title").strip()
        fields = {m.group("key"): m.group("value").strip() for m in FIELD_RE.finditer(block)}
        issue_ids = re.findall(r"issue_card_id:\s*([a-zA-Z0-9_]+)", block)
        topics.append(
            Topic(
                id=fields.get("topic_id", title),
                title=title,
                status=fields.get("status", "unknown"),
                issue_count_declared=parse_int(fields.get("issue_count")),
                article_count=parse_int(fields.get("article_count")),
                last_updated=fields.get("last_updated"),
                issue_ids=issue_ids,
                active_issue_ids=[],
                related_card_ids=[],
                related_research_ids=[],
            )
        )
    return topics


def parse_shadow(path: Path) -> dict[str, list[dict[str, str | int]]]:
    text = path.read_text(encoding="utf-8")
    matches = list(TOPIC_SHADOW_RE.finditer(text))
    out: dict[str, list[dict[str, str | int]]] = {}

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        rows = []
        for row in SHADOW_ISSUE_RE.finditer(block):
            rows.append(
                {
                    "issue_id": row.group("issue_id").strip(),
                    "articles": int(row.group("articles")),
                    "question": row.group("question").strip(),
                }
            )
        out[match.group("topic_id").strip()] = rows
    return out


def parse_issue_markdown(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    title_match = ISSUE_HEADER_RE.search(raw)
    title = title_match.group("title").strip() if title_match else path.stem
    fields = {m.group("key"): m.group("value").strip() for m in FIELD_RE.finditer(raw)}
    question = section_body(raw, "Canonical Question").split("\n\n")[0].strip()
    html = render_markdown(raw)
    return {
        "id": fields.get("issue_card_id", path.stem),
        "type": "issue",
        "title": title,
        "topicId": fields.get("topic_id", path.parent.name),
        "status": fields.get("status", "unknown"),
        "sourceArticleCount": parse_int(fields.get("source_article_count")),
        "updatedAt": fields.get("updated_at"),
        "createdAt": fields.get("created_at"),
        "canonicalQuestion": question,
        "path": str(path),
        "mtime": isoformat_from_mtime(path),
        "html": html,
        "text": plain_text(html),
    }


def parse_merged_markdown(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    title_match = MERGED_HEADER_RE.search(raw)
    title = title_match.group("title").strip() if title_match else path.stem
    fields = {m.group("key"): m.group("value").strip() for m in FIELD_RE.finditer(raw)}
    question = section_body(raw, "Canonical Question").split("\n\n")[0].strip()
    html = render_markdown(raw)
    return {
        "id": fields.get("issue_card_id", path.stem),
        "type": "card",
        "title": title,
        "topicId": fields.get("topic_id"),
        "status": fields.get("status", "active"),
        "sourceArticleCount": parse_int(fields.get("source_article_count")),
        "updatedAt": fields.get("updated_at"),
        "createdAt": fields.get("created_at"),
        "canonicalQuestion": question,
        "path": str(path),
        "mtime": isoformat_from_mtime(path),
        "html": html,
        "text": plain_text(html),
    }


def parse_research_report(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    header = HEADER_RE.search(raw)
    title = header.group("title").strip() if header else path.parent.name
    html = render_markdown(raw)
    return {
        "id": path.parent.name,
        "type": "research",
        "title": title,
        "topicId": None,
        "status": "published",
        "updatedAt": None,
        "createdAt": None,
        "canonicalQuestion": "",
        "path": str(path),
        "mtime": isoformat_from_mtime(path),
        "html": html,
        "text": plain_text(html),
    }


def research_candidates(base: Path) -> list[Path]:
    patterns = {
        "final_report.md",
        "report.md",
        "report_final.md",
        "report_v2_final.md",
        "agentarts_seminar_report_final.md",
    }
    return sorted(
        [path for path in base.rglob("*.md") if path.name in patterns],
        key=lambda item: item.as_posix(),
    )


def relate_assets(
    topics: list[Topic],
    issues: list[dict],
    cards: list[dict],
    research: list[dict],
    shadow: dict[str, list[dict[str, str | int]]],
) -> None:
    issue_map = {issue["id"]: issue for issue in issues}
    for topic in topics:
        if topic.id in shadow:
            topic.active_issue_ids = [row["issue_id"] for row in shadow[topic.id]]
        else:
            topic.active_issue_ids = [issue_id for issue_id in topic.issue_ids if issue_id in issue_map]

        terms = [topic.id, topic.title] + topic.issue_ids + topic.active_issue_ids
        normalized_terms = [term for term in terms if term]

        for card in cards:
            haystack = " ".join([card["id"], card["title"], card["text"][:4000]])
            if any(term in haystack for term in normalized_terms):
                topic.related_card_ids.append(card["id"])

        for item in research:
            haystack = " ".join([item["id"], item["title"], item["text"][:4000]])
            if any(term in haystack for term in normalized_terms):
                topic.related_research_ids.append(item["id"])

        topic.related_card_ids = sorted(set(topic.related_card_ids))
        topic.related_research_ids = sorted(set(topic.related_research_ids))


def sort_timeline(items: Iterable[dict]) -> list[dict]:
    return sorted(
        (
            {
                "id": item["id"],
                "type": item["type"],
                "title": item["title"],
                "topicId": item.get("topicId"),
                "updatedAt": item.get("updatedAt") or item["mtime"],
                "path": item["path"],
            }
            for item in items
        ),
        key=lambda item: item["updatedAt"] or "",
        reverse=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.out).resolve()
    index_root = repo_root / "data/semantic_pipeline_v2/index"
    research_root = repo_root / "data/semantic_pipeline_v2/research_packs"

    topics = parse_topic_registry(index_root / "topic_registry.md")
    shadow = parse_shadow(index_root / "registry_shadow_active_cards.md")

    issue_files = sorted(
        path
        for path in (index_root / "issue_cards").rglob("*.md")
        if ".bak." not in path.name
    )
    issues = [parse_issue_markdown(path) for path in issue_files]

    merged_files = sorted((index_root / "merged_cards").glob("*.md"))
    cards = [parse_merged_markdown(path) for path in merged_files]

    research_files = research_candidates(research_root)
    research = [parse_research_report(path) for path in research_files]

    relate_assets(topics, issues, cards, research, shadow)

    topic_rows = [
        {
            "id": topic.id,
            "title": topic.title,
            "status": topic.status,
            "issueCountDeclared": topic.issue_count_declared,
            "articleCount": topic.article_count,
            "lastUpdated": topic.last_updated,
            "issueIds": topic.issue_ids,
            "activeIssueIds": topic.active_issue_ids,
            "relatedCardIds": topic.related_card_ids,
            "relatedResearchIds": topic.related_research_ids,
        }
        for topic in topics
    ]

    active_issues = sum(1 for issue in issues if issue["status"] == "active")
    provisional_issues = sum(1 for issue in issues if issue["status"] == "provisional")
    latest_mtime = max(
        [item["mtime"] for item in issues + cards + research],
        default=datetime.now(tz=timezone.utc).isoformat(),
    )

    payload = {
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
        "repoRoot": str(repo_root),
        "stats": {
            "topics": len(topic_rows),
            "issues": len(issues),
            "cards": len(cards),
            "research": len(research),
            "activeIssues": active_issues,
            "provisionalIssues": provisional_issues,
            "latestUpdate": latest_mtime,
        },
        "topics": topic_rows,
        "issues": issues,
        "cards": cards,
        "research": research,
        "timeline": sort_timeline([*issues, *cards, *research])[:120],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
