from __future__ import annotations

from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.forms import formset_factory

from .models import (
    CompletionStatus,
    CoverageResult,
    DocumentStatus,
    ExecutionStatus,
    ITPActivityExecution,
    ITPAnnexure,
    ITPAnnexureLine,
    ITPClause,
    ITPDocument,
    ITPLineClauseMapping,
    MappingReviewStatus,
    NoticeOfInspection,
    SourceFormat,
)


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"


class ITPUploadForm(forms.ModelForm):
    class Meta:
        model = ITPDocument
        fields = [
            "sales_order",
            "document_number",
            "revision",
            "title",
            "original_file",
        ]

    def clean_original_file(self):
        upload = self.cleaned_data["original_file"]
        suffix = Path(upload.name).suffix.lower()
        if suffix not in {".pdf", ".xlsx", ".xls"}:
            raise forms.ValidationError("ITP must be PDF, XLSX, or XLS.")
        return upload

    def save(self, commit=True):
        instance = super().save(commit=False)
        suffix = Path(instance.original_file.name).suffix.lower()
        instance.source_format = SourceFormat.PDF if suffix == ".pdf" else SourceFormat.EXCEL
        if commit:
            instance.save()
        return instance


class AnnexureUploadForm(forms.ModelForm):
    class Meta:
        model = ITPAnnexure
        fields = [
            "sales_order",
            "document_number",
            "revision",
            "title",
            "original_file",
        ]

    def clean_original_file(self):
        upload = self.cleaned_data["original_file"]
        suffix = Path(upload.name).suffix.lower()
        if suffix not in {".xlsx", ".xls"}:
            raise forms.ValidationError("Annexure must be an Excel file (XLSX or XLS).")
        return upload


class ITPClauseForm(forms.ModelForm):
    class Meta:
        model = ITPClause
        fields = [
            "section_code",
            "section_title",
            "clause_number",
            "clause_code",
            "sequence_order",
            "parent",
            "activity",
            "reference_document",
            "characteristics",
            "inspection_extent",
            "acceptance_criteria",
            "verifying_document",
            "is_hold_point",
            "hold_release_mode",
            "completion_followup_days",
            "is_active",
        ]
        widgets = {
            "activity": forms.Textarea(attrs={"rows": 3}),
            "reference_document": forms.Textarea(attrs={"rows": 3}),
            "characteristics": forms.Textarea(attrs={"rows": 3}),
            "inspection_extent": forms.Textarea(attrs={"rows": 2}),
            "acceptance_criteria": forms.Textarea(attrs={"rows": 4}),
            "verifying_document": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.itp_id:
            self.fields["parent"].queryset = ITPClause.objects.filter(
                itp=self.instance.itp
            ).exclude(pk=self.instance.pk)


class AnnexureLineForm(forms.ModelForm):
    class Meta:
        model = ITPAnnexureLine
        fields = [
            "po_line_no",
            "description",
            "quantity",
            "inspection_class",
            "nde_applicable",
            "temperature_text",
            "tag_number",
            "piping_class",
            "service",
            "insulation",
            "datasheet_number",
            "valve_size",
            "pressure_class",
            "valve_type",
            "body_material",
            "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class NOIForm(forms.ModelForm):
    class Meta:
        model = NoticeOfInspection
        fields = [
            "itp",
            "annexure",
            "scheduled_start",
            "scheduled_end",
            "location",
            "responsible_user",
        ]
        widgets = {
            "scheduled_start": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "scheduled_end": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["itp"].queryset = ITPDocument.objects.filter(status=DocumentStatus.ACTIVE)
        self.fields["annexure"].queryset = ITPAnnexure.objects.filter(
            status=DocumentStatus.ACTIVE
        )
        self.fields["responsible_user"].queryset = get_user_model().objects.filter(
            is_active=True
        )
        self.fields["scheduled_start"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["scheduled_end"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        cleaned = super().clean()
        itp = cleaned.get("itp")
        annexure = cleaned.get("annexure")
        if itp and annexure and itp.sales_order_id != annexure.sales_order_id:
            raise forms.ValidationError("ITP and annexure must belong to the same Sales Order.")
        return cleaned


class NOICoverageForm(forms.Form):
    clause = forms.ModelChoiceField(queryset=ITPClause.objects.none())
    annexure_line = forms.ModelChoiceField(queryset=ITPAnnexureLine.objects.none())
    offered_quantity = forms.DecimalField(min_value=0.001, max_digits=14, decimal_places=3)
    heat_numbers = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 1}))
    serial_numbers = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 1}))

    def __init__(self, *args, itp=None, annexure=None, **kwargs):
        super().__init__(*args, **kwargs)
        if itp:
            self.fields["clause"].queryset = ITPClause.objects.filter(
                itp=itp,
                is_active=True,
                line_mappings__is_applicable=True,
                line_mappings__review_status=MappingReviewStatus.APPROVED,
            ).distinct()
        else:
            self.fields["clause"].queryset = ITPClause.objects.filter(
                itp__status=DocumentStatus.ACTIVE,
                is_active=True,
            )
        if annexure:
            self.fields["annexure_line"].queryset = ITPAnnexureLine.objects.filter(
                annexure=annexure, is_active=True
            )
        else:
            self.fields["annexure_line"].queryset = ITPAnnexureLine.objects.filter(
                annexure__status=DocumentStatus.ACTIVE,
                is_active=True,
            )


