from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import (
    Customer,
    CustomerVDRLTemplate,
    CustomerVDRLTemplateItem,
    CRSComment,
    CRSRegister,
    Department,
    DocumentCategory,
    DocumentFile,
    DocumentMaster,
    DocumentTransaction,
    EmployeeProfile,
    NotificationLog,
    Project,
    SalesOrder,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
    AuditLog,
    InAppNotification,
    DocumentAssignmentHistory,
    DocumentOpenPoint,
    DocumentOpenPointTransaction,
    DocumentWorkflow,
    DocumentWorkflowTransaction,
    ProjectTeam,
    ProjectTeamMember,
)
from .project_team_forms import (
    SalesOrderTeamForm,
)

admin.site.site_header = "VDRL Management System"
admin.site.site_title = "VDRL Administration"
admin.site.index_title = "VDRL Master Data Administration"


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "manager",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = (
        "code",
        "name",
        "manager__username",
        "manager__first_name",
        "manager__last_name",
    )
    ordering = ("name",)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "employee_name",
        "department",
        "job_title",
        "is_active",
    )
    list_filter = (
        "department",
        "is_active",
    )
    search_fields = (
        "employee_id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "job_title",
    )
    ordering = ("employee_id",)

    @admin.display(description="Employee Name")
    def employee_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_code",
        "name",
        "country",
        "standard_review_days",
        "is_active",
    )
    list_filter = (
        "country",
        "is_active",
    )
    search_fields = (
        "customer_code",
        "name",
        "contact_person",
        "contact_email",
    )
    ordering = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_code",
        "project_name",
        "customer",
        "location",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = (
        "customer",
        "is_active",
    )
    search_fields = (
        "project_code",
        "project_name",
        "customer_project_number",
        "customer__name",
        "customer__customer_code",
    )
    ordering = (
        "customer__name",
        "project_name",
    )


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = (
    "sales_order_number",
    "customer",
    "project",
    "project_manager",
    "approval_status",
    "document_controller",
    "is_active",
    "project_team",
    "application_engineer",
    )
    list_filter = (
        "status",
        "customer",
        "project",
        "project_manager",
        "document_controller",
        "is_active",
    )
    search_fields = (
        "sales_order_number",
        "customer_po_number",
        "customer__name",
        "customer__customer_code",
        "project__project_code",
        "project__project_name",
        "project_team",
        "approval_status",
        "is_active",
        )

    fieldsets = (
    (
        "Sales Order Details",
        {
            "fields": (
    "sales_order_number",
    "customer",
    "project",

    "project_team",
    "project_manager",
    "application_engineer",
    "document_controller",
    "backup_document_controllers",

    "order_date",
    "is_active",
    "authorized_users",
)
        },
    ),
    (
        "Approval Details",
        {
            "fields": (
                "approval_status",
                "submitted_for_approval_by",
                "submitted_for_approval_at",
                "sales_manager_approved_by",
                "sales_manager_approved_at",
                "sales_manager_approval_comment",
                "project_manager_approved_by",
                "project_manager_approved_at",
                "project_manager_approval_comment",
                "rejected_by",
                "rejected_at",
                "rejection_reason",
            ),
        },
    ),
)
    readonly_fields = (
    "submitted_for_approval_by",
    "submitted_for_approval_at",
    "sales_manager_approved_by",
    "sales_manager_approved_at",
    "project_manager_approved_by",
    "project_manager_approved_at",
    "rejected_by",
    "rejected_at",
)

    filter_horizontal = (
    "authorized_users",
    "backup_document_controllers",
)
    date_hierarchy = "order_date"
    ordering = ("-order_date",)
    form = SalesOrderTeamForm

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(
            request,
            obj,
            **kwargs,
        )

        class RequestAwareSalesOrderForm(base_form):
            def __init__(self, *args, **form_kwargs):
                form_kwargs["user"] = request.user
                super().__init__(*args, **form_kwargs)

        return RequestAwareSalesOrderForm
    
@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = (
        "code",
        "name",
        "description",
    )
    ordering = ("name",)


