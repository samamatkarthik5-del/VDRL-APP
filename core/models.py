from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

def safe_path_part(value, fallback="item"):
    """
    Convert customer codes, Sales Order numbers and document codes
    into safe folder names.
    """

    value = str(value or "").strip()

    if not value:
        return fallback

    cleaned_value = slugify(value).replace("-", "_")

    return cleaned_value or fallback


def vdrl_document_upload_path(instance, filename):
    """
    Create the controlled VDRL filing structure automatically.

    Example:

    vdrl_documents/
        petrofac/
        mtv2607001/
        020_itp/
        submitted/
        Rev_1/
        filename_20260714_153000_a1b2c3d4.pdf
    """

    document = instance.document
    sales_order = document.vdrl.sales_order

    customer_folder = safe_path_part(
        sales_order.customer.customer_code,
        "customer",
    )

    sales_order_folder = safe_path_part(
        sales_order.sales_order_number,
        "sales_order",
    )

    document_code = safe_path_part(
        document.customer_document_code
        or document.document.internal_document_code,
        "document",
    )

    sequence_folder = (
        f"{document.sequence_number:03d}_"
        f"{document_code}"
    )

    file_type_folder = safe_path_part(
        instance.file_type,
        "other",
    )

    revision = safe_path_part(
        instance.revision
        or document.current_revision
        or "0",
        "0",
    )

    original_path = Path(filename)

    file_extension = (
        original_path.suffix.lower()
    )

    safe_filename = safe_path_part(
        original_path.stem,
        "file",
    )[:80]

    timestamp = timezone.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    unique_reference = uuid4().hex[:8]

    stored_filename = (
        f"{safe_filename}_"
        f"{timestamp}_"
        f"{unique_reference}"
        f"{file_extension}"
    )

    return (
        f"vdrl_documents/"
        f"{customer_folder}/"
        f"{sales_order_folder}/"
        f"{sequence_folder}/"
        f"{file_type_folder}/"
        f"Rev_{revision}/"
        f"{stored_filename}"
    )

class TimeStampedModel(models.Model):
    """
    Abstract base model providing creation and modification timestamps.
    No separate database table will be created for this model.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProjectTeam(TimeStampedModel):
    team_code = models.CharField(
        max_length=30,
        unique=True,
    )

    team_name = models.CharField(
        max_length=150,
        unique=True,
    )

    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="managed_project_teams",
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = [
            "team_code",
        ]

        verbose_name = "Project Team"
        verbose_name_plural = "Project Teams"

    def clean(self):
        super().clean()

        if (
            self.project_manager_id
            and not self.project_manager.is_active
        ):
            raise ValidationError(
                {
                    "project_manager": (
                        "The selected Project Manager "
                        "is not an active user."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.team_code} - "
            f"{self.team_name}"
        )


class ProjectTeamMember(TimeStampedModel):
    class Role(models.TextChoices):
        APPLICATION_ENGINEER = (
            "APPLICATION_ENGINEER",
            "Application Engineer",
        )

        DOCUMENT_CONTROLLER = (
            "DOCUMENT_CONTROLLER",
            "Document Controller",
        )

    project_team = models.ForeignKey(
        ProjectTeam,
        on_delete=models.CASCADE,
        related_name="members",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_team_memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = [
            "project_team",
            "role",
            "user__first_name",
            "user__username",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "project_team",
                    "user",
                    "role",
                ],
                name="unique_project_team_member_role",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "project_team",
                    "role",
                    "is_active",
                ],
                name="project_team_role_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.user_id and not self.user.is_active:
            raise ValidationError(
                {
                    "user": (
                        "An inactive user cannot be "
                        "added to a Project Team."
                    )
                }
            )

        other_membership = (
            ProjectTeamMember.objects
            .filter(
                user=self.user,
                role=self.role,
                is_active=True,
            )
            .exclude(
                pk=self.pk,
            )
        )

        if other_membership.exists():
            existing = other_membership.first()

            raise ValidationError(
                {
                    "user": (
                        f"This user is already an active "
                        f"{self.get_role_display()} in "
                        f"{existing.project_team}."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.project_team} - "
            f"{self.user} - "
            f"{self.get_role_display()}"
        )

class Department(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Example: QA, QC, ENG, PROJECTS",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_departments",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class EmployeeProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    employee_id = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    job_title = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["employee_id"]

    def __str__(self):
        full_name = self.user.get_full_name().strip()
        display_name = full_name or self.user.username
        return f"{self.employee_id} - {display_name}"


class Customer(TimeStampedModel):
    name = models.CharField(max_length=200, unique=True)
    customer_code = models.CharField(
        max_length=30,
        unique=True,
        help_text="Short customer reference, for example ADNOC or PTF",
    )
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    standard_review_days = models.PositiveIntegerField(
        default=14,
        help_text="Normal customer document review period in calendar days.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.customer_code} - {self.name}"


class Project(TimeStampedModel):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    project_code = models.CharField(max_length=50)
    project_name = models.CharField(max_length=250)
    customer_project_number = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=150, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["customer__name", "project_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "project_code"],
                name="unique_project_code_per_customer",
            )
        ]

    def clean(self):
        errors = {}

        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors["end_date"] = (
                    "Project end date cannot be earlier than the start date."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project_code} - {self.project_name}"


class SalesOrder(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ON_HOLD = "ON_HOLD", "On Hold"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    sales_order_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal Sales Order number.",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sales_orders",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    customer_po_number = models.CharField(max_length=100, blank=True)

    order_date = models.DateField()

    kickoff_date = models.DateField(
        null=True,
        blank=True,
        help_text="Project kick-off meeting date.",
    )

    planned_procurement_date = models.DateField(
        null=True,
        blank=True,
        help_text="Planned procurement start date.",
    )

    manufacturing_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Planned manufacturing start date.",
    )

    planned_inspection_date = models.DateField(
        null=True,
        blank=True,
        help_text="Planned first inspection date.",
    )
    contractual_vdrl_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date by which the initial VDRL must be submitted.",
    )
    planned_delivery_date = models.DateField(null=True, blank=True)

    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_managed_sales_orders",
    )
    application_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_order_application_engineer",
    )
    sales_manager = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="sales_managed_sales_orders",
    verbose_name="Sales Manager",
)
    project_team = models.ForeignKey(
        "ProjectTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders",
    )
    document_controller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_controlled_sales_orders",
    )

    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="authorized_sales_orders",
        verbose_name=(
            "Users Allowed to Access "
            "This Sales Order"
        ),
        help_text=(
            "Only these users may view this "
            "Sales Order and its related "
            "VDRL documents."
        ),
    )
    backup_document_controllers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="backup_document_controlled_sales_orders",
        verbose_name="Backup Document Controllers",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class ApprovalStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        PARTIALLY_APPROVED = "PARTIALLY_APPROVED", "Partially Approved"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    approval_status = models.CharField(
        max_length=30,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.DRAFT,
        db_index=True,
    )

    submitted_for_approval_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_orders_submitted_for_approval",
    )

    submitted_for_approval_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    sales_manager_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_manager_approved_sales_orders",
    )

    sales_manager_approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    sales_manager_approval_comment = models.TextField(
        blank=True,
    )

    project_manager_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_manager_approved_sales_orders",
    )

    project_manager_approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    project_manager_approval_comment = models.TextField(
        blank=True,
    )

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_sales_orders",
    )

    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejection_reason = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["-order_date", "sales_order_number"]
        permissions = [
            (
                "submit_sales_order_for_approval",
                "Can submit Sales Order for approval",
            ),
            (
                "approve_sales_order_as_sales_manager",
                "Can approve Sales Order as Sales Manager",
            ),
            (
                "approve_sales_order_as_project_manager",
                "Can approve Sales Order as Project Manager",
            ),
            (
                "reject_sales_order",
                "Can reject Sales Order",
            ),
            (
                "assign_document_controller",
                "Can assign Document Controller after approval",
            ),
            (
                "view_sales_order_approval_history",
                "Can view Sales Order approval history",
            ),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if self.project_id and self.customer_id:
            if self.project.customer_id != self.customer_id:
                errors["project"] = (
                    "The selected project does not belong to the selected customer."
                )

        if self.contractual_vdrl_date:
            if self.contractual_vdrl_date < self.order_date:
                errors["contractual_vdrl_date"] = (
                    "The contractual VDRL date cannot be earlier than the order date."
                )

        if self.planned_delivery_date:
            if self.planned_delivery_date < self.order_date:
                errors["planned_delivery_date"] = (
                    "The planned delivery date cannot be earlier than the order date."
                )

        if errors:
            raise ValidationError(errors)

        if not self.project_team_id:
            return

        team = self.project_team

        if (
            self.project_manager_id
            and self.project_manager_id != team.project_manager_id
        ):
            raise ValidationError(
                {
                    "project_manager": (
                        "The Project Manager must be the "
                        "manager assigned to the selected "
                        "Project Team."
                    )
                }
            )

        if self.application_engineer_id:
            valid_ae = (
                ProjectTeamMember.objects
                .filter(
                    project_team=team,
                    user_id=self.application_engineer_id,
                    role=(
                        ProjectTeamMember
                        .Role
                        .APPLICATION_ENGINEER
                    ),
                    is_active=True,
                )
                .exists()
            )

            if not valid_ae:
                raise ValidationError(
                    {
                        "application_engineer": (
                            "The Application Engineer must "
                            "belong to the selected "
                            "Project Team."
                        )
                    }
                )

        if self.document_controller_id:
            valid_dc = (
                ProjectTeamMember.objects
                .filter(
                    project_team=team,
                    user_id=self.document_controller_id,
                    role=(
                        ProjectTeamMember
                        .Role
                        .DOCUMENT_CONTROLLER
                    ),
                    is_active=True,
                )
                .exists()
            )

            if not valid_dc:
                raise ValidationError(
                    {
                        "document_controller": (
                            "The Document Controller must "
                            "belong to the selected "
                            "Project Team."
                        )
                    }
                )
        if self.sales_manager_id:
            is_sales_manager = (
                self.sales_manager.is_superuser
                or self.sales_manager.groups.filter(
            name__iexact="SALES MANAGER",
        ).exists()
    )

        if not is_sales_manager:
            raise ValidationError(
            {
                "sales_manager": (
                    "The selected user must belong "
                    "to the SALES MANAGER group."
                )
            }
        )

    def save(self, *args, **kwargs):
        if self.project_team_id:
            self.project_manager_id = self.project_team.project_manager_id

        super().save(*args, **kwargs)

        users_to_authorize = []

        if self.project_manager_id:
            users_to_authorize.append(self.project_manager)

        if self.document_controller_id:
            users_to_authorize.append(self.document_controller)

        if users_to_authorize:
            self.authorized_users.add(*users_to_authorize)

    def __str__(self):
        return f"{self.sales_order_number} - {self.customer.name}"


class DocumentCategory(TimeStampedModel):
    """
    General classification used for VDRL documents.
    Examples: Quality, Engineering, Procedures and Certificates.
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Example: QA, ENG, PROC, CERT",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Document categories"

    def __str__(self):
        return f"{self.code} - {self.name}"