NOICoverageFormSet = formset_factory(NOICoverageForm, extra=1, can_delete=True)


class NOICompletionForm(forms.Form):
    overall_status = forms.ChoiceField(
        choices=[
            (CompletionStatus.COMPLETED, "Completed"),
            (CompletionStatus.NOT_COMPLETED, "Not completed"),
        ],
        widget=forms.RadioSelect,
    )
    comment = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))


class CoverageCompletionForm(forms.Form):
    coverage_id = forms.UUIDField(widget=forms.HiddenInput)
    completed_quantity = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=3
    )
    actual_completion_at = forms.DateTimeField(
        required=False,
        widget=DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    result = forms.ChoiceField(
        required=False,
        choices=[
            (CoverageResult.ACCEPTED, "Accepted"),
            (CoverageResult.REJECTED, "Rejected"),
            (CoverageResult.WAIVED, "Waived"),
        ],
    )
    report_reference = forms.CharField(required=False)


CoverageCompletionFormSet = formset_factory(CoverageCompletionForm, extra=0)


class HoldReleaseForm(forms.Form):
    release_reference = forms.CharField(max_length=255)
    remarks = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))


class CorrectionRequestForm(forms.Form):
    reason = forms.CharField(
        label="What needs to be corrected",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Explain what the uploader needs to fix..."}),
    )


class CommentForm(forms.Form):
    body = forms.CharField(
        label="Comment",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Add a comment..."}),
    )


class InternalActivityExecutionForm(forms.ModelForm):
    class Meta:
        model = ITPActivityExecution
        fields = [
            "mapping",
            "quantity",
            "status",
            "scheduled_end",
            "completed_at",
            "release_reference",
            "remarks",
            "evidence_file",
        ]
        widgets = {
            "scheduled_end": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "completed_at": DateTimeLocalInput(format="%Y-%m-%dT%H:%M"),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mapping"].queryset = ITPLineClauseMapping.objects.filter(
            is_applicable=True,
            review_status=MappingReviewStatus.APPROVED,
        ).select_related("clause", "annexure_line")
        self.fields["status"].choices = [
            (ExecutionStatus.COMPLETED, "Completed"),
            (ExecutionStatus.NOT_COMPLETED, "Not completed"),
            (ExecutionStatus.RELEASED, "Hold point released"),
            (ExecutionStatus.WAIVED, "Waived"),
        ]