@admin.register(DocumentMaster)
class DocumentMasterAdmin(admin.ModelAdmin):
    list_display = (
        "internal_document_code",
        "document_title",
        "category",
        "default_responsible_department",
        "is_active",
    )
    list_filter = (
        "category",
        "default_responsible_department",
        "is_active",
    )
    search_fields = (
        "internal_document_code",
        "document_title",
        "description",
    )
    autocomplete_fields = (
        "category",
        "default_responsible_department",
    )
    ordering = (
        "category__name",
        "document_title",
    )


class CustomerVDRLTemplateItemInline(admin.TabularInline):
    model = CustomerVDRLTemplateItem
    extra = 1
    show_change_link = True

    autocomplete_fields = (
        "document",
        "responsible_department",
    )

    fields = (
        "sequence_number",
        "document",
        "customer_document_title",
        "requirement_type",
        "condition_description",
        "submission_stage",
        "due_date_basis",
        "day_offset",
        "customer_review_days",
        "responsible_department",
        "approval_required",
        "crs_required",
        "include_in_final_mrb",
        "required_file_format",
        "is_active",
    )

    ordering = ("sequence_number",)


@admin.register(CustomerVDRLTemplate)
class CustomerVDRLTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "template_code",
        "template_name",
        "customer",
        "revision",
        "effective_from",
        "effective_to",
        "is_default",
        "is_active",
        "document_count",
    )
    list_filter = (
        "customer",
        "is_default",
        "is_active",
        "effective_from",
    )
    search_fields = (
        "template_code",
        "template_name",
        "customer__name",
        "customer__customer_code",
        "description",
    )
    autocomplete_fields = ("customer",)
    date_hierarchy = "effective_from"
    ordering = (
        "customer__name",
        "template_name",
        "-effective_from",
    )
    inlines = (CustomerVDRLTemplateItemInline,)

    fieldsets = (
        (
            "Template Identification",
            {
                "fields": (
                    "customer",
                    "template_code",
                    "template_name",
                    "revision",
                )
            },
        ),
        (
            "Validity",
            {
                "fields": (
                    "effective_from",
                    "effective_to",
                    "is_default",
                    "is_active",
                )
            },
        ),
        (
            "Additional Information",
            {
                "fields": ("description",)
            },
        ),
    )

    @admin.display(description="Documents")
    def document_count(self, obj):
        return obj.items.filter(is_active=True).count()


@admin.register(CustomerVDRLTemplateItem)
class CustomerVDRLTemplateItemAdmin(admin.ModelAdmin):
    list_display = (
        "template",
        "sequence_number",
        "display_title",
        "requirement_type",
        "submission_stage",
        "due_date_basis",
        "day_offset",
        "responsible_department",
        "is_active",
    )
    list_filter = (
        "template__customer",
        "template",
        "requirement_type",
        "submission_stage",
        "responsible_department",
        "approval_required",
        "crs_required",
        "include_in_final_mrb",
        "is_active",
    )
    search_fields = (
        "template__template_code",
        "template__template_name",
        "document__internal_document_code",
        "document__document_title",
        "customer_document_title",
        "condition_description",
    )
    autocomplete_fields = (
        "template",
        "document",
        "responsible_department",
    )
    ordering = (
        "template",
        "sequence_number",
    )

    @admin.display(description="Document Title")
    def display_title(self, obj):
        return obj.display_document_title
    
class SalesOrderVDRLDocumentInline(admin.TabularInline):
    model = SalesOrderVDRLDocument
    extra = 0
    show_change_link = True

    fields = (
        "sequence_number",
        "customer_document_code",
        "document_title",
        "applicability_status",
        "planned_submission_date",
        "forecast_submission_date",
        "current_revision",
        "status",
        "responsible_department",
        "responsible_person",
    )

    readonly_fields = (
        "sequence_number",
        "document_title",
    )

    autocomplete_fields = (
        "responsible_department",
        "responsible_person",
    )

    ordering = (
        "sequence_number",
    )