class DocumentMaster(TimeStampedModel):
    """
    Internal master library of documents commonly used in VDRLs.
    Customer-specific codes and titles will be maintained in the template.
    """

    internal_document_code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal document code, for example ITP or QAP.",
    )
    document_title = models.CharField(max_length=250)
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    default_responsible_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_documents",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__name", "document_title"]

    def __str__(self):
        return f"{self.internal_document_code} - {self.document_title}"


class CustomerVDRLTemplate(TimeStampedModel):
    """
    Customer-specific VDRL template.

    A customer may have more than one template, for example:
    - Standard Valve Order
    - Actuated Valve Order
    - Offshore Project
    - ADNOC-Specific Project
    """

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="vdrl_templates",
    )
    template_code = models.CharField(
        max_length=50,
        help_text="Example: PETROFAC-STD or ADNOC-BALL-VALVE",
    )
    template_name = models.CharField(max_length=200)
    revision = models.CharField(
        max_length=20,
        default="0",
        help_text="Template revision, for example 0, 1, A or B.",
    )
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Use this as the default template for the selected customer.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = [
            "customer__name",
            "template_name",
            "-effective_from",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "template_code", "revision"],
                name="unique_customer_template_revision",
            )
        ]

    def clean(self):
        errors = {}

        if self.effective_from and self.effective_to:
            if self.effective_to < self.effective_from:
                errors["effective_to"] = (
                    "Effective-to date cannot be earlier than effective-from date."
                )

        if self.is_default and self.is_active and self.customer_id:
            duplicate_default = CustomerVDRLTemplate.objects.filter(
                customer_id=self.customer_id,
                is_default=True,
                is_active=True,
            )

            if self.pk:
                duplicate_default = duplicate_default.exclude(pk=self.pk)

            if duplicate_default.exists():
                errors["is_default"] = (
                    "This customer already has another active default VDRL template."
                )

        if errors:
            raise ValidationError(errors)
    application_engineer = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="vdrl_template_application_engineer",
    verbose_name="Application Engineer",
)
    def __str__(self):
        return (
            f"{self.customer.customer_code} - "
            f"{self.template_code} Rev.{self.revision}"
        )


