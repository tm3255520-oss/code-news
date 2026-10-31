#!/usr/bin/env python3
"""Check lightweight quality issues in an Obsidian-style Markdown vault."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import re
import stat
import sys
import unicodedata

try:
    from .check_obsidian_links import count_block_math_delimiters, text_without_code
    from .safe_io import InputRootError, validate_input_root
except ImportError:
    from check_obsidian_links import count_block_math_delimiters, text_without_code
    from safe_io import InputRootError, validate_input_root


TEMPLATE_RE = re.compile(r"(相关知识链接|TODO|FIXME|TBD|待补|待完善)")
SOLVENOTES_STUDY_RE = re.compile(
    r"(待补充|占位|空话|套话|泛泛|交作业式|神谕|需要注意的是|"
    r"P\(UO\)|L\(UO\)|软件工程：风险管理复习与 RMMM|"
    r"这个公式把项目状态转成可量化的控制指标|若等待图成环，则可能发生死锁|"
    r"关键不是背结论|信息如何进入价格|收益、方差、估值或技术指标)"
)
REPORT_NOTE_NAME_RE = re.compile(
    r"(?:"
    r"^99_.*(?:审查|复查|审计|巡检|报告)$|"
    r"(?:质量|内容覆盖|来源覆盖|一致性|严格).*(?:审查|复查|审计|巡检|报告)$|"
    r"(?:审计|巡检)(?:报告|记录|台账)?$|"
    r"(?:审查|复查)(?:报告|记录|台账)$|"
    r"(?:^|[_ -])(?:audit|coverage_audit|quality_report|review_report|validation_report)(?:$|[_ -])"
    r")",
    re.IGNORECASE,
)
FORMAL_COVERAGE_AUDIT_NAME = "99_内容覆盖审查.md"
FORMAL_COVERAGE_NOTE_TYPE_RE = re.compile(
    r'''note_type\s*:\s*(?:coverage_audit|"coverage_audit"|'coverage_audit')\s*'''
)
SOURCE_MANIFEST_NAME = "source_manifest.md"
SOURCE_MANIFEST_NOTE_TYPE_RE = re.compile(
    r'''note_type\s*:\s*(?:source_manifest|"source_manifest"|'source_manifest')\s*'''
)
NOTE_TYPE_VALUE_RE = re.compile(
    r'''^note_type\s*:\s*(?:"(?P<double>[a-z_]+)"|'(?P<single>[a-z_]+)'|(?P<bare>[a-z_]+))\s*$'''
)
SOLVENOTES_REPORT_NOTE_TYPES = frozenset(
    {
        "coverage_audit",
        "global_coverage_audit",
        "vault_audit",
        "audit_record",
        "source_manifest_history",
    }
)
BRIDGE_NOTE_RE = re.compile(r"本页保留旧路径，正文请读 \[\[[^\]]+\]\]。")
WIKI_LINK_RE = re.compile(r"\[\[[^\]]+\]\]")
DEFAULT_EXCLUDED_DIRS = frozenset({".git", ".obsidian", ".pytest_cache", ".ruff_cache", "__pycache__", "scripts", "skills", "build", "output"})
DEFAULT_EXCLUDED_FILES = frozenset({"AGENT.md"})


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def stem_collision_key(value: str) -> str:
    """Model canonically normalizing, case-insensitive vault filesystems."""

    return unicodedata.normalize("NFC", value).casefold()


@dataclass(frozen=True)
class VaultIssue:
    path: Path
    kind: str
    message: str


def normalized_skip_dirs(
    root: Path,
    skip_dirs: list[Path] | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Validate exact root-relative directory exclusions and return their parts."""

    normalized: set[tuple[str, ...]] = set()
    for raw_skip_dir in skip_dirs or []:
        relative = Path(raw_skip_dir)
        windows_relative = PureWindowsPath(str(raw_skip_dir))
        if relative.is_absolute() or windows_relative.drive or windows_relative.anchor:
            raise ValueError(f"--skip-dir must be root-relative: {raw_skip_dir}")
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError(f"--skip-dir must name a directory below root: {raw_skip_dir}")

        parent = root
        for component in relative.parts:
            entries = {entry.name: entry for entry in parent.iterdir()}
            candidate = entries.get(component)
            if candidate is None:
                case_aliases = sorted(
                    name
                    for name in entries
                    if name.casefold() == component.casefold()
                )
                if case_aliases:
                    exact_names = ", ".join(repr(name) for name in case_aliases)
                    raise ValueError(
                        f"--skip-dir uses non-canonical spelling {component!r}; "
                        f"exact directory entry is {exact_names}: {raw_skip_dir}"
                    )
                raise ValueError(
                    f"--skip-dir does not exist: {raw_skip_dir} "
                    f"(missing component: {component})"
                )

            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(
                    f"--skip-dir contains symlink component {component!r}: "
                    f"{raw_skip_dir}"
                )
            if not stat.S_ISDIR(mode):
                raise ValueError(
                    f"--skip-dir is not a directory at component "
                    f"{component!r}: {raw_skip_dir}"
                )
            parent = candidate
        normalized.add(relative.parts)
    return tuple(sorted(normalized))


