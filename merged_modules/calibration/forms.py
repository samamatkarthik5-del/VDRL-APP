from django import forms
from django.contrib.auth import get_user_model

from .models import CalibrationCycle, CalibrationCycleStatus, Instrument


class DateInput(forms.DateInput):
    input_type = "date"


class InstrumentForm(forms.ModelForm):
    class Meta:
        model = Instrument
        fields = [
            "asset_number",
            "purchase_serial_number",
            "manufacturer_serial_number",
            "description",
            "category",
            "manufacturer",
            "model_number",
            "measurement_range",
            "least_count",
            "purchase_date",
            "calibration_frequency_days",
            "department",
            "location",
            "custodian",
            "monitor",
            "latest_calibration_date",
            "next_due_date",
            "status",
            "notes",
            "is_active",
        ]
        widgets = {
            "purchase_date": DateInput(),
            "latest_calibration_date": DateInput(),
            "next_due_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        users = get_user_model().objects.filter(is_active=True).order_by("first_name", "username")
        self.fields["custodian"].queryset = users
        self.fields["monitor"].queryset = users


class CalibrationCycleForm(forms.ModelForm):
    class Meta:
        model = CalibrationCycle
        fields = [
            "status",
            "collected_from_user_date",
            "sent_to_lab_date",
            "laboratory",
            "returned_from_lab_date",
            "calibration_date",
            "next_due_date",
            "certificate_number",
            "certificate_file",
            "result",
            "repair_details",
            "qc_comments",
            "returned_to_production_date",
            "put_back_in_service_date",
        ]
        widgets = {
            "collected_from_user_date": DateInput(),
            "sent_to_lab_date": DateInput(),
            "returned_from_lab_date": DateInput(),
            "calibration_date": DateInput(),
            "next_due_date": DateInput(),
            "returned_to_production_date": DateInput(),
            "put_back_in_service_date": DateInput(),
            "repair_details": forms.Textarea(attrs={"rows": 3}),
            "qc_comments": forms.Textarea(attrs={"rows": 3}),
        }


class CalibrationVerificationForm(forms.ModelForm):
    class Meta:
        model = CalibrationCycle
        fields = [
            "returned_from_lab_date",
            "calibration_date",
            "next_due_date",
            "certificate_number",
            "certificate_file",
            "result",
            "repair_details",
            "qc_comments",
        ]
        widgets = {
            "returned_from_lab_date": DateInput(),
            "calibration_date": DateInput(),
            "next_due_date": DateInput(),
            "repair_details": forms.Textarea(attrs={"rows": 3}),
            "qc_comments": forms.Textarea(attrs={"rows": 3}),
        }

    def save(self, commit=True, verified_by=None):
        cycle = super().save(commit=False)
        cycle.status = CalibrationCycleStatus.VERIFIED
        cycle.verified_by = verified_by
        if commit:
            cycle.save()
        return cycle
