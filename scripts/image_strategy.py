from __future__ import annotations

from typing import Any


DEFAULT_SLOT_POSITIONS = (2, 4, 6)


def ordered_candidates(preferred: list[str], available: list[str]) -> list[str]:
    output: list[str] = []
    for item in [*preferred, *available]:
        if item and item not in output:
            output.append(item)
    return output


def recent_values(history: list[dict[str, Any]], key: str, limit: int) -> list[str]:
    values: list[str] = []
    for entry in history[-limit:]:
        value = entry.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def recent_body_values(history: list[dict[str, Any]], limit: int) -> list[str]:
    values: list[str] = []
    for entry in history[-limit:]:
        for item in entry.get("bodyFamilies", []) or []:
            if isinstance(item, str) and item and item not in values:
                values.append(item)
    return values


def pick_with_avoidance(
    candidates: list[str],
    blocked: list[str],
    already_selected: list[str] | None = None,
) -> str:
    selected = already_selected or []
    for candidate in candidates:
        if candidate not in blocked and candidate not in selected:
            return candidate
    for candidate in candidates:
        if candidate not in selected:
            return candidate
    return candidates[0]


def build_slot_positions(payload: dict[str, Any]) -> list[int]:
    slots: list[int] = []
    for item in payload.get("body_images", []) or []:
        position = item.get("insert_after_block") or item.get("insertAfterBlock")
        if isinstance(position, int) and position > 0:
            slots.append(position)
    if slots:
        return slots[:3]

    block_count = len(payload.get("article_blocks", []) or [])
    if block_count <= 3:
        return [1, 2, max(3, block_count)]
    if block_count <= 6:
        return [2, 4, block_count]
    return list(DEFAULT_SLOT_POSITIONS)


def focus_text_for_position(payload: dict[str, Any], position: int) -> str:
    blocks = payload.get("article_blocks", []) or []
    if not blocks:
        return str(payload.get("summary") or payload.get("title") or "").strip()

    index = max(0, min(len(blocks) - 1, position - 1))
    return str(blocks[index]).strip()


def build_image_plan(
    payload: dict[str, Any],
    domain: str,
    strategy: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    preferences = strategy.get("domainPreferences", {}).get(domain, {})
    cover_families = ordered_candidates(
        list(preferences.get("coverFamilies", [])),
        list(strategy.get("coverFamilies", {}).keys()),
    )
    body_families = ordered_candidates(
        list(preferences.get("bodyFamilies", [])),
        list(strategy.get("bodyFamilies", {}).keys()),
    )
    palettes = ordered_candidates(
        list(preferences.get("palettes", [])),
        list(strategy.get("palettes", {}).keys()),
    )

    avoid_window = int(strategy.get("avoidRepeatWindow", 2) or 2)
    blocked_cover_families = recent_values(history, "coverFamily", avoid_window)
    blocked_cover_palettes = recent_values(history, "coverPalette", avoid_window)
    blocked_body_families = recent_body_values(history, avoid_window)

    cover_family = pick_with_avoidance(cover_families, blocked_cover_families)
    cover_palette = pick_with_avoidance(palettes, blocked_cover_palettes)
    cover_renderer = strategy["coverFamilies"][cover_family]["renderer"]

    slot_positions = build_slot_positions(payload)
    chosen_body_families: list[str] = []
    body_slots: list[dict[str, Any]] = []
    for index, position in enumerate(slot_positions[:3], start=1):
        family = pick_with_avoidance(
            body_families,
            blocked_body_families,
            already_selected=chosen_body_families,
        )
        chosen_body_families.append(family)
        body_slots.append(
            {
                "index": index,
                "family": family,
                "renderer": strategy["bodyFamilies"][family]["renderer"],
                "palette": cover_palette,
                "insertAfterBlock": position,
                "focusText": focus_text_for_position(payload, position),
                "promptStyle": strategy["bodyFamilies"][family].get("promptStyle", ""),
            }
        )

    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or ""),
        "domain": domain,
        "coverFamily": cover_family,
        "coverRenderer": cover_renderer,
        "coverPalette": cover_palette,
        "coverPromptStyle": strategy["coverFamilies"][cover_family].get("promptStyle", ""),
        "bodySlots": body_slots,
    }
