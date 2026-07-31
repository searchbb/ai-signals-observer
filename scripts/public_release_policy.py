"""Fail-closed publication policy for the static public portal."""

from __future__ import annotations

import hashlib
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


def record_evidence_items(record: dict) -> list[dict]:
    evidence: list[dict] = []
    direct = record.get("evidence")
    if isinstance(direct, dict):
        evidence.append(direct)
    evidence.extend(
        item
        for item in list(record.get("evidence_cards") or [])
        if isinstance(item, dict)
    )
    return evidence


def direct_reader_payload(record: dict) -> dict:
    """Keep direct reader fields while leaving nested records independent."""

    payload: dict = {}
    for key, value in record.items():
        if key in {
            "evidence",
            "evidence_cards",
            "html",
            "publication_binding",
        }:
            continue
        if isinstance(value, dict):
            continue
        if isinstance(value, list):
            scalar_items = [
                item
                for item in value
                if not isinstance(item, (dict, list))
            ]
            if scalar_items:
                payload[key] = scalar_items
            continue
        payload[key] = value
    return payload


def claim_text(record: dict) -> str:
    return str(
        record.get("statement")
        or record.get("event")
        or record.get("claim")
        or ""
    )


def record_claim_id(record: dict) -> str:
    return str(
        record.get("fact_id")
        or record.get("claim_id")
        or record.get("update_id")
        or ""
    )


def semantic_release_record(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("publication_binding"), dict)
    )


def marker_codes_covered_by_quote(
    marker_codes: set[str],
    quote: object,
) -> bool:
    lowered_quote = str(quote or "").casefold()
    for code in marker_codes:
        index = int(code.rsplit("_", 1)[-1])
        if STRICT_VISIBLE_MARKERS[index - 1].casefold() not in lowered_quote:
            return False
    return True


def verified_publication_binding(
    record: dict,
) -> tuple[bool, set[str]]:
    """Trust only an upstream claim/evidence certificate bound by IDs and hash."""

    binding = dict(record.get("publication_binding") or {})
    claim = claim_text(record)
    claim_codes = set(strict_visible_marker_violations(claim))
    if (
        binding.get("binding_type") != "canonical_claim_evidence_v1"
        or not str(binding.get("binding_id") or "")
        or str(binding.get("claim_id") or "") != record_claim_id(record)
        or str(binding.get("claim_sha256") or "")
        != hashlib.sha256(claim.encode("utf-8")).hexdigest()
        or binding.get("support_status") != "claim_supported"
        or binding.get("review_status") != "fact_confirmed"
        or binding.get("validator") != "research_updates.review_status"
    ):
        return False, set()
    bound_evidence_id = str(binding.get("evidence_id") or "")
    evidence_items = record_evidence_items(record)
    for evidence in evidence_items:
        evidence_id = str(evidence.get("evidence_id") or "")
        if (
            evidence_id != bound_evidence_id
            or not public_http_url(evidence.get("source_url"))
            or str(evidence.get("verification_status") or "")
            not in VERIFIED_PUBLIC_EVIDENCE_STATUSES
            or not marker_codes_covered_by_quote(
                claim_codes,
                evidence.get("source_quote"),
            )
        ):
            continue
        quote_codes = set(
            strict_visible_marker_violations(
                evidence.get("source_quote") or ""
            )
        )
        return True, claim_codes | quote_codes
    return False, set()


def evidence_aware_marker_violations(
    value: object,
    *,
    inherited_authorized_codes: set[str] | None = None,
) -> tuple[set[str], set[str]]:
    """Recursively validate explicit semantic records without path allowlists."""

    inherited = set(inherited_authorized_codes or ())
    violations: set[str] = set()
    authorized_codes: set[str] = set(inherited)
    if isinstance(value, dict):
        direct_payload = direct_reader_payload(value)
        direct_codes = set(strict_visible_marker_violations(direct_payload))
        evidence_items = record_evidence_items(value)
        bound, bound_codes = verified_publication_binding(value)
        if semantic_release_record(value):
            if bound:
                authorized_codes.update(bound_codes)
                violations.update(direct_codes - bound_codes)
            else:
                violations.update(direct_codes)
        else:
            violations.update(direct_codes - inherited)
            for evidence in evidence_items:
                violations.update(
                    strict_visible_marker_violations(
                        evidence.get("source_quote") or ""
                    )
                )

        for key, child in value.items():
            if key in {
                "evidence",
                "evidence_cards",
                "html",
                "publication_binding",
            }:
                continue
            nested_items: list[object] = []
            if isinstance(child, dict):
                nested_items = [child]
            elif isinstance(child, list):
                nested_items = [
                    item
                    for item in child
                    if isinstance(item, (dict, list))
                ]
            for nested in nested_items:
                child_inherited = (
                    set()
                    if semantic_release_record(nested)
                    else set(authorized_codes)
                )
                child_violations, child_authorized = (
                    evidence_aware_marker_violations(
                        nested,
                        inherited_authorized_codes=child_inherited,
                    )
                )
                violations.update(child_violations)
                authorized_codes.update(child_authorized)

        html_codes = set(
            strict_visible_marker_violations(value.get("html") or "")
        )
        violations.update(html_codes - authorized_codes)
        return violations, authorized_codes
    if isinstance(value, list):
        for child in value:
            child_violations, child_authorized = (
                evidence_aware_marker_violations(
                    child,
                    inherited_authorized_codes=inherited,
                )
            )
            violations.update(child_violations)
            authorized_codes.update(child_authorized)
        return violations, authorized_codes
    scalar_codes = set(strict_visible_marker_violations(value))
    violations.update(scalar_codes - inherited)
    authorized_codes.update(scalar_codes & inherited)
    return violations, authorized_codes


def public_http_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def object_marker_violations(item: dict) -> list[str]:
    """Allow sensitive public facts only with an upstream binding certificate."""

    violations, _ = evidence_aware_marker_violations(
        item,
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