class CustomerVDRLTemplateItem(TimeStampedModel):
    """
    Individual document requirement inside a customer VDRL template.
    """

    class RequirementType(models.TextChoices):
        MANDATORY = "MANDATORY", "Mandatory"
        OPTIONAL = "OPTIONAL", "Optional"
        CONDITIONAL = "CONDITIONAL", "Conditional"

    class SubmissionStage(models.TextChoices):
        AFTER_ORDER = "AFTER_ORDER", "After Order Receipt"
        AFTER_KICKOFF = "AFTER_KICKOFF", "After Kick-off Meeting"
        BEFORE_PROCUREMENT = "BEFORE_PROCUREMENT", "Before Procurement"
        BEFORE_MANUFACTURING = (
            "BEFORE_MANUFACTURING",
            "Before Manufacturing",
        )
        BEFORE_INSPECTION = "BEFORE_INSPECTION", "Before Inspection"
        BEFORE_DELIVERY = "BEFORE_DELIVERY", "Before Delivery"
        FINAL_DOSSIER = "FINAL_DOSSIER", "Final Dossier / MRB"
        AS_REQUIRED = "AS_REQUIRED", "As Required"
        MANUAL = "MANUAL", "Manually Planned"

    class DueDateBasis(models.TextChoices):
        ORDER_DATE = "ORDER_DATE", "Sales Order Date"
        KICKOFF_DATE = "KICKOFF_DATE", "Kick-off Meeting Date"
        PROCUREMENT_DATE = (
            "PROCUREMENT_DATE",
            "Planned Procurement Date",
        )
        MANUFACTURING_DATE = (
            "MANUFACTURING_DATE",
            "Manufacturing Start Date",
        )
        INSPECTION_DATE = (
            "INSPECTION_DATE",
            "Planned Inspection Date",
        )
        DELIVERY_DATE = (
            "DELIVERY_DATE",
            "Planned Delivery Date",
        )
        MANUAL = "MANUAL", "Manual Date"

    class FileFormat(models.TextChoices):
        PDF = "PDF", "PDF"
        NATIVE = "NATIVE", "Native / Editable File"
        PDF_AND_NATIVE = "PDF_AND_NATIVE", "PDF and Native File"
        OTHER = "OTHER", "Other"

    template = models.ForeignKey(
        CustomerVDRLTemplate,
        on_delete=models.CASCADE,
        related_name="items",
    )
    sequence_number = models.PositiveSmallIntegerField(
        help_text="Document sequence number in the VDRL.",
    )
    document = models.ForeignKey(
        DocumentMaster,
        on_delete=models.PROTECT,
        related_name="customer_template_items",
    )

    customer_document_title = models.CharField(
        max_length=250,
        blank=True,
        help_text=(
            "Customer-specific title. Leave blank to use the internal "
            "document title."
        ),
    )

    requirement_type = models.CharField(
        max_length=20,
        choices=RequirementType.choices,
        default=RequirementType.MANDATORY,
    )
    condition_description = models.TextField(
        blank=True,
        help_text=(
            "Required when Requirement Type is Conditional. "
            "Example: Applicable only for cryogenic valves."
        ),
    )

    submission_stage = models.CharField(
        max_length=30,
        choices=SubmissionStage.choices,
        default=SubmissionStage.AFTER_ORDER,
    )
    due_date_basis = models.CharField(
        max_length=30,
        choices=DueDateBasis.choices,
        default=DueDateBasis.ORDER_DATE,
    )
    day_offset = models.IntegerField(
        default=0,
        help_text=(
            "Positive number means days after the basis date. "
            "Negative number means days before the basis date."
        ),
    )

    customer_review_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Leave blank to use the customer's standard review period."
        ),
    )

    responsible_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_vdrl_template_items",
    )

    approval_required = models.BooleanField(default=True)
    crs_required = models.BooleanField(default=True)
    include_in_final_mrb = models.BooleanField(default=True)

    required_file_format = models.CharField(
        max_length=20,
        choices=FileFormat.choices,
        default=FileFormat.PDF,
    )

    remarks = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["template", "sequence_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "sequence_number"],
                name="unique_sequence_per_customer_vdrl_template",
            )
        ]

    def clean(self):
        errors = {}

        if (
            self.requirement_type == self.RequirementType.CONDITIONAL
            and not self.condition_description.strip()
        ):
            errors["condition_description"] = (
                "Enter the condition for a conditional document."
            )

        if (
            self.requirement_type != self.RequirementType.CONDITIONAL
            and self.condition_description.strip()
        ):
            errors["condition_description"] = (
                "Condition description should normally be used only for "
                "conditional documents."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def display_document_title(self):
        return self.customer_document_title or self.document.document_title

    def __str__(self):
        return (
            f"{self.template.template_code} - "
            f"{self.sequence_number}: {self.display_document_title}"
        )
    
class SalesOrderVDRL(TimeStampedModel):
    """
    Actual VDRL created for a specific Sales Order.
    The source customer template is retained only for traceability.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="vdrls",
    )

    source_template = models.ForeignKey(
        CustomerVDRLTemplate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="generated_vdrls",
        help_text="Customer template used to generate this Sales Order VDRL.",
    )

    vdrl_number = models.CharField(
        max_length=100,
        help_text="Example: MTV2607001-VDRL-001",
    )

    title = models.CharField(
        max_length=250,
        default="Vendor Document Requirement List",
    )

    revision = models.CharField(
        max_length=20,
        default="0",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    is_current = models.BooleanField(
        default=True,
        help_text="Indicates the current working VDRL revision.",
    )

    generated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_sales_order_vdrls",
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = [
            "-created_at",
            "sales_order__sales_order_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "sales_order",
                    "vdrl_number",
                    "revision",
                ],
                name="unique_sales_order_vdrl_revision",
            )
        ]

    def clean(self):
        errors = {}

        if self.source_template_id and self.sales_order_id:
            if (
                self.source_template.customer_id
                != self.sales_order.customer_id
            ):
                errors["source_template"] = (
                    "The selected VDRL template does not belong "
                    "to the Sales Order customer."
                )

        if self.is_current and self.sales_order_id:
            other_current_vdrls = SalesOrderVDRL.objects.filter(
                sales_order_id=self.sales_order_id,
                is_current=True,
            )

            if self.pk:
                other_current_vdrls = other_current_vdrls.exclude(
                    pk=self.pk
                )

            if other_current_vdrls.exists():
                errors["is_current"] = (
                    "This Sales Order already has another current VDRL."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.sales_order.sales_order_number} - "
            f"{self.vdrl_number} Rev.{self.revision}"
        )


class SalesOrderVDRLDocument(TimeStampedModel):
    """
    Actual document requirement under a Sales Order VDRL.

    Template information is copied into this record so that later changes
    to the customer template do not modify the existing Sales Order VDRL.
    """

    class ApplicabilityStatus(models.TextChoices):
        REQUIRED = "REQUIRED", "Required"
        TO_CONFIRM = "TO_CONFIRM", "To Be Confirmed"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Not Applicable"

    class DocumentStatus(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        UNDER_PREPARATION = (
            "UNDER_PREPARATION",
            "Under Preparation",
        )
        INTERNAL_REVIEW = (
            "INTERNAL_REVIEW",
            "Internal Review",
        )
        READY_FOR_SUBMISSION = (
            "READY_FOR_SUBMISSION",
            "Ready for Submission",
        )
        SUBMITTED = (
            "SUBMITTED",
            "Submitted to Customer",
        )
        UNDER_CUSTOMER_REVIEW = (
            "UNDER_CUSTOMER_REVIEW",
            "Under Customer Review",
        )
        RETURNED_WITH_COMMENTS = (
            "RETURNED_WITH_COMMENTS",
            "Returned with Comments",
        )
        COMMENT_ASSESSMENT = (
            "COMMENT_ASSESSMENT",
            "Comment Assessment in Progress",
        )
        REVISION_IN_PROGRESS = (
            "REVISION_IN_PROGRESS",
            "Revision in Progress",
        )
        CRS_IN_PROGRESS = (
            "CRS_IN_PROGRESS",
            "CRS Preparation in Progress",
        )
        READY_FOR_RESUBMISSION = (
            "READY_FOR_RESUBMISSION",
            "Ready for Resubmission",
        )
        RESUBMITTED = (
            "RESUBMITTED",
            "Resubmitted to Customer",
        )
        APPROVED_WITH_COMMENTS = (
            "APPROVED_WITH_COMMENTS",
            "Approved with Comments",
        )
        APPROVED = (
            "APPROVED",
            "Approved",
        )
        ON_HOLD = (
            "ON_HOLD",
            "On Hold",
        )
        NOT_APPLICABLE = (
            "NOT_APPLICABLE",
            "Not Applicable",
        )
        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )

    vdrl = models.ForeignKey(
        SalesOrderVDRL,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    source_template_item = models.ForeignKey(
        CustomerVDRLTemplateItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_sales_order_documents",
    )

    sequence_number = models.PositiveSmallIntegerField()

    document = models.ForeignKey(
        DocumentMaster,
        on_delete=models.PROTECT,
        related_name="sales_order_vdrl_documents",
    )

    customer_document_code = models.CharField(
        max_length=100,
        blank=True,
    )

    document_title = models.CharField(
        max_length=250,
    )

    requirement_type = models.CharField(
        max_length=20,
        choices=CustomerVDRLTemplateItem.RequirementType.choices,
        default=CustomerVDRLTemplateItem.RequirementType.MANDATORY,
    )

    condition_description = models.TextField(
        blank=True,
    )

    applicability_status = models.CharField(
        max_length=20,
        choices=ApplicabilityStatus.choices,
        default=ApplicabilityStatus.REQUIRED,
    )

    submission_stage = models.CharField(
        max_length=30,
        choices=CustomerVDRLTemplateItem.SubmissionStage.choices,
        default=CustomerVDRLTemplateItem.SubmissionStage.AFTER_ORDER,
    )

    due_date_basis = models.CharField(
        max_length=30,
        choices=CustomerVDRLTemplateItem.DueDateBasis.choices,
        default=CustomerVDRLTemplateItem.DueDateBasis.ORDER_DATE,
    )

    day_offset = models.IntegerField(
        default=0,
    )

    planned_submission_date = models.DateField(
        null=True,
        blank=True,
    )

    forecast_submission_date = models.DateField(
        null=True,
        blank=True,
    )

    customer_review_days = models.PositiveIntegerField(
        default=14,
    )

    responsible_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_order_vdrl_documents",
    )

    responsible_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responsible_vdrl_documents",
    )

    current_revision = models.CharField(
        max_length=20,
        default="0",
    )

    status = models.CharField(
        max_length=40,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PLANNED,
    )

    current_cycle = models.PositiveSmallIntegerField(
        default=0,
        help_text="0 before first submission, 1 for first submission cycle, etc.",
    )

    first_submission_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_submission_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_customer_return_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    final_approval_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    customer_review_due_date = models.DateField(
        null=True,
        blank=True,
    )

    current_action_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time when the current holder received the action.",
    )

    approval_required = models.BooleanField(
        default=True,
    )

    crs_required = models.BooleanField(
        default=True,
    )

    include_in_final_mrb = models.BooleanField(
        default=True,
    )

    required_file_format = models.CharField(
        max_length=20,
        choices=CustomerVDRLTemplateItem.FileFormat.choices,
        default=CustomerVDRLTemplateItem.FileFormat.PDF,
    )

    remarks = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = [
            "vdrl",
            "sequence_number",
        ]

        permissions = [
    (
        "view_all_vdrl_data",
        "Can view all VDRL data",
    ),
    (
        "manage_vdrl_document_details",
        "Can manage VDRL document details",
    ),
    (
        "manage_vdrl_workflow",
        "Can manage VDRL workflow",
    ),
    (
        "manage_vdrl_files",
        "Can manage VDRL document files",
    ),
    (
        "manage_crs",
        "Can manage CRS registers and comments",
    ),
    (
        "view_management_reports",
        "Can view VDRL management reports",
    ),
    (
        "bulk_import_vdrl_data",
        "Can bulk import VDRL data",
    ),
    (
        "view_audit_log",
        "Can view VDRL audit log",
    ),
]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vdrl",
                    "sequence_number",
                ],
                name="unique_sequence_per_sales_order_vdrl",
            ),
            models.UniqueConstraint(
                fields=[
                    "vdrl",
                    "source_template_item",
                ],
                name="unique_template_item_per_sales_order_vdrl",
            ),
        ]

    def get_basis_date(self):
        """
        Returns the Sales Order milestone date used to calculate
        the planned submission date.
        """

        sales_order = self.vdrl.sales_order

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.ORDER_DATE
        ):
            return sales_order.order_date

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.KICKOFF_DATE
        ):
            return sales_order.kickoff_date

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.PROCUREMENT_DATE
        ):
            return sales_order.planned_procurement_date

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.MANUFACTURING_DATE
        ):
            return sales_order.manufacturing_start_date

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.INSPECTION_DATE
        ):
            return sales_order.planned_inspection_date

        if (
            self.due_date_basis
            == CustomerVDRLTemplateItem.DueDateBasis.DELIVERY_DATE
        ):
            return sales_order.planned_delivery_date

        return None

    def calculate_planned_submission_date(self):
        """
        Calculate the planned submission date using the milestone
        date and the template day offset.
        """

        basis_date = self.get_basis_date()

        if basis_date is None:
            return None

        return basis_date + timedelta(days=self.day_offset)

    @property
    def current_holder(self):
        """
        Determines who currently holds the document action.
        """

        customer_statuses = {
            self.DocumentStatus.SUBMITTED,
            self.DocumentStatus.UNDER_CUSTOMER_REVIEW,
            self.DocumentStatus.RESUBMITTED,
        }

        completed_statuses = {
            self.DocumentStatus.APPROVED,
            self.DocumentStatus.NOT_APPLICABLE,
            self.DocumentStatus.CANCELLED,
        }

        if self.status in customer_statuses:
            return "Customer"

        if self.status in completed_statuses:
            return "Completed"

        if self.status == self.DocumentStatus.ON_HOLD:
            return "On Hold"

        return "Internal"
    
    @property
    def total_internal_days(self):
        total = self.transactions.filter(
            elapsed_holder_type=DocumentTransaction.HolderType.INTERNAL
        ).aggregate(
            total=models.Sum("elapsed_calendar_days")
        )["total"]

        return total or Decimal("0.00")

    @property
    def total_customer_days(self):
        total = self.transactions.filter(
            elapsed_holder_type=DocumentTransaction.HolderType.CUSTOMER
        ).aggregate(
            total=models.Sum("elapsed_calendar_days")
        )["total"]

        return total or Decimal("0.00")

    @property
    def total_on_hold_days(self):
        total = self.transactions.filter(
            elapsed_holder_type=DocumentTransaction.HolderType.ON_HOLD
        ).aggregate(
            total=models.Sum("elapsed_calendar_days")
        )["total"]

        return total or Decimal("0.00")

    @property
    def current_aging_days(self):
        completed_statuses = {
            self.DocumentStatus.APPROVED,
            self.DocumentStatus.NOT_APPLICABLE,
            self.DocumentStatus.CANCELLED,
        }

        if self.status in completed_statuses:
            return Decimal("0.00")

        if not self.current_action_since:
            return Decimal("0.00")

        elapsed_seconds = (
            timezone.now() - self.current_action_since
        ).total_seconds()

        elapsed_days = max(elapsed_seconds, 0) / 86400

        return Decimal(
            str(round(elapsed_days, 2))
        )

    def get_default_file(self):
        """
        Return the most relevant file according to the
        document's current workflow status.
        """

        file_type = None

        if self.status == self.DocumentStatus.APPROVED:
            file_type = DocumentFile.FileType.APPROVED

        elif self.status in {
            self.DocumentStatus.SUBMITTED,
            self.DocumentStatus.UNDER_CUSTOMER_REVIEW,
            self.DocumentStatus.RESUBMITTED,
        }:
            file_type = DocumentFile.FileType.SUBMITTED

        elif self.status in {
            self.DocumentStatus.RETURNED_WITH_COMMENTS,
            self.DocumentStatus.COMMENT_ASSESSMENT,
        }:
            file_type = (
                DocumentFile
                .FileType
                .CUSTOMER_RETURNED
            )

        elif self.status == self.DocumentStatus.CRS_IN_PROGRESS:
            file_type = DocumentFile.FileType.CRS

        elif self.status in {
            self.DocumentStatus.PLANNED,
            self.DocumentStatus.UNDER_PREPARATION,
            self.DocumentStatus.INTERNAL_REVIEW,
            self.DocumentStatus.READY_FOR_SUBMISSION,
            self.DocumentStatus.REVISION_IN_PROGRESS,
            self.DocumentStatus.READY_FOR_RESUBMISSION,
        }:
            file_type = DocumentFile.FileType.WORKING

        if file_type:
            preferred_file = (
                self.files
                .filter(
                    file_type=file_type,
                    is_active=True,
                    is_current=True,
                )
                .order_by(
                    "-uploaded_at",
                    "-id",
                )
                .first()
            )

            if preferred_file:
                return preferred_file

        return (
            self.files
            .filter(
                is_active=True,
                is_current=True,
            )
            .order_by(
                "-uploaded_at",
                "-id",
            )
            .first()
        )

    @property
    def default_file(self):
        return self.get_default_file()

    def __str__(self):
        return (
            f"{self.vdrl.sales_order.sales_order_number} - "
            f"{self.sequence_number} - {self.document_title}"
        )

class DocumentTransaction(TimeStampedModel):
    """
    Append-only lifecycle transaction for a VDRL document.

    Each transaction records a workflow event and calculates how long
    the document remained with the holder from the previous transaction.
    """

    class TransactionType(models.TextChoices):
        ASSIGNED_INTERNAL = (
            "ASSIGNED_INTERNAL",
            "Assigned to Internal Owner",
        )

        READY_INITIAL_SUBMISSION = (
            "READY_INITIAL_SUBMISSION",
            "Ready for Initial Submission",
        )

        INITIAL_SUBMISSION = (
            "INITIAL_SUBMISSION",
            "Initial Submission to Customer",
        )

        RETURNED_WITH_COMMENTS = (
            "RETURNED_WITH_COMMENTS",
            "Returned by Customer with Comments",
        )

        COMMENT_ASSESSMENT = (
            "COMMENT_ASSESSMENT",
            "Comment Assessment Started",
        )

        REVISION_STARTED = (
            "REVISION_STARTED",
            "Document Revision Started",
        )

        REVISION_COMPLETED = (
            "REVISION_COMPLETED",
            "Document Revision Completed",
        )

        CRS_STARTED = (
            "CRS_STARTED",
            "CRS Preparation Started",
        )

        CRS_COMPLETED = (
            "CRS_COMPLETED",
            "CRS Preparation Completed",
        )

        RESUBMISSION = (
            "RESUBMISSION",
            "Resubmitted to Customer",
        )

        APPROVED_WITH_COMMENTS = (
            "APPROVED_WITH_COMMENTS",
            "Approved with Comments",
        )

        FINAL_APPROVAL = (
            "FINAL_APPROVAL",
            "Final Approval - No Comments",
        )

        ON_HOLD = (
            "ON_HOLD",
            "Placed On Hold",
        )

        REACTIVATED = (
            "REACTIVATED",
            "Reactivated",
        )

        MARK_NOT_APPLICABLE = (
            "MARK_NOT_APPLICABLE",
            "Marked Not Applicable",
        )

        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )

    class HolderType(models.TextChoices):
        INTERNAL = "INTERNAL", "Internal"
        CUSTOMER = "CUSTOMER", "Customer"
        COMPLETED = "COMPLETED", "Completed"
        ON_HOLD = "ON_HOLD", "On Hold"

    document = models.ForeignKey(
        SalesOrderVDRLDocument,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    transaction_type = models.CharField(
        max_length=40,
        choices=TransactionType.choices,
    )

    transaction_at = models.DateTimeField(
        default=timezone.now,
        help_text="Actual date and time when this transaction occurred.",
    )

    cycle_number = models.PositiveSmallIntegerField(
        default=0,
        editable=False,
    )

    revision = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Document revision applicable to this transaction. "
            "Leave blank to retain the current revision."
        ),
    )

    status_before = models.CharField(
        max_length=40,
        choices=SalesOrderVDRLDocument.DocumentStatus.choices,
        blank=True,
        default="",
        editable=False,
    )

    status_after = models.CharField(
        max_length=40,
        choices=SalesOrderVDRLDocument.DocumentStatus.choices,
        blank=True,
        default="",
        editable=False,
    )

    holder_after_event = models.CharField(
        max_length=20,
        choices=HolderType.choices,
        blank=True,
        default="",
        editable=False,
    )

    responsible_person_after_event = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_vdrl_transactions",
        help_text=(
            "Internal person responsible after this transaction. "
            "Leave blank when the document moves to the customer."
        ),
    )

    customer_comment_count = models.PositiveIntegerField(
        default=0,
    )

    crs_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    remarks = models.TextField(
        blank=True,
    )

    elapsed_calendar_days = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        editable=False,
        help_text=(
            "Calendar days elapsed since the previous transaction."
        ),
    )

    elapsed_holder_type = models.CharField(
        max_length=20,
        choices=HolderType.choices,
        blank=True,
        default="",
        editable=False,
        help_text=(
            "Holder responsible for the elapsed period before this event."
        ),
    )

    elapsed_responsible_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        help_text=(
            "Internal person responsible for the elapsed period."
        ),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_vdrl_transactions",
    )

    class Meta:
        ordering = [
            "document",
            "transaction_at",
            "id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "document",
                    "transaction_at",
                ]
            )
        ]

    def get_status_after(self):
        status_map = {
            self.TransactionType.ASSIGNED_INTERNAL:
                SalesOrderVDRLDocument.DocumentStatus.UNDER_PREPARATION,

            self.TransactionType.READY_INITIAL_SUBMISSION:
                SalesOrderVDRLDocument.DocumentStatus.READY_FOR_SUBMISSION,

            self.TransactionType.INITIAL_SUBMISSION:
                SalesOrderVDRLDocument.DocumentStatus.UNDER_CUSTOMER_REVIEW,

            self.TransactionType.RETURNED_WITH_COMMENTS:
                SalesOrderVDRLDocument.DocumentStatus.RETURNED_WITH_COMMENTS,

            self.TransactionType.COMMENT_ASSESSMENT:
                SalesOrderVDRLDocument.DocumentStatus.COMMENT_ASSESSMENT,

            self.TransactionType.REVISION_STARTED:
                SalesOrderVDRLDocument.DocumentStatus.REVISION_IN_PROGRESS,

            self.TransactionType.REVISION_COMPLETED:
                SalesOrderVDRLDocument.DocumentStatus.READY_FOR_RESUBMISSION,

            self.TransactionType.CRS_STARTED:
                SalesOrderVDRLDocument.DocumentStatus.CRS_IN_PROGRESS,

            self.TransactionType.CRS_COMPLETED:
                SalesOrderVDRLDocument.DocumentStatus.READY_FOR_RESUBMISSION,

            self.TransactionType.RESUBMISSION:
                SalesOrderVDRLDocument.DocumentStatus.UNDER_CUSTOMER_REVIEW,

            self.TransactionType.APPROVED_WITH_COMMENTS:
                SalesOrderVDRLDocument.DocumentStatus.APPROVED_WITH_COMMENTS,

            self.TransactionType.FINAL_APPROVAL:
                SalesOrderVDRLDocument.DocumentStatus.APPROVED,

            self.TransactionType.ON_HOLD:
                SalesOrderVDRLDocument.DocumentStatus.ON_HOLD,

            self.TransactionType.REACTIVATED:
                SalesOrderVDRLDocument.DocumentStatus.UNDER_PREPARATION,

            self.TransactionType.MARK_NOT_APPLICABLE:
                SalesOrderVDRLDocument.DocumentStatus.NOT_APPLICABLE,

            self.TransactionType.CANCELLED:
                SalesOrderVDRLDocument.DocumentStatus.CANCELLED,
        }

        return status_map[self.transaction_type]

    def get_holder_after_event(self):
        customer_events = {
            self.TransactionType.INITIAL_SUBMISSION,
            self.TransactionType.RESUBMISSION,
        }

        completed_events = {
            self.TransactionType.FINAL_APPROVAL,
            self.TransactionType.MARK_NOT_APPLICABLE,
            self.TransactionType.CANCELLED,
        }

        if self.transaction_type in customer_events:
            return self.HolderType.CUSTOMER

        if self.transaction_type in completed_events:
            return self.HolderType.COMPLETED

        if self.transaction_type == self.TransactionType.ON_HOLD:
            return self.HolderType.ON_HOLD

        return self.HolderType.INTERNAL

    def clean(self):
        errors = {}

        if self.document_id and self._state.adding:
            latest_transaction = (
                DocumentTransaction.objects
                .filter(document_id=self.document_id)
                .order_by(
                    "-transaction_at",
                    "-id",
                )
                .first()
            )

            if (
                latest_transaction
                and self.transaction_at
                < latest_transaction.transaction_at
            ):
                errors["transaction_at"] = (
                    "The new transaction cannot be earlier than "
                    "the latest existing transaction."
                )

            if (
                self.transaction_type
                == self.TransactionType.INITIAL_SUBMISSION
            ):
                initial_submission_exists = (
                    DocumentTransaction.objects
                    .filter(
                        document_id=self.document_id,
                        transaction_type=(
                            self.TransactionType.INITIAL_SUBMISSION
                        ),
                    )
                    .exists()
                )

                if initial_submission_exists:
                    errors["transaction_type"] = (
                        "Initial submission has already been recorded. "
                        "Use Resubmitted to Customer for the next cycle."
                    )

            if (
                self.transaction_type
                == self.TransactionType.RESUBMISSION
            ):
                submission_exists = (
                    DocumentTransaction.objects
                    .filter(
                        document_id=self.document_id,
                        transaction_type__in=[
                            self.TransactionType.INITIAL_SUBMISSION,
                            self.TransactionType.RESUBMISSION,
                        ],
                    )
                    .exists()
                )

                if not submission_exists:
                    errors["transaction_type"] = (
                        "An initial submission must be recorded before "
                        "a resubmission."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Create the transaction and update the current VDRL document state.
        Existing transaction records are not recalculated here.
        """

        if not self._state.adding:
            super().save(*args, **kwargs)
            return

        with transaction.atomic():
            document = (
                SalesOrderVDRLDocument.objects
                .select_for_update()
                .get(pk=self.document_id)
            )

            self.document = document

            previous_transaction = (
                DocumentTransaction.objects
                .filter(document=document)
                .order_by(
                    "transaction_at",
                    "id",
                )
                .last()
            )

            self.status_before = document.status
            self.status_after = self.get_status_after()
            self.holder_after_event = self.get_holder_after_event()

            if not self.revision.strip():
                self.revision = document.current_revision

            if previous_transaction:
                elapsed_seconds = max(
                    (
                        self.transaction_at
                        - previous_transaction.transaction_at
                    ).total_seconds(),
                    0,
                )

                elapsed_days = elapsed_seconds / 86400

                self.elapsed_calendar_days = Decimal(
                    str(round(elapsed_days, 2))
                )

                self.elapsed_holder_type = (
                    previous_transaction.holder_after_event
                )

                if (
                    previous_transaction.holder_after_event
                    == self.HolderType.INTERNAL
                ):
                    self.elapsed_responsible_person = (
                        previous_transaction
                        .responsible_person_after_event
                    )
            else:
                self.elapsed_calendar_days = Decimal("0.00")
                self.elapsed_holder_type = ""

            if (
                self.transaction_type
                == self.TransactionType.INITIAL_SUBMISSION
            ):
                self.cycle_number = 1

            elif (
                self.transaction_type
                == self.TransactionType.RESUBMISSION
            ):
                self.cycle_number = max(
                    document.current_cycle,
                    1,
                ) + 1

            else:
                self.cycle_number = document.current_cycle

            if (
                self.holder_after_event
                != self.HolderType.INTERNAL
            ):
                self.responsible_person_after_event = None

            self.full_clean()

            super().save(*args, **kwargs)

            document.status = self.status_after
            document.current_revision = self.revision
            document.current_action_since = self.transaction_at

            if (
                self.holder_after_event
                == self.HolderType.INTERNAL
            ):
                document.responsible_person = (
                    self.responsible_person_after_event
                )
            else:
                document.responsible_person = None

            if (
                self.transaction_type
                == self.TransactionType.INITIAL_SUBMISSION
            ):
                document.current_cycle = 1

                if not document.first_submission_at:
                    document.first_submission_at = (
                        self.transaction_at
                    )

                document.last_submission_at = (
                    self.transaction_at
                )

                document.customer_review_due_date = (
                    self.transaction_at.date()
                    + timedelta(
                        days=document.customer_review_days
                    )
                )

            elif (
                self.transaction_type
                == self.TransactionType.RESUBMISSION
            ):
                document.current_cycle = self.cycle_number

                document.last_submission_at = (
                    self.transaction_at
                )

                document.customer_review_due_date = (
                    self.transaction_at.date()
                    + timedelta(
                        days=document.customer_review_days
                    )
                )

            elif self.transaction_type in {
                self.TransactionType.RETURNED_WITH_COMMENTS,
                self.TransactionType.APPROVED_WITH_COMMENTS,
            }:
                document.last_customer_return_at = (
                    self.transaction_at
                )

                document.customer_review_due_date = None

            elif (
                self.transaction_type
                == self.TransactionType.FINAL_APPROVAL
            ):
                document.final_approval_at = (
                    self.transaction_at
                )

                document.customer_review_due_date = None

            elif self.transaction_type in {
                self.TransactionType.MARK_NOT_APPLICABLE,
                self.TransactionType.CANCELLED,
            }:
                document.customer_review_due_date = None

            document.save(
                update_fields=[
                    "status",
                    "current_revision",
                    "current_cycle",
                    "current_action_since",
                    "responsible_person",
                    "first_submission_at",
                    "last_submission_at",
                    "last_customer_return_at",
                    "final_approval_at",
                    "customer_review_due_date",
                    "updated_at",
                ]
            )

    def __str__(self):
        return (
            f"{self.document.vdrl.sales_order.sales_order_number} - "
            f"{self.document.document_title} - "
            f"{self.get_transaction_type_display()}"
        )
    
class DocumentFile(TimeStampedModel):
    """
    File register for every Sales Order VDRL document.

    The actual file is stored in the filesystem.
    This model stores the path and related metadata.
    """

    class FileType(models.TextChoices):
        WORKING = (
            "WORKING",
            "Internal Working File",
        )

        SUBMITTED = (
            "SUBMITTED",
            "Submitted to Customer",
        )

        CUSTOMER_RETURNED = (
            "CUSTOMER_RETURNED",
            "Customer Returned / Commented Copy",
        )

        CRS = (
            "CRS",
            "Comments Resolution Sheet",
        )

        APPROVED = (
            "APPROVED",
            "Approved Final File",
        )

        TRANSMITTAL = (
            "TRANSMITTAL",
            "Submission Transmittal",
        )

        SUPPORTING = (
            "SUPPORTING",
            "Supporting Document",
        )

        OTHER = (
            "OTHER",
            "Other",
        )

    document = models.ForeignKey(
        SalesOrderVDRLDocument,
        on_delete=models.CASCADE,
        related_name="files",
    )

    file_type = models.CharField(
        max_length=30,
        choices=FileType.choices,
    )

    revision = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Document revision applicable to this file."
        ),
    )

    cycle_number = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Submission cycle applicable to this file."
        ),
    )

    file = models.FileField(
        upload_to=vdrl_document_upload_path,
    )

    original_filename = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
    )

    description = models.TextField(
        blank=True,
    )

    uploaded_at = models.DateTimeField(
        default=timezone.now,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_vdrl_files",
    )

    is_current = models.BooleanField(
        default=True,
        help_text=(
            "Indicates the latest/current file for this file type."
        ),
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = [
            "document",
            "-uploaded_at",
            "-id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "document",
                    "file_type",
                    "is_current",
                ]
            ),
        ]

    def save(self, *args, **kwargs):
        if (
            self.file
            and not self.original_filename
        ):
            self.original_filename = Path(
                self.file.name
            ).name

        if not self.revision:
            self.revision = (
                self.document.current_revision
                or "0"
            )

        if not self.cycle_number:
            self.cycle_number = (
                self.document.current_cycle
            )

        super().save(
            *args,
            **kwargs,
        )

    @property
    def file_extension(self):
        if not self.original_filename:
            return ""

        return (
            Path(
                self.original_filename
            )
            .suffix
            .lower()
        )

    @property
    def file_size_mb(self):
        try:
            return round(
                self.file.size
                / 1024
                / 1024,
                2,
            )

        except (
            FileNotFoundError,
            OSError,
            ValueError,
        ):
            return 0

    def __str__(self):
        return (
            f"{self.document.document_title} - "
            f"{self.get_file_type_display()} - "
            f"Rev.{self.revision}"
        )
    
