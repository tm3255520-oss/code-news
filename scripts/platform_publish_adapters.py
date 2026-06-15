from __future__ import annotations

from typing import Any


def should_skip_platform(state: dict[str, Any], platform: str) -> bool:
    status = str(state["platforms"][platform]["status"])
    return status in {"published_verified", "duplicate_blocked", "awaiting_verification"}


def map_toutiao_result(
    record: dict[str, Any] | None,
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    if verification and verification.get("hasTitleMatch"):
        return {
            "status": "published_verified",
            "publishedAt": (record or {}).get("submittedAt") or verification.get("checkedAt"),
            "url": (record or {}).get("pageUrl"),
            "verificationSource": "article_list_check",
            "error": None,
        }
    if verification and not verification.get("hasTitleMatch"):
        return {
            "status": "publish_failed",
            "publishedAt": None,
            "url": (record or {}).get("pageUrl") or verification.get("pageUrl"),
            "verificationSource": "article_list_check",
            "error": "toutiao publish verification failed",
        }
    if record and record.get("status") == "verification_failed":
        return {
            "status": "publish_failed",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": "article_list_check",
            "error": "toutiao verification failed",
        }
    return {
        "status": "awaiting_verification",
        "publishedAt": None,
        "url": (record or {}).get("pageUrl"),
        "verificationSource": "local_publish_record",
        "error": None,
    }


def map_zhihu_result(record: dict[str, Any] | None) -> dict[str, Any]:
    if record and record.get("publishedAt"):
        return {
            "status": "published_verified",
            "publishedAt": record.get("publishedAt"),
            "url": record.get("url"),
            "verificationSource": "local_publish_record",
            "error": None,
        }
    return {
        "status": "publish_failed",
        "publishedAt": None,
        "url": None,
        "verificationSource": "local_publish_record",
        "error": "zhihu publish record missing",
    }


def map_wechat_result(record: dict[str, Any] | None) -> dict[str, Any]:
    status = str((record or {}).get("status") or "")
    if status == "published" or (record and record.get("publishedAt")):
        return {
            "status": "published_verified",
            "publishedAt": record.get("publishedAt"),
            "url": record.get("pageUrl"),
            "verificationSource": str(record.get("source") or "local_publish_record"),
            "error": None,
        }
    if status == "awaiting_wechat_verification":
        return {
            "status": "awaiting_verification",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": "local_publish_record",
            "error": None,
        }
    if status in {"remote_publish_pending", "remote_publish_pending_preflight"}:
        return {
            "status": "awaiting_verification",
            "publishedAt": None,
            "url": record.get("pageUrl"),
            "verificationSource": str(record.get("source") or "local_publish_record"),
            "error": None,
        }
    return {
        "status": "publish_failed",
        "publishedAt": None,
        "url": (record or {}).get("pageUrl"),
        "verificationSource": "local_publish_record",
        "error": "wechat publish result unresolved",
    }
