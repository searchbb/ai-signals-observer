"""Fail-closed publication policy for the static public portal."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Iterable
from urllib.parse import urlparse


DENIED_RESEARCH_SOURCE_PREFIXES = ("research/department_strategy/",)
STRICT_VISIBLE_MARKERS = (
    "会议纪要",
    "会议记录",
    "内部会议",
    "内部讨论",
    "内部材料",
    "内部资料",
    "内部研究",
    "未公开资料",
    "未公开信息",
    "用户上传",
    "用户提供的资料",
    "你提供的资料",
    "您提供的资料",
    "上传材料",
    "上传资料",
    "据内部",
    "我司内部",
    "PRIVATE_ROUTING_ONLY_DO_NOT_PUBLISH",
    "meeting minutes",
    "internal meeting",
    "user-uploaded material",
    "confidential material",
)
CORPORATE_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:huawei|h-partners)\.com", re.IGNORECASE
)
VERIFIED_PUBLIC_EVIDENCE_STATUSES = {
    "quote_verified",
    "quote_verified_claim_candidate",
}


def strict_visible_marker_violations(value: object) -> list[str]:
    lowered = json.dumps(value, ensure_ascii=False).lower()
    return [
        f"forbidden_provenance_term_{index}"
        for index, marker in enumerate(STRICT_VISIBLE_MARKERS, start=1)
        if marker.lower() in lowered
    ]


def verified_public_evidence_for_text(
    target: object,
    evidence: object,
) -> bool:
    """Require a verified public quote that covers every matched marker."""

    evidence_item = dict(evidence or {})
    if (
        not public_http_url(evidence_item.get("source_url"))
        or str(evidence_item.get("verification_status") or "")
        not in VERIFIED_PUBLIC_EVIDENCE_STATUSES
    ):
        return False
    target_codes = strict_visible_marker_violations(target)
    if not target_codes:
        return True
    quote = str(evidence_item.get("source_quote") or "").casefold()
    for code in target_codes:
        index = int(code.rsplit("_", 1)[-1])
        if STRICT_VISIBLE_MARKERS[index - 1].casefold() not in quote:
            return False
    return True


def verified_public_evidence_card(
    target: object,
    evidence_cards: object,
) -> bool:
    return any(
        verified_public_evidence_for_text(target, evidence)
        for evidence in list(evidence_cards or [])
        if isinstance(evidence, dict)
    )


def public_http_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def object_marker_violations(item: dict) -> list[str]:
    """Allow reported internal events only when their public evidence is verified."""

    violations = strict_visible_marker_violations(
        {
            key: value
            for key, value in item.items()
            if key not in {
                "updates",
                "facts",
                "html",
                "longTermSections",
            }
        }
    )
    evidence_authorized_codes: set[str] = set()
    verified_fact_ids: set[str] = set()
    for update in list(item.get("updates") or []):
        update_violations = strict_visible_marker_violations(update)
        if not update_violations:
            continue
        evidence = dict(update.get("evidence") or {})
        if verified_public_evidence_for_text(update, evidence):
            evidence_authorized_codes.update(update_violations)
            fact_id = str(update.get("fact_id") or "")
            if fact_id:
                verified_fact_ids.add(fact_id)
            continue
        violations.extend(update_violations)
    for fact in list(item.get("facts") or []):
        fact_violations = strict_visible_marker_violations(fact)
        if not fact_violations:
            continue
        if (
            str(fact.get("fact_id") or "") in verified_fact_ids
            and public_http_url(fact.get("source_url"))
            and str(fact.get("status") or "") in {"confirmed", "fact_confirmed"}
        ):
            evidence_authorized_codes.update(fact_violations)
            continue
        violations.extend(fact_violations)
    for section in list(item.get("longTermSections") or []):
        if not isinstance(section, dict):
            violations.extend(strict_visible_marker_violations(section))
            continue
        section_metadata = {
            key: value
            for key, value in section.items()
            if key not in {"facts", "html", "evidence_cards"}
        }
        section_violations = strict_visible_marker_violations(section_metadata)
        if section_violations:
            if verified_public_evidence_card(
                section_metadata,
                section.get("evidence_cards"),
            ):
                evidence_authorized_codes.update(section_violations)
            else:
                violations.extend(section_violations)
        for fact in list(section.get("facts") or []):
            if not isinstance(fact, dict):
                violations.extend(strict_visible_marker_violations(fact))
                continue
            fact_violations = strict_visible_marker_violations(fact)
            if not fact_violations:
                continue
            if verified_public_evidence_card(
                fact,
                fact.get("evidence_cards"),
            ):
                evidence_authorized_codes.update(fact_violations)
                continue
            violations.extend(fact_violations)
        section_html_violations = strict_visible_marker_violations(
            section.get("html") or ""
        )
        violations.extend(
            code
            for code in section_html_violations
            if code not in evidence_authorized_codes
        )
    html_violations = strict_visible_marker_violations(item.get("html") or "")
    violations.extend(
        code
        for code in html_violations
        if code not in evidence_authorized_codes
    )
    return sorted(set(violations))


def publication_violations(collection: str, item: dict) -> list[str]:
    """Return reason codes only, so audits never echo private copy."""
    violations: list[str] = []
    source_path = str(item.get("path") or "").replace("\\", "/")
    if collection == "research" and source_path.startswith(DENIED_RESEARCH_SOURCE_PREFIXES):
        violations.append("private_research_source_class")
    if collection == "articles" and not str(item.get("url") or "").startswith(("http://", "https://")):
        violations.append("article_missing_public_source_url")
    serialized = json.dumps(item, ensure_ascii=False)
    if collection == "objects":
        violations.extend(object_marker_violations(item))
    elif collection in {"issues", "cards", "research", "articles", "signals"}:
        violations.extend(strict_visible_marker_violations(item))
    if CORPORATE_EMAIL_RE.search(serialized):
        violations.append("corporate_email_address")
    return sorted(set(violations))


def partition_public_items(collection: str, items: Iterable[dict]) -> tuple[list[dict], dict]:
    accepted: list[dict] = []
    reasons: Counter[str] = Counter()
    excluded = 0
    for item in items:
        violations = publication_violations(collection, item)
        if violations:
            excluded += 1
            reasons.update(violations)
        else:
            accepted.append(item)
    return accepted, {
        "excluded": excluded,
        "reasonCounts": dict(sorted(reasons.items())),
    }