class CRSRegister(TimeStampedModel):
    """
    Header record for a Comments Resolution Sheet related
    to one VDRL document and one customer review cycle.
    """

    class Status(models.TextChoices):
        DRAFT = (
            "DRAFT",
            "Draft",
        )

        IN_PROGRESS = (
            "IN_PROGRESS",
            "In Progress",
        )

        INTERNAL_REVIEW = (
            "INTERNAL_REVIEW",
            "Internal Review",
        )

        READY_FOR_SUBMISSION = (
            "READY_FOR_SUBMISSION",
            "Ready for Submission",
        )

        SUBMITTED = (
            "SUBMITTED",
            "Submitted to Customer",
        )

        CUSTOMER_REVIEW = (
            "CUSTOMER_REVIEW",
            "Under Customer Review",
        )

        CLOSED = (
            "CLOSED",
            "Closed",
        )

        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )

    document = models.ForeignKey(
        SalesOrderVDRLDocument,
        on_delete=models.CASCADE,
        related_name="crs_registers",
    )

    source_return_transaction = models.ForeignKey(
        DocumentTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crs_registers",
        help_text=(
            "Customer-return transaction that initiated this CRS."
        ),
    )

    cycle_number = models.PositiveSmallIntegerField(
        default=1,
    )

    document_revision = models.CharField(
        max_length=20,
        blank=True,
    )

    crs_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Example: CRS-001",
    )

    expected_comment_count = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Number of comments received from the customer."
        ),
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    opened_at = models.DateTimeField(
        default=timezone.now,
    )

    target_completion_date = models.DateField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_crs_registers",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_crs_registers",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_crs_registers",
    )

    crs_file = models.ForeignKey(
        DocumentFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_crs_registers",
        help_text=(
            "Optional CRS file uploaded under the VDRL document."
        ),
    )

    remarks = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_crs_registers",
    )

    class Meta:
        ordering = [
            "document",
            "-cycle_number",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "document",
                    "cycle_number",
                ],
                name="unique_crs_cycle_per_vdrl_document",
            )
        ]

    def clean(self):
        errors = {}

        if (
            self.source_return_transaction_id
            and self.document_id
        ):
            if (
                self.source_return_transaction.document_id
                != self.document_id
            ):
                errors[
                    "source_return_transaction"
                ] = (
                    "The selected transaction does not belong "
                    "to this VDRL document."
                )

        if (
            self.crs_file_id
            and self.document_id
        ):
            if (
                self.crs_file.document_id
                != self.document_id
            ):
                errors["crs_file"] = (
                    "The selected CRS file does not belong "
                    "to this VDRL document."
                )

            elif (
                self.crs_file.file_type
                != DocumentFile.FileType.CRS
            ):
                errors["crs_file"] = (
                    "The selected file must have the file type "
                    "'Comments Resolution Sheet'."
                )

        if (
            self.target_completion_date
            and self.opened_at
            and self.target_completion_date
            < self.opened_at.date()
        ):
            errors["target_completion_date"] = (
                "Target completion date cannot be earlier "
                "than the CRS opening date."
            )

        if errors:
            raise ValidationError(errors)

    @property
    def total_comments(self):
        return self.comments.count()

    @property
    def open_comments(self):
        return self.comments.exclude(
            status=CRSComment.Status.CLOSED
        ).count()

    @property
    def closed_comments(self):
        return self.comments.filter(
            status=CRSComment.Status.CLOSED
        ).count()

    @property
    def overdue_comments(self):
        today = timezone.localdate()

        return (
            self.comments
            .exclude(
                status=CRSComment.Status.CLOSED
            )
            .filter(
                target_response_date__lt=today
            )
            .count()
        )

    @property
    def progress_percent(self):
        total = self.total_comments

        if total == 0:
            return 0

        return round(
            self.closed_comments
            * 100
            / total
        )

    @property
    def aging_days(self):
        end_time = (
            self.closed_at
            or timezone.now()
        )

        elapsed_seconds = (
            end_time
            - self.opened_at
        ).total_seconds()

        return Decimal(
            str(
                round(
                    max(
                        elapsed_seconds,
                        0,
                    )
                    / 86400,
                    2,
                )
            )
        )

    def save(
        self,
        *args,
        **kwargs,
    ):
        if (
            not self.document_revision
            and self.document_id
        ):
            self.document_revision = (
                self.document.current_revision
            )

        if (
            self.status
            == self.Status.CLOSED
        ):
            if not self.closed_at:
                self.closed_at = timezone.now()

        elif self.closed_at:
            self.closed_at = None

        super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        reference = (
            self.crs_reference
            or f"Cycle {self.cycle_number}"
        )

        return (
            f"{self.document.vdrl.sales_order.sales_order_number} - "
            f"{self.document.document_title} - "
            f"{reference}"
        )


