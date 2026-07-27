from pathlib import Path

from django.core.exceptions import ValidationError
from django import forms
from django.contrib.auth import get_user_model

from .models import (
    CRSComment,
    CRSRegister,
    CustomerVDRLTemplate,
    Department,
    DocumentFile,
    DocumentTransaction,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
    SalesOrder
)

User = get_user_model()


class SalesOrderVDRLDocumentUpdateForm(forms.ModelForm):
    """
    Allows project users to maintain order-specific VDRL information.

    Customer document code belongs here, not in the customer template.
    """

    class Meta:
        model = SalesOrderVDRLDocument

        fields = (
            "customer_document_code",
            "applicability_status",
            "planned_submission_date",
            "forecast_submission_date",
            "responsible_department",
            "responsible_person",
            "remarks",
        )

        widgets = {
            "customer_document_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter customer document code",
                }
            ),
            "applicability_status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "planned_submission_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "forecast_submission_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "responsible_department": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "responsible_person": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields[
            "responsible_department"
        ].queryset = Department.objects.filter(
            is_active=True
        ).order_by("name")

        self.fields[
            "responsible_person"
        ].queryset = User.objects.filter(
            is_active=True
        ).order_by(
            "first_name",
            "last_name",
            "username",
        )


class DocumentTransactionActionForm(forms.ModelForm):
    """
    Form used to record workflow actions.

    Document, transaction type and created-by user are controlled
    by the view and are not entered manually by the user.
    """

    class Meta:
        model = DocumentTransaction

        fields = (
            "transaction_at",
            "revision",
            "responsible_person_after_event",
            "customer_comment_count",
            "crs_reference",
            "remarks",
        )

        widgets = {
            "transaction_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),
            "revision": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: 0, 1, A, B",
                }
            ),
            "responsible_person_after_event": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "customer_comment_count": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                }
            ),
            "crs_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: CRS-001",
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["transaction_at"].input_formats = [
            "%Y-%m-%dT%H:%M"
    ]

        self.fields[
        "responsible_person_after_event"
    ].queryset = User.objects.filter(
        is_active=True
    ).order_by(
        "first_name",
        "last_name",
        "username",
    )

    # This field is hidden for most workflow actions.
        self.fields["customer_comment_count"].required = False
        self.fields["customer_comment_count"].initial = 0


def clean_customer_comment_count(self):
    return self.cleaned_data.get("customer_comment_count") or 0

class DocumentFileUploadForm(forms.ModelForm):
    """
    Upload files against an actual Sales Order VDRL document.
    """

    allowed_extensions = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".csv",
        ".txt",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".zip",
        ".rar",
        ".7z",
        ".dwg",
        ".msg",
        ".eml",
        ".ppt",
        ".pptx",
    }

    maximum_file_size = (
        100 * 1024 * 1024
    )

    class Meta:
        model = DocumentFile

        fields = (
            "file_type",
            "revision",
            "cycle_number",
            "file",
            "description",
            "is_current",
        )

        widgets = {
            "file_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "revision": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: 0, 1, A, B"
                    ),
                }
            ),

            "cycle_number": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                }
            ),

            "file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def __init__(
        self,
        *args,
        document=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.document = document

        if document:
            self.fields[
                "revision"
            ].initial = (
                document.current_revision
            )

            self.fields[
                "cycle_number"
            ].initial = (
                document.current_cycle
            )

    def clean_file(self):
        uploaded_file = (
            self.cleaned_data.get(
                "file"
            )
        )

        if not uploaded_file:
            return uploaded_file

        extension = (
            Path(
                uploaded_file.name
            )
            .suffix
            .lower()
        )

        if (
            extension
            not in self.allowed_extensions
        ):
            raise ValidationError(
                (
                    f"File type '{extension}' "
                    "is not permitted."
                )
            )

        if (
            uploaded_file.size
            > self.maximum_file_size
        ):
            raise ValidationError(
                (
                    "The file is larger than "
                    "the 100 MB upload limit."
                )
            )

        return uploaded_file
    
