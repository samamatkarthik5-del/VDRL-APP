from __future__ import annotations

from django.db import transaction

from itp.models import (
    ITPAnnexure,
    ITPDocument,
    ITPLineClauseMapping,
    MappingReviewStatus,
    MappingSource,
)


def _contains_any(text: str, terms: list[str]) -> bool:
    upper = (text or "").upper()
    return any(term in upper for term in terms)


def _suggest(clause, line) -> tuple[bool, str]:
    activity = f"{clause.activity} {clause.characteristics} {clause.verifying_document}".upper()
    description = line.description.upper()
    nde = line.nde_applicable.upper()
    service = line.service.upper()
    material = f"{line.body_material} {description}".upper()

    nde_rules = [
        ("UT", ["UT", "ULTRASONIC"]),
        ("MT", ["MT", "MAGNETIC PARTICLE"]),
        ("PT", ["PT", "DP", "DYE PENETRANT", "DIE PENETRATION", "PENETRANT"]),
        ("PMI", ["PMI", "POSITIVE MATERIAL IDENTIFICATION"]),
    ]
    for label, terms in nde_rules:
        if _contains_any(activity, terms):
            applicable = _contains_any(nde, terms)
            return applicable, f"{label} applicability inferred from annexure NDE column: {line.nde_applicable or 'blank'}"

    if "IMPACT" in activity:
        applicable = _contains_any(material, ["A350", "LF2", "LOW TEMPERATURE"])
        return applicable, "Impact test suggested for low-temperature/LF2 material."

    if _contains_any(activity, ["CHEMICAL", "MECHANICAL", "HARDNESS", "HEAT TREATMENT"]):
        return True, "Raw-material inspection suggested for this valve line; QC review required."

    if _contains_any(activity, ["SOUR", "NACE"]):
        applicable = "SOUR" in service and "NON SOUR" not in service
        return applicable, f"Sour-service applicability inferred from service column: {line.service or 'blank'}"

    if _contains_any(
        activity,
        [
            "HYDRO",
            "PRESSURE TEST",
            "AIR SEAT",
            "FINAL VISUAL",
            "DIMENSION",
            "PAINT",
            "PACKING",
            "MARKING",
            "NAME PLATE",
            "MRB",
            "RELEASE NOTE",
            "PUNCH LIST",
        ],
    ):
        return True, "General final inspection/release activity suggested for every annexure line."

    return True, "Default suggested applicability; QC must approve or reject."


@transaction.atomic
def suggest_line_clause_mappings(itp: ITPDocument, annexure: ITPAnnexure) -> dict[str, int]:
    if itp.sales_order_id != annexure.sales_order_id:
        raise ValueError("ITP and annexure must belong to the same Sales Order.")

    created = 0
    updated = 0
    applicable_count = 0
    for clause in itp.clauses.filter(is_active=True):
        for line in annexure.lines.filter(is_active=True):
            applicable, rationale = _suggest(clause, line)
            mapping, was_created = ITPLineClauseMapping.objects.update_or_create(
                clause=clause,
                annexure_line=line,
                defaults={
                    "is_applicable": applicable,
                    "required_quantity": line.quantity if applicable else None,
                    "source": MappingSource.AUTO,
                    "review_status": MappingReviewStatus.SUGGESTED,
                    "rationale": rationale,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
            if applicable:
                applicable_count += 1
    return {"created": created, "updated": updated, "applicable": applicable_count}
