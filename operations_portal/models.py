from __future__ import annotations

from django.conf import settings
from django.db import models


class ModuleCode(models.TextChoices):
    VDRL = "VDRL", "VDRL"
    ITP_NOI = "ITP_NOI", "Send for TPI NOI"
    CALIBRATION = "CALIBRATION", "Calibration"


class UserModuleAccess(models.Model):
    """One clear access record per user for the three application modules."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="module_access",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Disable all module access for this user without deleting the record.",
    )
    can_access_vdrl = models.BooleanField(default=False)
    can_access_itp_noi = models.BooleanField(default=False)
    can_access_calibration = models.BooleanField(default=False)

    # Sales-order scope controls. Normal users remain limited to assignments.
    vdrl_all_sales_orders = models.BooleanField(default=False)
    itp_all_sales_orders = models.BooleanField(default=False)

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_module_access_records",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "User module access"
        verbose_name_plural = "User module access"

    def __str__(self) -> str:
        return f"Module access - {self.user.get_username()}"

    def has_module(self, module_code: str) -> bool:
        if not self.is_active:
            return False
        mapping = {
            ModuleCode.VDRL: self.can_access_vdrl,
            ModuleCode.ITP_NOI: self.can_access_itp_noi,
            ModuleCode.CALIBRATION: self.can_access_calibration,
        }
        return bool(mapping.get(module_code, False))
