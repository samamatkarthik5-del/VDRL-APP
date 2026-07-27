from django import forms
from django.core.validators import FileExtensionValidator


class CalibrationExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        label="Calibration Excel File",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["xlsx", "xlsm"],
            )
        ],
        help_text=(
            "Upload the calibration template in XLSX or XLSM format."
        ),
    )

    update_existing = forms.BooleanField(
        required=False,
        initial=True,
        label="Update existing instruments",
        help_text=(
            "Existing instruments are matched using instrument code, "
            "purchase serial number, asset code or serial number."
        ),
    )