class CRSComment(TimeStampedModel):
    """
    Individual customer comment tracked under a CRS register.
    """

    class Category(models.TextChoices):
        TECHNICAL = (
            "TECHNICAL",
            "Technical",
        )

        QUALITY = (
            "QUALITY",
            "Quality",
        )

        CONTRACTUAL = (
            "CONTRACTUAL",
            "Contractual",
        )

        COMMERCIAL = (
            "COMMERCIAL",
            "Commercial",
        )

        EDITORIAL = (
            "EDITORIAL",
            "Editorial",
        )

        OTHER = (
            "OTHER",
            "Other",
        )

    class Decision(models.TextChoices):
        PENDING = (
            "PENDING",
            "Pending Assessment",
        )

        ACCEPTED = (
            "ACCEPTED",
            "Accepted",
        )

        PARTIALLY_ACCEPTED = (
            "PARTIALLY_ACCEPTED",
            "Partially Accepted",
        )

        NOT_ACCEPTED = (
            "NOT_ACCEPTED",
            "Not Accepted",
        )

        CLARIFICATION_REQUIRED = (
            "CLARIFICATION_REQUIRED",
            "Clarification Required",
        )

    class DocumentUpdateStatus(models.TextChoices):
        NOT_APPLICABLE = (
            "NOT_APPLICABLE",
            "Not Applicable",
        )

        PENDING = (
            "PENDING",
            "Update Pending",
        )

        UPDATED = (
            "UPDATED",
            "Document Updated",
        )

    class Status(models.TextChoices):
        OPEN = (
            "OPEN",
            "Open",
        )

        UNDER_REVIEW = (
            "UNDER_REVIEW",
            "Under Review",
        )

        RESPONSE_PREPARED = (
            "RESPONSE_PREPARED",
            "Response Prepared",
        )

        INTERNAL_REVIEW = (
            "INTERNAL_REVIEW",
            "Internal Review",
        )

        READY_FOR_SUBMISSION = (
            "READY_FOR_SUBMISSION",
            "Ready for Submission",
        )

        CUSTOMER_REVIEW = (
            "CUSTOMER_REVIEW",
            "Under Customer Review",
        )

        CLOSED = (
            "CLOSED",
            "Closed",
        )

    class CustomerDisposition(models.TextChoices):
        PENDING = (
            "PENDING",
            "Pending",
        )

        ACCEPTED = (
            "ACCEPTED",
            "Accepted",
        )

        REPEATED = (
            "REPEATED",
            "Comment Repeated",
        )

        REJECTED = (
            "REJECTED",
            "Response Rejected",
        )

    crs = models.ForeignKey(
        CRSRegister,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    comment_number = models.CharField(
        max_length=50,
        help_text="Example: 1, 2, 3A, C-01",
    )

    page_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    clause_reference = models.CharField(
        max_length=150,
        blank=True,
    )

    customer_comment = models.TextField()

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.TECHNICAL,
    )

    assigned_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_crs_comments",
    )

    assigned_person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_crs_comments",
    )

    decision = models.CharField(
        max_length=30,
        choices=Decision.choices,
        default=Decision.PENDING,
    )

    supplier_response = models.TextField(
        blank=True,
    )

    internal_action_required = models.TextField(
        blank=True,
        help_text=(
            "Describe the document change or internal action required."
        ),
    )

    document_update_status = models.CharField(
        max_length=20,
        choices=DocumentUpdateStatus.choices,
        default=DocumentUpdateStatus.PENDING,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.OPEN,
    )

    customer_disposition = models.CharField(
        max_length=20,
        choices=CustomerDisposition.choices,
        default=CustomerDisposition.PENDING,
    )

    assigned_at = models.DateTimeField(
        default=timezone.now,
    )

    target_response_date = models.DateField(
        null=True,
        blank=True,
    )

    response_completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    remarks = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_crs_comments",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_crs_comments",
    )

    class Meta:
        ordering = [
            "crs",
            "comment_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "crs",
                    "comment_number",
                ],
                name="unique_comment_number_per_crs",
            )
        ]

    def clean(self):
        errors = {}

        if (
            self.target_response_date
            and self.assigned_at
            and self.target_response_date
            < self.assigned_at.date()
        ):
            errors["target_response_date"] = (
                "Target response date cannot be earlier "
                "than the assignment date."
            )

        if (
            self.decision
            == self.Decision.NOT_ACCEPTED
            and not self.supplier_response.strip()
        ):
            errors["supplier_response"] = (
                "A justification or supplier response is required "
                "when the customer comment is not accepted."
            )

        if errors:
            raise ValidationError(errors)

    def save(
        self,
        *args,
        **kwargs,
    ):
        if self.status == self.Status.CLOSED:
            if not self.closed_at:
                self.closed_at = timezone.now()

        elif self.closed_at:
            self.closed_at = None

        super().save(
            *args,
            **kwargs,
        )

    @property
    def aging_days(self):
        end_time = (
            self.closed_at
            or timezone.now()
        )

        elapsed_seconds = (
            end_time
            - self.assigned_at
        ).total_seconds()

        return Decimal(
            str(
                round(
                    max(
                        elapsed_seconds,
                        0,
                    )
                    / 86400,
                    2,
                )
            )
        )

    @property
    def is_overdue(self):
        if (
            self.status
            == self.Status.CLOSED
        ):
            return False

        if not self.target_response_date:
            return False

        return (
            self.target_response_date
            < timezone.localdate()
        )

    def __str__(self):
        return (
            f"{self.crs} - "
            f"Comment {self.comment_number}"
        )
    