class CRSRegisterForm(forms.ModelForm):
    """
    Create or update one CRS register for one
    customer review cycle.
    """

    class Meta:
        model = CRSRegister

        fields = (
            "source_return_transaction",
            "cycle_number",
            "document_revision",
            "crs_reference",
            "expected_comment_count",
            "status",
            "opened_at",
            "target_completion_date",
            "prepared_by",
            "reviewed_by",
            "approved_by",
            "crs_file",
            "remarks",
        )

        widgets = {
            "source_return_transaction": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "cycle_number": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1,
                }
            ),

            "document_revision": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "crs_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: CRS-001",
                }
            ),

            "expected_comment_count": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "opened_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),

            "target_completion_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "prepared_by": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "reviewed_by": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "approved_by": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "crs_file": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        document=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.document = document

        self.fields[
            "opened_at"
        ].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

        user_queryset = (
            User.objects
            .filter(is_active=True)
            .order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

        self.fields[
            "prepared_by"
        ].queryset = user_queryset

        self.fields[
            "reviewed_by"
        ].queryset = user_queryset

        self.fields[
            "approved_by"
        ].queryset = user_queryset

        if document:
            self.fields[
                "source_return_transaction"
            ].queryset = (
                DocumentTransaction.objects
                .filter(
                    document=document,
                    transaction_type__in=[
                        DocumentTransaction
                        .TransactionType
                        .RETURNED_WITH_COMMENTS,

                        DocumentTransaction
                        .TransactionType
                        .APPROVED_WITH_COMMENTS,
                    ],
                )
                .order_by(
                    "-transaction_at"
                )
            )

            self.fields[
                "crs_file"
            ].queryset = (
                DocumentFile.objects
                .filter(
                    document=document,
                    file_type=(
                        DocumentFile
                        .FileType
                        .CRS
                    ),
                    is_active=True,
                )
                .order_by(
                    "-uploaded_at"
                )
            )

        else:
            self.fields[
                "source_return_transaction"
            ].queryset = (
                DocumentTransaction.objects.none()
            )

            self.fields[
                "crs_file"
            ].queryset = (
                DocumentFile.objects.none()
            )


class CRSCommentForm(forms.ModelForm):
    """
    Individual customer comment form.
    """

    class Meta:
        model = CRSComment

        fields = (
            "comment_number",
            "page_reference",
            "clause_reference",
            "customer_comment",
            "category",
            "assigned_department",
            "assigned_person",
            "decision",
            "supplier_response",
            "internal_action_required",
            "document_update_status",
            "status",
            "customer_disposition",
            "assigned_at",
            "target_response_date",
            "response_completed_at",
            "remarks",
        )

        widgets = {
            "comment_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "page_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "clause_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "customer_comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                }
            ),

            "category": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "assigned_department": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "assigned_person": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "decision": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "supplier_response": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 6,
                }
            ),

            "internal_action_required": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),

            "document_update_status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "customer_disposition": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "assigned_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),

            "target_response_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "response_completed_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),

            "remarks": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "assigned_at"
        ].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

        self.fields[
            "response_completed_at"
        ].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

        self.fields[
            "assigned_department"
        ].queryset = (
            Department.objects
            .filter(is_active=True)
            .order_by("name")
        )

        self.fields[
            "assigned_person"
        ].queryset = (
            User.objects
            .filter(is_active=True)
            .order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

class BaseExcelImportForm(forms.Form):
    """
    Common controls for all Excel imports.
    """

    class ImportMode:
        CREATE_ONLY = (
            "CREATE_ONLY"
        )

        UPDATE_EXISTING = (
            "UPDATE_EXISTING"
        )

        UPSERT = (
            "UPSERT"
        )

    IMPORT_MODE_CHOICES = [
        (
            ImportMode.CREATE_ONLY,
            "Create New Records Only",
        ),
        (
            ImportMode.UPDATE_EXISTING,
            "Update Existing Records Only",
        ),
        (
            ImportMode.UPSERT,
            "Create New and Update Existing",
        ),
    ]

    excel_file = forms.FileField(
        label="Excel File",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".xlsx",
            }
        ),
    )

    import_mode = forms.ChoiceField(
        choices=IMPORT_MODE_CHOICES,
        initial=ImportMode.UPSERT,
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label=(
            "Dry Run - Validate Only, "
            "Do Not Save Data"
        ),
    )

    def clean_excel_file(self):
        uploaded_file = (
            self.cleaned_data[
                "excel_file"
            ]
        )

        if not (
            uploaded_file
            .name
            .lower()
            .endswith(".xlsx")
        ):
            raise forms.ValidationError(
                (
                    "Only .xlsx Excel files "
                    "are accepted."
                )
            )

        maximum_size = (
            20
            * 1024
            * 1024
        )

        if (
            uploaded_file.size
            > maximum_size
        ):
            raise forms.ValidationError(
                (
                    "The Excel file exceeds "
                    "the 20 MB upload limit."
                )
            )

        return uploaded_file


class CustomerTemplateExcelImportForm(
    BaseExcelImportForm
):
    template = forms.ModelChoiceField(
        queryset=(
            CustomerVDRLTemplate
            .objects
            .none()
        ),
        label="Customer VDRL Template",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    def __init__(
        self,
        *args,
        template_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if template_queryset is not None:
            self.fields[
                "template"
            ].queryset = (
                template_queryset
            )


class SalesOrderVDRLExcelImportForm(
    BaseExcelImportForm
):
    vdrl = forms.ModelChoiceField(
        queryset=(
            SalesOrderVDRL
            .objects
            .none()
        ),
        label="Sales Order VDRL",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    def __init__(
        self,
        *args,
        vdrl_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if vdrl_queryset is not None:
            self.fields[
                "vdrl"
            ].queryset = (
                vdrl_queryset
            )


class CRSCommentExcelImportForm(
    BaseExcelImportForm
):
    crs = forms.ModelChoiceField(
        queryset=(
            CRSRegister
            .objects
            .none()
        ),
        label="CRS Register",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    def __init__(
        self,
        *args,
        crs_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if crs_queryset is not None:
            self.fields[
                "crs"
            ].queryset = (
                crs_queryset
            )

class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder

        fields = [
            "sales_order_number",
            "customer",
            "project",
            "order_date",
            "project_manager",
            "document_controller",
            "authorized_users",
            "is_active",
        ]

        widgets = {
            "authorized_users": (
                forms.CheckboxSelectMultiple()
            ),
        }