def markdown_files(
    root: Path,
    skip_dirs: list[Path] | None = None,
) -> list[Path]:
    excluded_subtrees = normalized_skip_dirs(root, skip_dirs)
    files: list[Path] = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if not _is_regular_file_without_symlink_components(root, path):
            continue
        if path.name in DEFAULT_EXCLUDED_FILES:
            continue
        if set(relative.parts) & DEFAULT_EXCLUDED_DIRS:
            continue
        if any(
            relative.parts[: len(excluded)] == excluded
            for excluded in excluded_subtrees
        ):
            continue
        if not _is_within_root(root, path):
            continue
        files.append(path)
    return sorted(files)


def _is_regular_file_without_symlink_components(root: Path, path: Path) -> bool:
    """Accept only a regular file reached without traversing symlink components."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if not relative.parts:
        return False

    current = root
    try:
        for index, component in enumerate(relative.parts):
            current = current / component
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                return False
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(mode):
                return False
        return stat.S_ISREG(mode)
    except OSError:
        return False


def _is_within_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def relative_issue(root: Path, path: Path, kind: str, message: str) -> VaultIssue:
    return VaultIssue(path.relative_to(root), kind, message)


def is_conflict_marker(line: str, has_conflict_edges: bool) -> bool:
    stripped = line.strip()
    return stripped.startswith("<<<<<<<") or stripped.startswith(">>>>>>>") or (has_conflict_edges and stripped == "=======")


def is_bridge_note(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 260:
        return False
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return bool(lines and lines[0].startswith("# ") and "旧入口" in lines[0] and BRIDGE_NOTE_RE.search(stripped))


def has_frontmatter_note_type(text: str, note_type_pattern: re.Pattern[str]) -> bool:
    """Return whether frontmatter has exactly one matching note_type field."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    try:
        closing_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return False
    note_type_lines = [line.strip() for line in lines[1:closing_index] if re.match(r"^note_type\s*:", line)]
    return len(note_type_lines) == 1 and note_type_pattern.fullmatch(note_type_lines[0]) is not None