class NotificationLog(TimeStampedModel):
    """
    Audit record for daily VDRL reminder emails.

    One digest is normally sent to one email address
    per day.
    """

    class DeliveryStatus(models.TextChoices):
        SENT = (
            "SENT",
            "Sent",
        )

        FAILED = (
            "FAILED",
            "Failed",
        )

        SKIPPED = (
            "SKIPPED",
            "Skipped",
        )

    DAILY_DIGEST = "DAILY_VDRL_DIGEST"

    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vdrl_notification_logs",
    )

    recipient_email = models.EmailField()

    notification_date = models.DateField(
        default=timezone.localdate,
    )

    digest_key = models.CharField(
        max_length=50,
        default=DAILY_DIGEST,
    )

    subject = models.CharField(
        max_length=250,
    )

    item_count = models.PositiveIntegerField(
        default=0,
    )

    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error_message = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = [
            "-notification_date",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "recipient_email",
                    "notification_date",
                    "digest_key",
                ],
                name=(
                    "unique_daily_vdrl_digest_per_recipient"
                ),
            )
        ]

    def __str__(self):
        return (
            f"{self.notification_date} - "
            f"{self.recipient_email} - "
            f"{self.delivery_status}"
        )
    
class AuditLog(models.Model):
    """
    Permanent audit record for VDRL application activity.
    """

    class Action(models.TextChoices):
        CREATE = (
            "CREATE",
            "Created",
        )

        UPDATE = (
            "UPDATE",
            "Updated",
        )

        DELETE = (
            "DELETE",
            "Deleted",
        )

        LOGIN = (
            "LOGIN",
            "Logged In",
        )

        LOGOUT = (
            "LOGOUT",
            "Logged Out",
        )

        VIEW = (
            "VIEW",
            "Viewed",
        )

        DOWNLOAD = (
            "DOWNLOAD",
            "Downloaded",
        )

        EXPORT = (
            "EXPORT",
            "Exported",
        )

        IMPORT = (
            "IMPORT",
            "Imported",
        )

        WORKFLOW = (
            "WORKFLOW",
            "Workflow Action",
        )

        SYSTEM = (
            "SYSTEM",
            "System Action",
        )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vdrl_audit_logs",
    )

    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )

    model_label = models.CharField(
        max_length=150,
        blank=True,
        db_index=True,
        help_text=(
            "Example: core.SalesOrderVDRLDocument"
        ),
    )

    object_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )

    object_repr = models.CharField(
        max_length=500,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Field-level old and new values."
        ),
    )

    event_data = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Additional data related to the event."
        ),
    )

    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    document = models.ForeignKey(
        SalesOrderVDRLDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    crs = models.ForeignKey(
        CRSRegister,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    request_method = models.CharField(
        max_length=10,
        blank=True,
    )

    request_path = models.CharField(
        max_length=500,
        blank=True,
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    user_agent = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        editable=False,
    )

    class Meta:
        ordering = [
            "-created_at",
            "-id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "actor",
                    "created_at",
                ],
                name="audit_actor_date_idx",
            ),

            models.Index(
                fields=[
                    "action",
                    "created_at",
                ],
                name="audit_action_date_idx",
            ),

            models.Index(
                fields=[
                    "model_label",
                    "object_id",
                ],
                name="audit_object_idx",
            ),
        ]

        permissions = [
            (
                "export_audit_log",
                "Can export VDRL audit log",
            ),
        ]

    def __str__(self):
        actor_name = (
            self.actor.get_full_name().strip()
            if self.actor
            else "System"
        )

        if not actor_name and self.actor:
            actor_name = self.actor.username

        return (
            f"{self.created_at:%Y-%m-%d %H:%M} - "
            f"{actor_name} - "
            f"{self.get_action_display()} - "
            f"{self.object_repr}"
        )
    
