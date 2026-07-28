from django.contrib import admin

from .models import (
    AuditLog,
    ImportIssue,
    ITPActivityExecution,
    ITPAnnexure,
    ITPAnnexureLine,
    ITPClause,
    ITPClauseDependency,
    ITPClauseIntervention,
    ITPComment,
    ITPDocument,
    ITPLineClauseMapping,
    ITPStakeholder,
    NOICoverage,
    NOICompletionTask,
    NOINumberSequence,
    NoticeOfInspection,
    WorkflowAlert,
)


class InterventionInline(admin.TabularInline):
    model = ITPClauseIntervention
    extra = 0


class ClauseInline(admin.TabularInline):
    model = ITPClause
    fields = (
        "sequence_order",
        "clause_code",
        "activity",
        "inspection_extent",
        "is_hold_point",
        "hold_release_mode",
    )
    readonly_fields = ("is_hold_point",)
    extra = 0
    show_change_link = True


@admin.register(ITPDocument)
class ITPDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "revision",
        "sales_order",
        "source_format",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("status", "source_format", "created_at")
    search_fields = ("document_number", "revision", "title")
    inlines = [ClauseInline]


@admin.register(ITPClause)
class ITPClauseAdmin(admin.ModelAdmin):
    list_display = (
        "clause_code",
        "itp",
        "sequence_order",
        "activity_short",
        "is_hold_point",
        "hold_release_mode",
    )
    list_filter = ("itp", "is_hold_point", "hold_release_mode", "section_code")
    search_fields = ("clause_code", "activity", "reference_document", "acceptance_criteria")
    inlines = [InterventionInline]

    @admin.display(description="Activity")
    def activity_short(self, obj):
        return obj.activity[:100]


@admin.register(ITPStakeholder)
class ITPStakeholderAdmin(admin.ModelAdmin):
    list_display = ("name", "itp", "display_order")
    list_filter = ("itp",)


@admin.register(ITPClauseDependency)
class ITPClauseDependencyAdmin(admin.ModelAdmin):
    list_display = (
        "predecessor",
        "successor",
        "dependency_type",
        "mandatory",
        "blocking_if_predecessor_is_hold",
    )
    list_filter = ("mandatory", "dependency_type")


class AnnexureLineInline(admin.TabularInline):
    model = ITPAnnexureLine
    fields = (
        "row_number",
        "po_line_no",
        "quantity",
        "inspection_class",
        "nde_applicable",
        "tag_number",
        "service",
    )
    extra = 0
    show_change_link = True


@admin.register(ITPAnnexure)
class ITPAnnexureAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "revision",
        "sales_order",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("document_number", "revision", "title")
    inlines = [AnnexureLineInline]


@admin.register(ITPAnnexureLine)
class ITPAnnexureLineAdmin(admin.ModelAdmin):
    list_display = (
        "po_line_no",
        "annexure",
        "quantity",
        "inspection_class",
        "nde_applicable",
        "tag_number",
        "service",
    )
    list_filter = ("annexure", "inspection_class", "service", "is_active")
    search_fields = ("po_line_no", "description", "tag_number", "datasheet_number")


@admin.register(ITPLineClauseMapping)
class MappingAdmin(admin.ModelAdmin):
    list_display = (
        "clause",
        "annexure_line",
        "is_applicable",
        "review_status",
        "source",
        "required_quantity",
    )
    list_filter = ("review_status", "source", "is_applicable", "clause__itp")
    search_fields = (
        "clause__clause_code",
        "clause__activity",
        "annexure_line__po_line_no",
        "annexure_line__tag_number",
    )


class CoverageInline(admin.TabularInline):
    model = NOICoverage
    extra = 0
    show_change_link = True


@admin.register(NoticeOfInspection)
class NoticeOfInspectionAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "itp",
        "annexure",
        "scheduled_start",
        "scheduled_end",
        "responsible_user",
        "status",
        "completion_status",
    )
    list_filter = ("status", "completion_status", "scheduled_start")
    search_fields = ("number", "location")
    inlines = [CoverageInline]


@admin.register(ITPActivityExecution)
class ActivityExecutionAdmin(admin.ModelAdmin):
    list_display = (
        "mapping",
        "quantity",
        "status",
        "source",
        "completed_at",
        "released_at",
    )
    list_filter = ("status", "source", "mapping__clause__is_hold_point")
    search_fields = (
        "mapping__clause__clause_code",
        "mapping__annexure_line__po_line_no",
        "release_reference",
    )


@admin.register(WorkflowAlert)
class WorkflowAlertAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "severity",
        "alert_type",
        "assigned_to",
        "noi",
        "is_resolved",
        "created_at",
    )
    list_filter = ("severity", "alert_type", "is_resolved")
    search_fields = ("title", "message", "noi__number")


@admin.register(ImportIssue)
class ImportIssueAdmin(admin.ModelAdmin):
    list_display = ("severity", "source_location", "message_short", "is_resolved")
    list_filter = ("severity", "is_resolved")
    search_fields = ("message", "source_location")

    @admin.display(description="Message")
    def message_short(self, obj):
        return obj.message[:120]


admin.site.register(ITPClauseIntervention)
admin.site.register(NOICoverage)
admin.site.register(NOICompletionTask)
admin.site.register(NOINumberSequence)
admin.site.register(AuditLog)


@admin.register(ITPComment)
class ITPCommentAdmin(admin.ModelAdmin):
    list_display = ("content_object", "kind", "author", "created_at")
    list_filter = ("kind",)
    search_fields = ("body",)