@admin.action(
    description="Generate documents from selected VDRL template"
)
def generate_documents_from_template(
    modeladmin,
    request,
    queryset,
):
    total_created = 0
    processed_vdrls = 0

    for vdrl in queryset.select_related(
        "sales_order",
        "sales_order__customer",
        "source_template",
    ):
        if not vdrl.source_template:
            messages.warning(
                request,
                (
                    f"{vdrl}: No source template selected. "
                    "Generation skipped."
                ),
            )
            continue

        if (
            vdrl.source_template.customer_id
            != vdrl.sales_order.customer_id
        ):
            messages.error(
                request,
                (
                    f"{vdrl}: Template customer does not match "
                    "the Sales Order customer."
                ),
            )
            continue

        created_for_this_vdrl = 0

        with transaction.atomic():
            template_items = (
                vdrl.source_template.items
                .filter(is_active=True)
                .select_related(
                    "document",
                    "responsible_department",
                )
                .order_by("sequence_number")
            )

            for item in template_items:
                already_exists = (
                    SalesOrderVDRLDocument.objects.filter(
                        vdrl=vdrl,
                        source_template_item=item,
                    ).exists()
                )

                if already_exists:
                    continue

                if (
                    item.requirement_type
                    == CustomerVDRLTemplateItem.RequirementType.MANDATORY
                ):
                    applicability_status = (
                        SalesOrderVDRLDocument
                        .ApplicabilityStatus
                        .REQUIRED
                    )
                else:
                    applicability_status = (
                        SalesOrderVDRLDocument
                        .ApplicabilityStatus
                        .TO_CONFIRM
                    )

                review_days = item.customer_review_days

                if review_days is None:
                    review_days = (
                        vdrl.sales_order
                        .customer
                        .standard_review_days
                    )

                vdrl_document = SalesOrderVDRLDocument(
                    vdrl=vdrl,
                    source_template_item=item,
                    sequence_number=item.sequence_number,
                    document=item.document,
                    document_title=(
                        item.display_document_title
                    ),
                    requirement_type=(
                        item.requirement_type
                    ),
                    condition_description=(
                        item.condition_description
                    ),
                    applicability_status=(
                        applicability_status
                    ),
                    submission_stage=(
                        item.submission_stage
                    ),
                    due_date_basis=(
                        item.due_date_basis
                    ),
                    day_offset=(
                        item.day_offset
                    ),
                    customer_review_days=(
                        review_days
                    ),
                    responsible_department=(
                        item.responsible_department
                        or
                        item.document
                        .default_responsible_department
                    ),
                    approval_required=(
                        item.approval_required
                    ),
                    crs_required=(
                        item.crs_required
                    ),
                    include_in_final_mrb=(
                        item.include_in_final_mrb
                    ),
                    required_file_format=(
                        item.required_file_format
                    ),
                    remarks=(
                        item.remarks
                    ),
                )

                vdrl_document.planned_submission_date = (
                    vdrl_document
                    .calculate_planned_submission_date()
                )

                vdrl_document.save()

                created_for_this_vdrl += 1
                total_created += 1

            vdrl.generated_at = timezone.now()
            vdrl.generated_by = request.user

            if vdrl.status == SalesOrderVDRL.Status.DRAFT:
                vdrl.status = SalesOrderVDRL.Status.ACTIVE

            vdrl.save(
                update_fields=[
                    "generated_at",
                    "generated_by",
                    "status",
                    "updated_at",
                ]
            )

        processed_vdrls += 1

        messages.info(
            request,
            (
                f"{vdrl}: "
                f"{created_for_this_vdrl} document(s) added."
            ),
        )

    messages.success(
        request,
        (
            f"Generation completed. "
            f"{total_created} document(s) created "
            f"across {processed_vdrls} VDRL(s)."
        ),
    )


@admin.register(SalesOrderVDRL)
class SalesOrderVDRLAdmin(admin.ModelAdmin):
    list_display = (
        "vdrl_number",
        "sales_order",
        "source_template",
        "revision",
        "status",
        "is_current",
        "document_count",
        "generated_at",
    )

    list_filter = (
        "status",
        "is_current",
        "sales_order__customer",
        "source_template",
    )

    search_fields = (
        "vdrl_number",
        "sales_order__sales_order_number",
        "sales_order__customer__name",
        "title",
    )

    autocomplete_fields = (
        "sales_order",
        "source_template",
    )

    readonly_fields = (
        "generated_at",
        "generated_by",
    )

    inlines = (
        SalesOrderVDRLDocumentInline,
    )

    actions = (
        generate_documents_from_template,
    )

    @admin.display(description="Documents")
    def document_count(self, obj):
        return obj.documents.filter(
            is_active=True
        ).count()