class InAppNotification(models.Model):
    """
    Notification displayed inside the VDRL application.
    """

    class Category(models.TextChoices):
        ASSIGNMENT = (
            "ASSIGNMENT",
            "Assignment",
        )

        WORKFLOW = (
            "WORKFLOW",
            "Workflow",
        )

        CRS = (
            "CRS",
            "CRS Comment",
        )

        DUE_DATE = (
            "DUE_DATE",
            "Due Date",
        )

        APPROVAL = (
            "APPROVAL",
            "Approval",
        )

        FILE = (
            "FILE",
            "Document File",
        )

        SYSTEM = (
            "SYSTEM",
            "System",
        )

    class Priority(models.TextChoices):
        LOW = (
            "LOW",
            "Low",
        )

        NORMAL = (
            "NORMAL",
            "Normal",
        )

        HIGH = (
            "HIGH",
            "High",
        )

        URGENT = (
            "URGENT",
            "Urgent",
        )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
    )

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    title = models.CharField(
        max_length=250,
    )

    message = models.TextField(
        blank=True,
    )

    url = models.CharField(
        max_length=500,
        blank=True,
    )

    is_read = models.BooleanField(
        default=False,
        db_index=True,
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    dedupe_key = models.CharField(
        max_length=250,
        blank=True,
        db_index=True,
        help_text=(
            "Used to prevent duplicate active notifications."
        ),
    )

    related_document = models.ForeignKey(
        SalesOrderVDRLDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="in_app_notifications",
    )

    related_crs_comment = models.ForeignKey(
        CRSComment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="in_app_notifications",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_in_app_notifications",
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
            "-id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "recipient",
                    "is_read",
                    "created_at",
                ],
                name="notification_unread_idx",
            ),
        ]

    def mark_as_read(self):
        if self.is_read:
            return

        self.is_read = True

        self.read_at = timezone.now()

        self.save(
            update_fields=[
                "is_read",
                "read_at",
            ]
        )

    def __str__(self):
        return (
            f"{self.recipient.username} - "
            f"{self.title}"
        )

class DocumentWorkflow(TimeStampedModel):
    class Status(models.TextChoices):
        WITH_DOCUMENT_CONTROLLER = (
            "WITH_DOCUMENT_CONTROLLER",
            "With Document Controller",
        )
        WITH_DEPARTMENT_MANAGER = (
            "WITH_DEPARTMENT_MANAGER",
            "With Department Manager",
        )
        WITH_CONTRIBUTOR = (
            "WITH_CONTRIBUTOR",
            "With Contributor",
        )
        AWAITING_APPLICATION_ENGINEER = (
            "AWAITING_APPLICATION_ENGINEER",
            "Awaiting Application Engineer",
        )
        CONTRIBUTOR_REVIEWING_RESPONSE = (
            "CONTRIBUTOR_REVIEWING_RESPONSE",
            "Contributor Reviewing AE Response",
        )
        SUBMITTED_FOR_DEPARTMENT_REVIEW = (
            "SUBMITTED_FOR_DEPARTMENT_REVIEW",
            "Submitted for Department Review",
        )
        RETURNED_FOR_REWORK = (
            "RETURNED_FOR_REWORK",
            "Returned for Rework",
        )
        READY_FOR_CUSTOMER_SUBMISSION = (
            "READY_FOR_CUSTOMER_SUBMISSION",
            "Ready for Customer Submission",
        )
        SUBMITTED_TO_CUSTOMER = (
            "SUBMITTED_TO_CUSTOMER",
            "Submitted to Customer",
        )
        CUSTOMER_RETURNED = (
            "CUSTOMER_RETURNED",
            "Customer Returned",
        )
        CUSTOMER_APPROVED = (
            "CUSTOMER_APPROVED",
            "Customer Approved",
        )
        ON_HOLD = (
            "ON_HOLD",
            "On Hold",
        )
        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )

    document = models.OneToOneField(
        SalesOrderVDRLDocument,
        on_delete=models.CASCADE,
        related_name="workflow",
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.WITH_DOCUMENT_CONTROLLER,
        db_index=True,
    )

    resume_status = models.CharField(
        max_length=50,
        choices=Status.choices,
        blank=True,
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_workflows",
    )

    contributor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributor_document_workflows",
    )

    planned_submission_date = models.DateField(
        null=True,
        blank=True,
    )

    department_assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_assigned_workflows",
    )

    department_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    contributor_assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contributor_assigned_workflows",
    )

    contributor_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_reassigned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    current_action_since = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "planned_submission_date",
            "document_id",
        ]

        permissions = [
            (
                "assign_document_department",
                "Can assign document department",
            ),
            (
                "assign_document_contributor",
                "Can assign document contributor",
            ),
            (
                "reassign_document_contributor",
                "Can reassign document contributor",
            ),
            (
                "raise_document_open_point",
                "Can raise document open point",
            ),
            (
                "respond_document_open_point",
                "Can respond to document open point",
            ),
            (
                "close_document_open_point",
                "Can close document open point",
            ),
            (
                "review_department_document",
                "Can review department document",
            ),
            (
                "record_customer_document_action",
                "Can record customer document action",
            ),
        ]

    @property
    def has_blocking_open_points(self):
        return self.open_points.filter(
            is_blocking=True,
        ).exclude(
            status__in=[
                DocumentOpenPoint.Status.CLOSED,
                DocumentOpenPoint.Status.CANCELLED,
            ],
        ).exists()

    @property
    def current_aging_seconds(self):
        return max(
            0,
            int(
                (
                    timezone.now()
                    - self.current_action_since
                ).total_seconds()
            ),
        )

    def __str__(self):
        return (
            f"{self.document} - "
            f"{self.get_status_display()}"
        )