def frontmatter_note_types(text: str) -> set[str]:
    """Return recognized note_type values from the leading YAML frontmatter."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return set()
    try:
        closing_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return set()
    values: set[str] = set()
    for line in lines[1:closing_index]:
        match = NOTE_TYPE_VALUE_RE.fullmatch(line.strip())
        if match:
            values.add(next(value for value in match.groupdict().values() if value is not None))
    return values


def is_formal_coverage_audit(path: Path, text: str) -> bool:
    """Match a typed coverage audit backed by a typed sibling source manifest."""

    if path.name != FORMAL_COVERAGE_AUDIT_NAME:
        return False
    if not has_frontmatter_note_type(text, FORMAL_COVERAGE_NOTE_TYPE_RE):
        return False

    try:
        manifest_path = next(
            (
                sibling
                for sibling in path.parent.iterdir()
                if sibling.name == SOURCE_MANIFEST_NAME
            ),
            None,
        )
    except OSError:
        return False
    if manifest_path is None:
        return False
    try:
        if not stat.S_ISREG(manifest_path.lstat().st_mode):
            return False
        manifest_text = manifest_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return has_frontmatter_note_type(manifest_text, SOURCE_MANIFEST_NOTE_TYPE_RE)


def load_pattern_file(path: Path) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("regex:"):
            pattern_text = line.removeprefix("regex:").strip()
        elif line.startswith("re:"):
            pattern_text = line.removeprefix("re:").strip()
        elif line.startswith("text:"):
            pattern_text = re.escape(line.removeprefix("text:").strip())
        else:
            pattern_text = re.escape(line)
        try:
            patterns.append(re.compile(pattern_text))
        except re.error as exc:
            raise ValueError(f"{path}:{line_number}: invalid regex: {exc}") from exc
    return patterns


def profile_patterns(profile: str, pattern_files: list[Path] | None = None) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    if profile == "solvenotes":
        patterns.append(SOLVENOTES_STUDY_RE)
    elif profile != "generic":
        raise ValueError(f"unknown quality profile: {profile}")

    for pattern_file in pattern_files or []:
        patterns.extend(load_pattern_file(pattern_file))
    return patterns


def find_vault_issues(
    root: Path,
    allow_duplicate_stems: bool = False,
    strict_study: bool = False,
    forbid_report_notes: bool = False,
    allow_formal_coverage_audits: bool = False,
    profile: str = "generic",
    pattern_files: list[Path] | None = None,
    skip_dirs: list[Path] | None = None,
) -> list[VaultIssue]:
    root = validate_input_root(root)
    files = markdown_files(root, skip_dirs=skip_dirs)
    issues: list[VaultIssue] = []
    stems: dict[str, list[Path]] = {}
    stem_labels: dict[str, str] = {}
    stem_file_identities: dict[str, set[tuple[int, int]]] = {}
    residue_patterns = profile_patterns(profile, pattern_files)

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        masked_text, unbalanced_fence = text_without_code(text, report_unclosed=True)
        stripped = text.strip()
        if not is_bridge_note(text):
            stem_key = stem_collision_key(path.stem)
            identity = path.stat()
            file_identity = (identity.st_dev, identity.st_ino)
            stem_labels.setdefault(stem_key, path.stem)
            identities = stem_file_identities.setdefault(stem_key, set())
            if file_identity not in identities:
                stems.setdefault(stem_key, []).append(path)
                identities.add(file_identity)
        has_conflict_edges = "<<<<<<<" in text and ">>>>>>>" in text
        lines = text.splitlines()
        masked_lines = masked_text.splitlines()
        report_note_type = bool(frontmatter_note_types(text) & SOLVENOTES_REPORT_NOTE_TYPES)

        if (
            (forbid_report_notes or profile == "solvenotes")
            and (REPORT_NOTE_NAME_RE.search(path.stem) or report_note_type)
            and not (
                allow_formal_coverage_audits
                and profile == "generic"
                and is_formal_coverage_audit(path, text)
            )
        ):
            issues.append(relative_issue(root, path, "report_note", "audit/report-style note is present in the vault"))

        if not stripped:
            issues.append(relative_issue(root, path, "empty_file", "Markdown file has no content"))
            continue

        for line_number, (line, masked_line) in enumerate(zip(lines, masked_lines), start=1):
            if is_conflict_marker(line, has_conflict_edges):
                issues.append(relative_issue(root, path, "conflict_marker", f"line {line_number} contains merge conflict marker"))
            if TEMPLATE_RE.search(masked_line):
                issues.append(relative_issue(root, path, "template_residue", f"line {line_number} contains leftover template text"))
            for residue_pattern in residue_patterns:
                if residue_pattern.search(masked_line):
                    issues.append(relative_issue(root, path, "strict_study_residue", f"line {line_number} contains profile or custom study-note residue"))
                    break
            if strict_study and masked_line.strip() == "## 知识链接":
                issues.append(relative_issue(root, path, "link_dump_section", f"line {line_number} contains a tail-style knowledge-link dump heading"))
            if strict_study and masked_line.startswith("关联阅读：") and len(WIKI_LINK_RE.findall(masked_line)) > 4:
                issues.append(relative_issue(root, path, "dense_related_links", f"line {line_number} contains too many related links for one concept"))
            if strict_study and masked_line.startswith("关联阅读：") and WIKI_LINK_RE.search(masked_line):
                previous = ""
                for prior in reversed(lines[: line_number - 1]):
                    if prior.strip():
                        previous = prior.strip()
                        break
                if previous.startswith("#") or previous.startswith("相关笔记") or previous.startswith("关联阅读"):
                    issues.append(relative_issue(root, path, "poor_link_context", f"line {line_number} is not attached to a concrete concept paragraph"))

        if unbalanced_fence:
            issues.append(relative_issue(root, path, "unbalanced_fence", "fenced code block is not closed"))

        if count_block_math_delimiters(masked_text) % 2:
            issues.append(relative_issue(root, path, "unbalanced_math", "odd number of block math delimiters"))

    if not allow_duplicate_stems:
        for stem_key, paths in sorted(stems.items()):
            if len(paths) <= 1:
                continue
            joined = ", ".join(str(path.relative_to(root)) for path in paths)
            issues.append(
                VaultIssue(
                    Path(stem_labels[stem_key]),
                    "duplicate_stem",
                    f"duplicate note stem across files: {joined}",
                )
            )

    return issues


def main() -> int:
    configure_output_encoding()
    parser = argparse.ArgumentParser(description="Check Markdown vault quality issues.")
    parser.add_argument("root", type=Path, help="Vault or notes directory")
    parser.add_argument("--allow-duplicate-stems", action="store_true")
    parser.add_argument("--strict-study", action="store_true", help="flag generic strict study-note link-placement issues")
    parser.add_argument(
        "--profile",
        choices=["generic", "solvenotes"],
        default="generic",
        help="quality profile for project-specific residue patterns; solvenotes also forbids legacy audit/report notes",
    )
    parser.add_argument("--pattern-file", action="append", default=[], type=Path, help="custom residue pattern file; plain lines are literal text, regex:/re: lines are regular expressions")
    parser.add_argument(
        "--skip-dir",
        action="append",
        default=[],
        type=Path,
        metavar="RELATIVE_DIR",
        help="skip one existing directory subtree by exact canonical root-relative spelling; symlink components are rejected; may be repeated",
    )
    parser.add_argument("--forbid-report-notes", action="store_true", help="flag audit/report-style Markdown notes in the checked tree")
    parser.add_argument(
        "--allow-formal-coverage-audits",
        action="store_true",
        help=(
            "with --profile generic and --forbid-report-notes, allow only "
            "99_内容覆盖审查.md with note_type: coverage_audit backed by sibling "
            "source_manifest.md with note_type: source_manifest; the solvenotes "
            "profile always rejects legacy coverage-audit notes"
        ),
    )
    args = parser.parse_args()

    try:
        issues = find_vault_issues(
            args.root,
            allow_duplicate_stems=args.allow_duplicate_stems,
            strict_study=args.strict_study,
            forbid_report_notes=args.forbid_report_notes,
            allow_formal_coverage_audits=args.allow_formal_coverage_audits,
            profile=args.profile,
            pattern_files=args.pattern_file,
            skip_dirs=args.skip_dir,
        )
    except InputRootError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"vault_quality_issues {len(issues)}")
    for issue in issues:
        print(f"{issue.kind.upper()}: {issue.path}: {issue.message}")

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
