#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote


SITE_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_TYPES = {
    "topics": "topic",
    "issues": "issue",
    "cards": "card",
    "research": "research",
    "articles": "article",
    "news": "news",
    "objects": "object",
    "signals": "signal",
}
LOCAL_PATH_RE = re.compile(r"/Users/|\\Users\\|[A-Za-z]:\\")
URL_SAFE_FILENAME_CHARS = "-_.!~*'()"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shard_path(detail_root: Path, detail_type: str, item_id: str) -> Path:
    filename = f"{quote(item_id, safe=URL_SAFE_FILENAME_CHARS)}.json"
    return detail_root / detail_type / filename


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-data", default=str(SITE_ROOT / "data/site-data.json"))
    parser.add_argument("--detail-root", default=str(SITE_ROOT / "data/details"))
    parser.add_argument("--manifest", default=str(SITE_ROOT / "data/details-manifest.json"))
    parser.add_argument("--mail-report", default="")
    args = parser.parse_args()

    site_data_path = Path(args.site_data).resolve()
    detail_root = Path(args.detail_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    site_data = json.loads(site_data_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {
        (str(row["type"]), str(row["id"])): row
        for row in list(manifest.get("entries") or [])
    }

    expected_count = 0
    maximum_shard_bytes = 0
    for collection_name, detail_type in COLLECTION_TYPES.items():
        rows = list(dict(site_data.get("collections") or {}).get(collection_name) or [])
        assert int(dict(manifest.get("counts") or {}).get(detail_type) or -1) == len(rows)
        for item in rows:
            expected_count += 1
            item_id = str(item["id"])
            path = shard_path(detail_root, detail_type, item_id)
            assert path.is_file(), path
            raw = path.read_text(encoding="utf-8")
            assert not LOCAL_PATH_RE.search(raw), path
            payload = json.loads(raw)
            assert payload["type"] == detail_type
            assert payload["id"] == item_id
            assert payload["item"] == item
            entry = entries[(detail_type, item_id)]
            assert int(entry["bytes"]) == path.stat().st_size
            assert entry["sha256"] == sha256_file(path)
            maximum_shard_bytes = max(maximum_shard_bytes, path.stat().st_size)

    assert int(manifest.get("count") or -1) == expected_count
    assert len(entries) == expected_count

    mail_result = {"checked": False}
    if args.mail_report:
        report = json.loads(Path(args.mail_report).resolve().read_text(encoding="utf-8"))
        article_ids = [
            str(item["article_id"]) for item in list(report.get("digested_articles_24h") or [])
        ]
        news_ids = [
            str(item["article_id"])
            for item in list(report.get("selected_for_digest") or [])
            + list(report.get("watch_only") or [])
        ]
        checked = []
        for detail_type, ids in (("article", article_ids), ("news", news_ids)):
            for item_id in ids:
                path = shard_path(detail_root, detail_type, item_id)
                payload = json.loads(path.read_text(encoding="utf-8"))
                item = dict(payload["item"])
                summary = str(item.get("summary") or "").strip()
                html = str(item.get("html") or "").strip()
                assert summary or html, f"empty mail detail shard: {detail_type}/{item_id}"
                checked.append(
                    {
                        "type": detail_type,
                        "id": item_id,
                        "bytes": path.stat().st_size,
                        "summary_length": len(summary),
                        "html_length": len(html),
                    }
                )
        mail_result = {
            "checked": True,
            "article_count": len(article_ids),
            "news_count": len(news_ids),
            "all_nonempty": True,
            "maximum_mail_shard_bytes": max(row["bytes"] for row in checked),
        }

    result = {
        "status": "passed",
        "site_data_bytes": site_data_path.stat().st_size,
        "detail_count": expected_count,
        "maximum_shard_bytes": maximum_shard_bytes,
        "manifest_sha256": sha256_file(manifest_path),
        "mail_links": mail_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