class DocumentWorkflowTransaction(models.Model):
    class Action(models.TextChoices):
        DEPARTMENT_ASSIGNED = (
            "DEPARTMENT_ASSIGNED",
            "Department Assigned",
        )
        CONTRIBUTOR_ASSIGNED = (
            "CONTRIBUTOR_ASSIGNED",
            "Contributor Assigned",
        )
        CONTRIBUTOR_REASSIGNED = (
            "CONTRIBUTOR_REASSIGNED",
            "Contributor Reassigned",
        )
        OPEN_POINT_RAISED = (
            "OPEN_POINT_RAISED",
            "Open Point Raised",
        )
        OPEN_POINT_RESPONDED = (
            "OPEN_POINT_RESPONDED",
            "Open Point Responded",
        )
        OPEN_POINT_CLOSED = (
            "OPEN_POINT_CLOSED",
            "Open Point Closed",
        )
        SUBMITTED_FOR_REVIEW = (
            "SUBMITTED_FOR_REVIEW",
            "Submitted for Department Review",
        )
        RETURNED_FOR_REWORK = (
            "RETURNED_FOR_REWORK",
            "Returned for Rework",
        )
        INTERNALLY_APPROVED = (
            "INTERNALLY_APPROVED",
            "Internally Approved",
        )
        CUSTOMER_SUBMITTED = (
            "CUSTOMER_SUBMITTED",
            "Submitted to Customer",
        )
        CUSTOMER_RETURNED = (
            "CUSTOMER_RETURNED",
            "Customer Returned",
        )
        CUSTOMER_APPROVED = (
            "CUSTOMER_APPROVED",
            "Customer Approved",
        )

    workflow = models.ForeignKey(
        DocumentWorkflow,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    action = models.CharField(
        max_length=50,
        choices=Action.choices,
    )

    from_status = models.CharField(
        max_length=50,
        blank=True,
    )

    to_status = models.CharField(
        max_length=50,
        blank=True,
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_workflow_transactions",
    )

    comment = models.TextField(
        blank=True,
    )

    revision = models.CharField(
        max_length=50,
        blank=True,
    )

    elapsed_seconds = models.PositiveBigIntegerField(
        default=0,
        help_text=(
            "Time spent in the previous workflow status."
        ),
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
            "-id",
        ]

    def __str__(self):
        return (
            f"{self.workflow} - "
            f"{self.get_action_display()}"
        )


class DocumentAssignmentHistory(models.Model):
    class Action(models.TextChoices):
        DEPARTMENT_ASSIGNED = (
            "DEPARTMENT_ASSIGNED",
            "Department Assigned",
        )
        CONTRIBUTOR_ASSIGNED = (
            "CONTRIBUTOR_ASSIGNED",
            "Contributor Assigned",
        )
        CONTRIBUTOR_REASSIGNED = (
            "CONTRIBUTOR_REASSIGNED",
            "Contributor Reassigned",
        )

    workflow = models.ForeignKey(
        DocumentWorkflow,
        on_delete=models.CASCADE,
        related_name="assignment_history",
    )

    action = models.CharField(
        max_length=40,
        choices=Action.choices,
    )

    previous_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    new_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    previous_contributor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    new_contributor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    previous_planned_date = models.DateField(
        null=True,
        blank=True,
    )

    new_planned_date = models.DateField(
        null=True,
        blank=True,
    )

    reason = models.TextField(
        blank=True,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="document_assignment_actions",
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
            "-id",
        ]


class DocumentOpenPoint(models.Model):
    class Status(models.TextChoices):
        OPEN = (
            "OPEN",
            "Open — Awaiting Application Engineer",
        )
        RESPONDED = (
            "RESPONDED",
            "Responded — Awaiting Contributor Review",
        )
        MORE_INFORMATION_REQUIRED = (
            "MORE_INFORMATION_REQUIRED",
            "More Information Required",
        )
        CLOSED = (
            "CLOSED",
            "Closed",
        )
        CANCELLED = (
            "CANCELLED",
            "Cancelled",
        )

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    workflow = models.ForeignKey(
        DocumentWorkflow,
        on_delete=models.CASCADE,
        related_name="open_points",
    )

    reference_number = models.CharField(
        max_length=30,
    )

    subject = models.CharField(
        max_length=250,
    )

    description = models.TextField()

    status = models.CharField(
        max_length=40,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    is_blocking = models.BooleanField(
        default=True,
    )

    application_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="application_engineer_open_points",
    )

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="raised_document_open_points",
    )

    required_by = models.DateField(
        null=True,
        blank=True,
    )

    opened_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    first_response_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    latest_response_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_document_open_points",
    )

    closure_remark = models.TextField(
        blank=True,
    )

    response_cycle = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        ordering = [
            "status",
            "-opened_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "workflow",
                    "reference_number",
                ],
                name="unique_open_point_reference",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "application_engineer",
                    "status",
                ],
                name="openpoint_ae_status_idx",
            ),
            models.Index(
                fields=[
                    "workflow",
                    "status",
                ],
                name="openpoint_workflow_status_idx",
            ),
        ]

    @property
    def total_open_seconds(self):
        end_time = (
            self.closed_at
            or timezone.now()
        )

        return max(
            0,
            int(
                (
                    end_time
                    - self.opened_at
                ).total_seconds()
            ),
        )

    @property
    def first_response_seconds(self):
        if not self.first_response_at:
            return None

        return max(
            0,
            int(
                (
                    self.first_response_at
                    - self.opened_at
                ).total_seconds()
            ),
        )

    @property
    def contributor_verification_seconds(self):
        if (
            not self.closed_at
            or not self.latest_response_at
        ):
            return None

        return max(
            0,
            int(
                (
                    self.closed_at
                    - self.latest_response_at
                ).total_seconds()
            ),
        )

    @property
    def is_overdue(self):
        return bool(
            self.required_by
            and self.status not in [
                self.Status.CLOSED,
                self.Status.CANCELLED,
            ]
            and self.required_by < timezone.localdate()
        )

    def __str__(self):
        return (
            f"{self.reference_number} - "
            f"{self.subject}"
        )


class DocumentOpenPointTransaction(models.Model):
    class Action(models.TextChoices):
        RAISED = "RAISED", "Raised"
        RESPONDED = "RESPONDED", "Responded"
        MORE_INFORMATION_REQUIRED = (
            "MORE_INFORMATION_REQUIRED",
            "More Information Required",
        )
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"
        CONTRIBUTOR_REASSIGNED = (
            "CONTRIBUTOR_REASSIGNED",
            "Contributor Reassigned",
        )

    class ResponsibleParty(models.TextChoices):
        CONTRIBUTOR = (
            "CONTRIBUTOR",
            "Contributor",
        )
        APPLICATION_ENGINEER = (
            "APPLICATION_ENGINEER",
            "Application Engineer",
        )
        DEPARTMENT_MANAGER = (
            "DEPARTMENT_MANAGER",
            "Department Manager",
        )
        DOCUMENT_CONTROLLER = (
            "DOCUMENT_CONTROLLER",
            "Document Controller",
        )
        SYSTEM = (
            "SYSTEM",
            "System",
        )

    open_point = models.ForeignKey(
        DocumentOpenPoint,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    action = models.CharField(
        max_length=40,
        choices=Action.choices,
    )

    from_status = models.CharField(
        max_length=40,
        blank=True,
    )

    to_status = models.CharField(
        max_length=40,
        blank=True,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="open_point_transactions",
    )

    responsible_party = models.CharField(
        max_length=30,
        choices=ResponsibleParty.choices,
    )

    comment = models.TextField(
        blank=True,
    )

    attachment = models.FileField(
        upload_to="open_point_attachments/%Y/%m/",
        null=True,
        blank=True,
    )

    elapsed_since_previous_seconds = (
        models.PositiveBigIntegerField(
            default=0,
        )
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = [
            "created_at",
            "id",
        ]