@admin.action(
    description="Recalculate planned submission dates"
)
def recalculate_planned_submission_dates(
    modeladmin,
    request,
    queryset,
):
    updated_count = 0
    skipped_count = 0

    for document in queryset.select_related(
        "vdrl",
        "vdrl__sales_order",
    ):
        calculated_date = (
            document.calculate_planned_submission_date()
        )

        if calculated_date is None:
            skipped_count += 1
            continue

        document.planned_submission_date = calculated_date
        document.save()

        updated_count += 1

    messages.success(
        request,
        (
            f"{updated_count} planned date(s) recalculated. "
            f"{skipped_count} skipped because the required "
            "Sales Order milestone date was not available."
        ),
    )

class DocumentTransactionInline(admin.TabularInline):
    model = DocumentTransaction
    extra = 0
    can_delete = False

    fields = (
        "transaction_at",
        "transaction_type",
        "cycle_number",
        "revision",
        "status_before",
        "status_after",
        "holder_after_event",
        "responsible_person_after_event",
        "elapsed_calendar_days",
        "elapsed_holder_type",
        "elapsed_responsible_person",
    )

    readonly_fields = fields

    ordering = (
        "transaction_at",
        "id",
    )

    def has_add_permission(
        self,
        request,
        obj=None,
    ):
        return False

@admin.register(SalesOrderVDRLDocument)
class SalesOrderVDRLDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "sequence_number",
        "sales_order_number",
        "customer_document_code",
        "document_title",
        "current_cycle",
        "current_revision",
        "status",
        "current_holder_display",
        "current_aging_days_display",
        "total_internal_days_display",
        "total_customer_days_display",
        "responsible_department",
        "responsible_person",
    )

    list_filter = (
        "vdrl__sales_order__customer",
        "vdrl__sales_order",
        "requirement_type",
        "applicability_status",
        "status",
        "responsible_department",
        "approval_required",
        "crs_required",
        "is_active",
    )

    search_fields = (
        "vdrl__vdrl_number",
        "vdrl__sales_order__sales_order_number",
        "customer_document_code",
        "document_title",
        "document__internal_document_code",
    )

    autocomplete_fields = (
        "vdrl",
        "document",
        "responsible_department",
        "responsible_person",
    )

    actions = (
        recalculate_planned_submission_dates,
    )

    inlines = (
        DocumentTransactionInline,
    )

    ordering = (
        "vdrl",
        "sequence_number",
    )

    list_select_related = (
        "vdrl",
        "vdrl__sales_order",
        "responsible_department",
        "responsible_person",
    )

    @admin.display(
        description="Sales Order"
    )
    def sales_order_number(self, obj):
        return (
            obj.vdrl
            .sales_order
            .sales_order_number
        )

    @admin.display(
        description="Current Holder"
    )
    def current_holder_display(self, obj):
        return obj.current_holder

    @admin.display(
        description="Current Aging"
    )
    def current_aging_days_display(self, obj):
        return f"{obj.current_aging_days:.2f}"

    @admin.display(
        description="Internal Days"
    )
    def total_internal_days_display(self, obj):
        return f"{obj.total_internal_days:.2f}"

    @admin.display(
        description="Customer Days"
    )
    def total_customer_days_display(self, obj):
        return f"{obj.total_customer_days:.2f}"

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not obj.planned_submission_date:
            obj.planned_submission_date = (
                obj.calculate_planned_submission_date()
            )

        super().save_model(
            request,
            obj,
            form,
            change,
        )

@admin.register(DocumentTransaction)
class DocumentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_at",
        "sales_order_number",
        "document_title_display",
        "transaction_type",
        "cycle_number",
        "revision",
        "status_before",
        "status_after",
        "holder_after_event",
        "elapsed_calendar_days",
        "elapsed_holder_type",
        "elapsed_responsible_person",
    )

    list_filter = (
        "transaction_type",
        "holder_after_event",
        "elapsed_holder_type",
        "document__vdrl__sales_order__customer",
        "document__vdrl__sales_order",
        "document__responsible_department",
    )

    search_fields = (
        "document__vdrl__sales_order__sales_order_number",
        "document__customer_document_code",
        "document__document_title",
        "crs_reference",
        "remarks",
    )

    autocomplete_fields = (
        "document",
        "responsible_person_after_event",
    )

    date_hierarchy = "transaction_at"

    ordering = (
        "-transaction_at",
        "-id",
    )

    readonly_fields = (
        "cycle_number",
        "status_before",
        "status_after",
        "holder_after_event",
        "elapsed_calendar_days",
        "elapsed_holder_type",
        "elapsed_responsible_person",
        "created_by",
        "created_at",
        "updated_at",
    )

    @admin.display(
        description="Sales Order"
    )
    def sales_order_number(self, obj):
        return (
            obj.document
            .vdrl
            .sales_order
            .sales_order_number
        )

    @admin.display(
        description="Document"
    )
    def document_title_display(self, obj):
        return obj.document.document_title

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not obj.created_by_id:
            obj.created_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )

@admin.register(DocumentFile)
class DocumentFileAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "sales_order_number",
        "document_title_display",
        "file_type",
        "revision",
        "cycle_number",
        "uploaded_at",
        "uploaded_by",
        "is_current",
        "is_active",
    )

    list_filter = (
        "file_type",
        "is_current",
        "is_active",
        "document__vdrl__sales_order__customer",
        "document__vdrl__sales_order",
    )

    search_fields = (
        "original_filename",
        "document__document_title",
        "document__customer_document_code",
        "document__vdrl__sales_order__sales_order_number",
        "description",
    )

    autocomplete_fields = (
        "document",
        "uploaded_by",
    )

    readonly_fields = (
        "original_filename",
        "uploaded_at",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-uploaded_at",
    )

    @admin.display(
        description="Sales Order"
    )
    def sales_order_number(self, obj):
        return (
            obj.document
            .vdrl
            .sales_order
            .sales_order_number
        )

    @admin.display(
        description="Document"
    )
    def document_title_display(self, obj):
        return obj.document.document_title
    
class CRSCommentInline(admin.TabularInline):
    model = CRSComment

    extra = 0

    show_change_link = True

    fields = (
        "comment_number",
        "page_reference",
        "customer_comment",
        "assigned_department",
        "assigned_person",
        "decision",
        "status",
        "target_response_date",
        "customer_disposition",
    )

    autocomplete_fields = (
        "assigned_department",
        "assigned_person",
    )


@admin.register(CRSRegister)
class CRSRegisterAdmin(admin.ModelAdmin):
    list_display = (
        "crs_reference",
        "sales_order_number",
        "document_title_display",
        "cycle_number",
        "document_revision",
        "status",
        "expected_comment_count",
        "comment_count",
        "open_comment_count",
        "target_completion_date",
        "prepared_by",
    )

    list_filter = (
        "status",
        "document__vdrl__sales_order__customer",
        "document__vdrl__sales_order",
        "cycle_number",
    )

    search_fields = (
        "crs_reference",
        "document__document_title",
        "document__customer_document_code",
        "document__vdrl__sales_order__sales_order_number",
    )

    autocomplete_fields = (
        "document",
        "source_return_transaction",
        "prepared_by",
        "reviewed_by",
        "approved_by",
        "crs_file",
    )

    inlines = (
        CRSCommentInline,
    )

    @admin.display(
        description="Sales Order"
    )
    def sales_order_number(
        self,
        obj,
    ):
        return (
            obj.document
            .vdrl
            .sales_order
            .sales_order_number
        )

    @admin.display(
        description="Document"
    )
    def document_title_display(
        self,
        obj,
    ):
        return (
            obj.document
            .document_title
        )

    @admin.display(
        description="Comments"
    )
    def comment_count(
        self,
        obj,
    ):
        return obj.total_comments

    @admin.display(
        description="Open"
    )
    def open_comment_count(
        self,
        obj,
    ):
        return obj.open_comments


@admin.register(CRSComment)
class CRSCommentAdmin(admin.ModelAdmin):
    list_display = (
        "comment_number",
        "crs",
        "sales_order_number",
        "assigned_department",
        "assigned_person",
        "decision",
        "document_update_status",
        "status",
        "target_response_date",
        "aging_days_display",
        "customer_disposition",
    )

    list_filter = (
        "status",
        "decision",
        "document_update_status",
        "customer_disposition",
        "assigned_department",
        "assigned_person",
        "crs__document__vdrl__sales_order__customer",
    )

    search_fields = (
        "comment_number",
        "customer_comment",
        "supplier_response",
        "crs__crs_reference",
        "crs__document__document_title",
        "crs__document__vdrl__sales_order__sales_order_number",
    )

    autocomplete_fields = (
        "crs",
        "assigned_department",
        "assigned_person",
    )

    @admin.display(
        description="Sales Order"
    )
    def sales_order_number(
        self,
        obj,
    ):
        return (
            obj.crs
            .document
            .vdrl
            .sales_order
            .sales_order_number
        )

    @admin.display(
        description="Aging"
    )
    def aging_days_display(
        self,
        obj,
    ):
        return (
            f"{obj.aging_days:.2f}"
        )
    
