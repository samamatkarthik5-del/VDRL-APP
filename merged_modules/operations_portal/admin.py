from django.contrib import admin

from .models import UserModuleAccess


@admin.register(UserModuleAccess)
class UserModuleAccessAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "is_active",
        "can_access_vdrl",
        "can_access_itp_noi",
        "can_access_calibration",
        "vdrl_all_sales_orders",
        "itp_all_sales_orders",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "can_access_vdrl",
        "can_access_itp_noi",
        "can_access_calibration",
    )
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    list_editable = (
        "is_active",
        "can_access_vdrl",
        "can_access_itp_noi",
        "can_access_calibration",
        "vdrl_all_sales_orders",
        "itp_all_sales_orders",
    )

    def save_model(self, request, obj, form, change):
        if not obj.granted_by_id:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)
