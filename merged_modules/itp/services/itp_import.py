from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from django.db import transaction

from itp.models import (
    DependencyType,
    DocumentStatus,
    ImportIssue,
    ImportIssueSeverity,
    ITPClause,
    ITPClauseDependency,
    ITPClauseIntervention,
    ITPDocument,
    ITPStakeholder,
    SourceFormat,
)

from .parsing import append_text, clean_cell, normalise_header
from .readers import read_excel_rows, read_pdf_tables


HEADER_ALIASES = {
    "action": ["ACTION", "CLAUSE", "ITP CLAUSE"],
    "activity": ["QUALITY RELATED ACTIVITY", "ACTIVITY", "INSPECTION ACTIVITY"],
    "reference": ["REFERENCE DOCUMENT", "REFERENCE", "REFERENCES"],
    "characteristics": [
        "CHARACTERISTICS TO BE VERIFIED",
        "CHARACTERISTICS",
        "EXTENT OF INSPECTION",
    ],
    "acceptance": ["ACCEPTANCE CRITERIA", "ACCEPTANCE"],
    "verifying": ["VERIFYING DOCUMENT", "RECORD", "VERIFYING RECORD"],
}


def _find_header_map(row: list[object]) -> dict[str, int]:
    normalised = [normalise_header(value) for value in row]
    mapping: dict[str, int] = {}
    for field, aliases in HEADER_ALIASES.items():
        for idx, header in enumerate(normalised):
            if any(alias in header for alias in aliases):
                mapping[field] = idx
                break
    return mapping


def _looks_like_header(row: list[object]) -> bool:
    mapping = _find_header_map(row)
    return len(mapping) >= 4 and "action" in mapping and "activity" in mapping