@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "notification_date",
        "recipient_email",
        "recipient_user",
        "item_count",
        "delivery_status",
        "sent_at",
    )

    list_filter = (
        "delivery_status",
        "notification_date",
    )

    search_fields = (
        "recipient_email",
        "recipient_user__username",
        "recipient_user__first_name",
        "recipient_user__last_name",
        "subject",
    )

    readonly_fields = (
        "recipient_user",
        "recipient_email",
        "notification_date",
        "digest_key",
        "subject",
        "item_count",
        "delivery_status",
        "sent_at",
        "error_message",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-notification_date",
        "-created_at",
    )

    def has_add_permission(
        self,
        request,
    ):
        return False
    
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor",
        "action",
        "model_label",
        "object_repr",
        "sales_order",
        "ip_address",
    )

    list_filter = (
        "action",
        "model_label",
        "created_at",
        "actor",
    )

    search_fields = (
        "object_repr",
        "description",
        "model_label",
        "object_id",
        "sales_order__sales_order_number",
        "actor__username",
        "actor__first_name",
        "actor__last_name",
    )

    readonly_fields = (
        "actor",
        "action",
        "model_label",
        "object_id",
        "object_repr",
        "description",
        "changes",
        "event_data",
        "sales_order",
        "document",
        "crs",
        "request_method",
        "request_path",
        "ip_address",
        "user_agent",
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    def has_add_permission(
        self,
        request,
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return False


@admin.register(InAppNotification)
class InAppNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "recipient",
        "category",
        "priority",
        "title",
        "is_read",
        "read_at",
    )

    list_filter = (
        "category",
        "priority",
        "is_read",
        "created_at",
    )

    search_fields = (
        "recipient__username",
        "recipient__first_name",
        "recipient__last_name",
        "title",
        "message",
    )

    readonly_fields = (
        "created_at",
        "read_at",
    )

    autocomplete_fields = (
        "recipient",
        "created_by",
        "related_document",
        "related_crs_comment",
    )

@admin.register(DocumentWorkflow)
class DocumentWorkflowAdmin(
    admin.ModelAdmin
):
    list_display = (
        "document",
        "status",
        "department",
        "contributor",
        "planned_submission_date",
        "current_action_since",
    )

    list_filter = (
        "status",
        "department",
    )

    search_fields = (
        "document__vdrl__sales_order__sales_order_number",
        "contributor__username",
    )


@admin.register(DocumentOpenPoint)
class DocumentOpenPointAdmin(
    admin.ModelAdmin
):
    list_display = (
        "reference_number",
        "workflow",
        "subject",
        "status",
        "priority",
        "application_engineer",
        "opened_at",
        "closed_at",
    )

    list_filter = (
        "status",
        "priority",
        "is_blocking",
    )

    search_fields = (
        "reference_number",
        "subject",
        "workflow__document__vdrl__sales_order__sales_order_number",
    )


admin.site.register(
    DocumentWorkflowTransaction
)

admin.site.register(
    DocumentAssignmentHistory
)

admin.site.register(
    DocumentOpenPointTransaction
)

class ProjectTeamMemberInline(
    admin.TabularInline
):
    model = ProjectTeamMember

    extra = 1

    fields = (
        "user",
        "role",
        "is_active",
    )


@admin.register(ProjectTeam)
class ProjectTeamAdmin(
    admin.ModelAdmin
):
    list_display = (
        "team_code",
        "team_name",
        "project_manager",
        "active_member_count",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "team_code",
        "team_name",
        "project_manager__username",
        "project_manager__first_name",
        "project_manager__last_name",
    )

    inlines = [
        ProjectTeamMemberInline,
    ]

    @admin.display(
        description="Active Members"
    )
    def active_member_count(
        self,
        obj,
    ):
        return obj.members.filter(
            is_active=True,
        ).count()