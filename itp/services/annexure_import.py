from __future__ import annotations

import re
from pathlib import Path

from django.db import transaction

from itp.models import (
    DocumentStatus,
    ImportIssue,
    ImportIssueSeverity,
    ITPAnnexure,
    ITPAnnexureLine,
)

from .parsing import clean_cell, normalise_header, parse_temperature_range, to_decimal
from .readers import read_excel_rows


COLUMN_ALIASES = {
    "po_line_no": ["PO SL", "PO SL NUMBER", "PO SERIAL", "LINE NO", "ITEM NO"],
    "description": ["DESCRIPTION", "VALVE DESCRIPTION", "ITEM DESCRIPTION"],
    "quantity": ["QTY", "QUANTITY"],
    "inspection_class": ["INSPECTION CLASS", "IC"],
    "nde_applicable": ["NDE APPLICABLE FOR BODY EP", "NDE APPLICABLE", "NDE"],
    "temperature_text": ["TEMPERATURE C", "TEMPERATURE", "DESIGN TEMPERATURE"],
    "tag_number": ["TAG NUMBER", "TAG NO", "TAG"],
    "piping_class": ["PIPING CLASS", "PIPE CLASS"],
    "service": ["SERVICE"],
    "insulation": ["INSULATION"],
}
REQUIRED_FIELDS = {"po_line_no", "description", "quantity"}


def _find_header_map(row: list[object]) -> dict[str, int]:
    normalised = [normalise_header(value) for value in row]
    mapping: dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for idx, header in enumerate(normalised):
            if any(alias == header or alias in header for alias in aliases):
                mapping[field] = idx
                break
    return mapping


def _extract_description_fields(description: str) -> dict[str, str]:
    result = {
        "datasheet_number": "",
        "valve_size": "",
        "pressure_class": "",
        "valve_type": "",
        "body_material": "",
    }

    datasheet = re.search(
        r"REFER\s+DATASHEET\s+NO\.?\s*[:\-]?\s*([A-Z0-9_./-]+)",
        description,
        flags=re.IGNORECASE,
    )
    if datasheet:
        result["datasheet_number"] = datasheet.group(1).rstrip(")")

    size = re.search(r"(^|\s)(\d+(?:\.\d+)?(?:/\d+)?\s*\")", description)
    if size:
        result["valve_size"] = size.group(2).replace(" ", "")

    pressure = re.search(r"\bCL\s*([0-9]+)\b", description, flags=re.IGNORECASE)
    if pressure:
        result["pressure_class"] = f"CL{pressure.group(1)}"

    upper = description.upper()
    for valve_name in [
        "BALL",
        "GATE",
        "GLOBE",
        "SWING CHECK",
        "PISTON CHECK",
        "CHECK",
        "BUTTERFLY",
        "PLUG",
    ]:
        if valve_name in upper:
            result["valve_type"] = valve_name.title()
            break

    material_patterns = [
        r"A350[- ]?LF2(?:[- ]?1|\s+CL\s*1)?",
        r"A182[- ]?F316(?:/F316L)?(?:[- ]?DG)?",
        r"A105N?",
        r"A216[- ]?WCB",
        r"A351[- ]?CF8M",
        r"A182[- ]?F51",
        r"A182[- ]?F53",
        r"B564[- ]?N06625",
    ]
    for pattern in material_patterns:
        material = re.search(pattern, description, flags=re.IGNORECASE)
        if material:
            result["body_material"] = material.group(0).upper()
            break

    return result


@transaction.atomic
def import_annexure(annexure: ITPAnnexure, replace_existing: bool = True) -> dict[str, int]:
    suffix = Path(annexure.original_file.name).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise ValueError("Annexure must be an Excel file.")

    annexure.status = DocumentStatus.EXTRACTING
    annexure.save(update_fields=["status", "updated_at"])
    annexure.import_issues.all().delete()
    if replace_existing:
        annexure.lines.all().delete()

    sheets = read_excel_rows(annexure.original_file)
    imported = 0
    skipped = 0
    errors = 0
    duplicate_lines: set[str] = set()

    for sheet_name, rows in sheets:
        header_map: dict[str, int] | None = None
        header_row = 0
        for idx, row in enumerate(rows[:30], start=1):
            candidate = _find_header_map(row)
            if REQUIRED_FIELDS.issubset(candidate):
                header_map = candidate
                header_row = idx
                break

        if not header_map:
            ImportIssue.objects.create(
                annexure=annexure,
                severity=ImportIssueSeverity.WARNING,
                source_location=sheet_name,
                message="No recognised annexure header row was found in this sheet.",
            )
            continue

        for row_number, row in enumerate(rows[header_row:], start=header_row + 1):
            values = {
                field: clean_cell(row[index]) if index < len(row) else ""
                for field, index in header_map.items()
            }
            if not any(values.values()):
                continue

            po_line_no = values.get("po_line_no", "")
            description = values.get("description", "")
            quantity = to_decimal(values.get("quantity", ""))

            row_errors: list[str] = []
            if not po_line_no:
                row_errors.append("PO line number is blank")
            if not description:
                row_errors.append("Description is blank")
            if quantity is None or quantity <= 0:
                row_errors.append("Quantity must be greater than zero")
            if po_line_no in duplicate_lines:
                row_errors.append(f"Duplicate PO line number {po_line_no}")

            if row_errors:
                errors += 1
                ImportIssue.objects.create(
                    annexure=annexure,
                    severity=ImportIssueSeverity.ERROR,
                    source_location=f"{sheet_name}, row {row_number}",
                    message="; ".join(row_errors),
                    raw_data=values,
                )
                skipped += 1
                continue

            duplicate_lines.add(po_line_no)
            temperature_text = values.get("temperature_text", "")
            temp_min, temp_max = parse_temperature_range(temperature_text)
            parsed = _extract_description_fields(description)

            ITPAnnexureLine.objects.create(
                annexure=annexure,
                row_number=row_number,
                po_line_no=po_line_no,
                description=description,
                quantity=quantity,
                inspection_class=values.get("inspection_class", ""),
                nde_applicable=values.get("nde_applicable", ""),
                temperature_text=temperature_text,
                temperature_min=temp_min,
                temperature_max=temp_max,
                tag_number=values.get("tag_number", ""),
                piping_class=values.get("piping_class", ""),
                service=values.get("service", ""),
                insulation=values.get("insulation", ""),
                datasheet_number=parsed["datasheet_number"],
                valve_size=parsed["valve_size"],
                pressure_class=parsed["pressure_class"],
                valve_type=parsed["valve_type"],
                body_material=parsed["body_material"],
                raw_data=values,
            )
            imported += 1

    if imported:
        annexure.status = DocumentStatus.QC_REVIEW
    else:
        annexure.status = DocumentStatus.FAILED
        ImportIssue.objects.create(
            annexure=annexure,
            severity=ImportIssueSeverity.ERROR,
            message="No annexure lines were imported from the uploaded workbook.",
        )

    annexure.import_summary = {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "issues": annexure.import_issues.count(),
    }
    annexure.save(update_fields=["status", "import_summary", "updated_at"])
    return annexure.import_summary
