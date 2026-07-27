from django.contrib import admin

from .models import (
    CalibrationAlert,
    CalibrationCycle,
    CalibrationLaboratory,
    Instrument,
    InstrumentCategory,
    InstrumentHistoryEvent,
)


@admin.register(InstrumentCategory)
class InstrumentCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(CalibrationLaboratory)
class CalibrationLaboratoryAdmin(admin.ModelAdmin):
    list_display = ("name", "accreditation_number", "accreditation_expiry", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "accreditation_number")


class CalibrationCycleInline(admin.TabularInline):
    model = CalibrationCycle
    extra = 0
    fields = ("cycle_number", "status", "laboratory", "calibration_date", "next_due_date", "result")
    readonly_fields = ("cycle_number",)
    show_change_link = True


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = (
        "asset_number",
        "description",
        "category",
        "department",
        "custodian",
        "latest_calibration_date",
        "next_due_date",
        "status",
    )
    list_filter = ("status", "category", "department", "is_active")
    search_fields = (
        "asset_number",
        "description",
        "purchase_serial_number",
        "manufacturer_serial_number",
    )
    inlines = [CalibrationCycleInline]


@admin.register(CalibrationCycle)
class CalibrationCycleAdmin(admin.ModelAdmin):
    list_display = (
        "instrument",
        "cycle_number",
        "status",
        "laboratory",
        "calibration_date",
        "next_due_date",
        "result",
        "verified_by",
    )
    list_filter = ("status", "result", "laboratory")
    search_fields = ("instrument__asset_number", "certificate_number")
    readonly_fields = ("cycle_number", "created_at", "updated_at")


@admin.register(InstrumentHistoryEvent)
class InstrumentHistoryEventAdmin(admin.ModelAdmin):
    list_display = ("instrument", "event_type", "event_date", "performed_by", "created_at")
    list_filter = ("event_type", "event_date")
    search_fields = ("instrument__asset_number", "remarks")
    readonly_fields = (
        "instrument",
        "calibration_cycle",
        "event_type",
        "event_date",
        "details",
        "remarks",
        "performed_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CalibrationAlert)
class CalibrationAlertAdmin(admin.ModelAdmin):
    list_display = ("instrument", "alert_type", "due_date", "assigned_to", "is_resolved", "created_at")
    list_filter = ("alert_type", "is_resolved")
    search_fields = ("instrument__asset_number", "message")