def _safe_value(row: list[object], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return clean_cell(row[index])


def _normalise_intervention(raw: str) -> tuple[str, str]:
    text = clean_cell(raw).upper()
    if not text:
        return "", ""
    if text == "-":
        return "-", ""
    match = re.match(r"(?:(\d+(?:\.\d+)?)%\s*)?(RW|W|H|R|A|S|M|AI|TC)(.*)", text)
    if not match:
        return text, ""
    percentage, code, tail = match.groups()
    sampling = f"{percentage}%" if percentage else ""
    if tail.strip():
        sampling = f"{sampling} {tail.strip()}".strip()
    return code, sampling


def _section_from_row(action: str, activity: str) -> tuple[str, str] | None:
    action_text = action.strip()
    if re.fullmatch(r"[A-Z]", action_text.upper()) and activity:
        return action_text.upper(), activity

    combined = action_text or activity.strip()
    match = re.match(r"^([A-Z])\s*[.):-]\s*(.+)$", combined, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper(), match.group(2).strip()
    return None


def _is_clause(action: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)*", action.strip()))


def _extract_rows(document: ITPDocument):
    suffix = Path(document.original_file.name).suffix.lower()
    if suffix == ".pdf":
        return read_pdf_tables(document.original_file)
    return read_excel_rows(document.original_file)


@transaction.atomic
def import_itp_document(document: ITPDocument) -> dict[str, int]:
    document.status = DocumentStatus.EXTRACTING
    document.save(update_fields=["status", "updated_at"])

    document.clauses.all().delete()
    document.stakeholders.all().delete()
    document.import_issues.all().delete()

    sources = _extract_rows(document)
    if not sources:
        document.status = DocumentStatus.FAILED
        document.extraction_summary = {"clauses": 0, "issues": 1}
        document.save(update_fields=["status", "extraction_summary", "updated_at"])
        ImportIssue.objects.create(
            itp=document,
            severity=ImportIssueSeverity.ERROR,
            message="No readable ITP tables were found. Upload a clearer PDF or Excel file.",
        )
        return document.extraction_summary

    current_section = ""
    current_section_title = ""
    sequence = 0
    previous_clause: ITPClause | None = None
    stakeholder_cache: dict[str, ITPStakeholder] = {}
    created_clauses: list[ITPClause] = []
    seen_codes: defaultdict[str, int] = defaultdict(int)

    for source_name, rows in sources:
        header_map: dict[str, int] | None = None
        stakeholder_indexes: list[tuple[str, int]] = []

        for row_number, row in enumerate(rows, start=1):
            if not any(clean_cell(cell) for cell in row):
                continue

            if _looks_like_header(row):
                header_map = _find_header_map(row)
                verifying_idx = header_map.get("verifying", -1)
                stakeholder_indexes = []
                for idx in range(verifying_idx + 1, len(row)):
                    name = clean_cell(row[idx])
                    if not name:
                        continue
                    normal = normalise_header(name)
                    if normal in {"INTERVENTION POINTS", "INSPECTION CLASS"}:
                        continue
                    stakeholder_indexes.append((name, idx))
                    if name not in stakeholder_cache:
                        stakeholder_cache[name] = ITPStakeholder.objects.create(
                            itp=document,
                            name=name,
                            display_order=len(stakeholder_cache) + 1,
                        )
                previous_clause = None
                continue

            if not header_map:
                continue

            action = _safe_value(row, header_map.get("action")).strip()
            activity = _safe_value(row, header_map.get("activity"))

            if action.upper().startswith("NOTES"):
                break

            section = _section_from_row(action, activity)
            if section:
                current_section, current_section_title = section
                previous_clause = None
                continue

            if _is_clause(action):
                sequence += 1
                base_code = f"{current_section}-{action}" if current_section else action
                seen_codes[base_code] += 1
                clause_code = base_code
                if seen_codes[base_code] > 1:
                    clause_code = f"{base_code}-{seen_codes[base_code]}"
                    ImportIssue.objects.create(
                        itp=document,
                        severity=ImportIssueSeverity.WARNING,
                        source_location=f"{source_name}, row {row_number}",
                        message=(
                            f"Duplicate clause {base_code} was renamed to {clause_code}. "
                            "QC must review the clause numbering."
                        ),
                    )

                clause = ITPClause.objects.create(
                    itp=document,
                    section_code=current_section,
                    section_title=current_section_title,
                    clause_number=action,
                    clause_code=clause_code,
                    sequence_order=sequence,
                    activity=activity,
                    reference_document=_safe_value(row, header_map.get("reference")),
                    characteristics=_safe_value(row, header_map.get("characteristics")),
                    inspection_extent=_safe_value(row, header_map.get("characteristics")),
                    acceptance_criteria=_safe_value(row, header_map.get("acceptance")),
                    verifying_document=_safe_value(row, header_map.get("verifying")),
                    raw_source={"source": source_name, "row": row_number},
                )
                created_clauses.append(clause)
                previous_clause = clause

                for stakeholder_name, idx in stakeholder_indexes:
                    raw_point = _safe_value(row, idx)
                    if not raw_point:
                        continue
                    code, sampling = _normalise_intervention(raw_point)
                    ITPClauseIntervention.objects.create(
                        clause=clause,
                        stakeholder=stakeholder_cache[stakeholder_name],
                        point_code=code,
                        sampling_text=sampling,
                        notes=raw_point if code == raw_point else "",
                    )
                continue

            if previous_clause and not action:
                previous_clause.activity = append_text(previous_clause.activity, activity)
                previous_clause.reference_document = append_text(
                    previous_clause.reference_document,
                    _safe_value(row, header_map.get("reference")),
                )
                previous_clause.characteristics = append_text(
                    previous_clause.characteristics,
                    _safe_value(row, header_map.get("characteristics")),
                )
                previous_clause.inspection_extent = previous_clause.characteristics
                previous_clause.acceptance_criteria = append_text(
                    previous_clause.acceptance_criteria,
                    _safe_value(row, header_map.get("acceptance")),
                )
                previous_clause.verifying_document = append_text(
                    previous_clause.verifying_document,
                    _safe_value(row, header_map.get("verifying")),
                )
                previous_clause.save(
                    update_fields=[
                        "activity",
                        "reference_document",
                        "characteristics",
                        "inspection_extent",
                        "acceptance_criteria",
                        "verifying_document",
                        "updated_at",
                    ]
                )

    for clause in created_clauses:
        if "." in clause.clause_number:
            parent_number = clause.clause_number.rsplit(".", 1)[0]
            parent_code = f"{clause.section_code}-{parent_number}" if clause.section_code else parent_number
            parent = next((item for item in created_clauses if item.clause_code == parent_code), None)
            if parent:
                clause.parent = parent
                clause.save(update_fields=["parent", "updated_at"])

    for predecessor, successor in zip(created_clauses, created_clauses[1:]):
        ITPClauseDependency.objects.get_or_create(
            predecessor=predecessor,
            successor=successor,
            defaults={
                "dependency_type": DependencyType.FINISH_TO_START,
                "mandatory": True,
                "applies_to_same_annexure_line": True,
                "blocking_if_predecessor_is_hold": True,
            },
        )

    hold_count = document.clauses.filter(is_hold_point=True).count()
    issue_count = document.import_issues.count()
    document.status = DocumentStatus.QC_REVIEW if created_clauses else DocumentStatus.FAILED
    document.extraction_summary = {
        "clauses": len(created_clauses),
        "stakeholders": len(stakeholder_cache),
        "hold_points": hold_count,
        "issues": issue_count,
    }
    document.save(update_fields=["status", "extraction_summary", "updated_at"])

    if not created_clauses:
        ImportIssue.objects.create(
            itp=document,
            severity=ImportIssueSeverity.ERROR,
            message=(
                "Tables were found, but no clause rows could be recognised. "
                "Use Excel or manually enter the clauses during QC review."
            ),
        )

    return document.extraction_summary
