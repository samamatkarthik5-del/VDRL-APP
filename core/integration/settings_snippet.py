# Add these entries to vdrl_project/settings.py.
# Do not replace your existing INSTALLED_APPS or MIDDLEWARE lists.

INSTALLED_APPS += [
    "operations_portal.apps.OperationsPortalConfig",
    "itp.apps.ITPConfig",
    "calibration.apps.CalibrationConfig",
]

# Insert immediately AFTER django.contrib.auth.middleware.AuthenticationMiddleware.
# Example insertion code is shown below if you prefer not to edit the list manually.
AUTH_MIDDLEWARE = "django.contrib.auth.middleware.AuthenticationMiddleware"
MODULE_MIDDLEWARE = "operations_portal.middleware.ModuleAccessMiddleware"
if MODULE_MIDDLEWARE not in MIDDLEWARE:
    try:
        auth_index = MIDDLEWARE.index(AUTH_MIDDLEWARE)
        MIDDLEWARE.insert(auth_index + 1, MODULE_MIDDLEWARE)
    except ValueError:
        MIDDLEWARE.append(MODULE_MIDDLEWARE)

# Reuse existing VDRL master data. No duplicate Customer, Project, Sales Order or Department tables.
ITP_SALES_ORDER_MODEL = "core.SalesOrder"
CALIBRATION_DEPARTMENT_MODEL = "core.Department"

# Update only when your current VDRL landing path is different.
OPERATIONS_VDRL_URL = "/work-bucket/"

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Existing email settings will be used for future notification delivery.
ITP_ESCALATION_GROUPS = ["QC Manager", "Project Manager"]

"operations_portal.apps.OperationsPortalConfig"
"itp.apps.ITPConfig"
"calibration.apps.CalibrationConfig"
