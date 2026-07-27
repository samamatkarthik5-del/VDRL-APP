# Integrated VDRL + Send for TPI NOI + Calibration Modules

This package is designed to be copied into the existing `C:\VDRL_APP` Django project. It does not create duplicate Customer, Project, Sales Order, Department or User masters.

## What is included

- `operations_portal` — first page with three large application icons/cards.
  - VDRL
  - Send for TPI NOI
  - Calibration
- `itp` — ITP PDF/Excel import, annexure Excel import, clause-to-line mapping, sequential activity control, Hold Point blocking, NOI creation, completion confirmation and alerts.
- `calibration` — instrument/gauge master list, custodian and monitor, 15-day due control, external laboratory cycle, certificate verification, reusable/repaired/not-usable result, automatic history card and printable ISO/API master list.
- Module-level access control. Unauthorised cards remain visible but inactive, and direct URL access is blocked by middleware.

## Important before copying

Your existing VDRL application must first pass:

```bat
python manage.py check
```

The earlier error in `core\models.py` is independent of this package. Restore your last working `core\models.py` backup before installing these modules. Do not paste any ITP or Calibration code into `core\models.py`.

## 1. Copy folders

Extract this package. From its extracted folder, copy:

```text
operations_portal  -> C:\VDRL_APP\operations_portal
itp                -> C:\VDRL_APP\itp
calibration        -> C:\VDRL_APP\calibration
```

If an older `C:\VDRL_APP\itp` folder exists from the first attempt, rename it before copying:

```bat
cd /d C:\VDRL_APP
ren itp itp_old_backup
```

## 2. Install the additional libraries

```bat
cd /d C:\VDRL_APP
.venv\Scripts\activate
python -m pip install -r requirements-quality-modules.txt
```

Copy `requirements-quality-modules.txt` from this package into `C:\VDRL_APP` first.

## 3. Update settings

Open:

```text
C:\VDRL_APP\vdrl_project\settings.py
```

Copy the applicable lines from `integration\settings_snippet.py`.

The middleware must be placed after Django AuthenticationMiddleware so that `request.user` is available.

## 4. Update project URLs

Open:

```text
C:\VDRL_APP\vdrl_project\urls.py
```

Use `integration\project_urls_snippet.py` as the guide. The new root home route must be placed before the existing core routes. Do not delete your existing admin, accounts, media or VDRL URLs.

## 5. Create database migrations

```bat
python manage.py makemigrations operations_portal calibration itp
python manage.py migrate
python manage.py check
```

## 6. Grant application access

The superuser automatically sees all three active modules.

For normal users, open:

```text
/admin/operations_portal/usermoduleaccess/
```

Create one access record per user and tick the permitted modules.

Command-line example:

```bat
python manage.py grant_module_access Karthik --all --itp-all-sales-orders
```

Examples for limited users:

```bat
python manage.py grant_module_access Divya --vdrl --itp
python manage.py grant_module_access Sharfaraj --itp
python manage.py grant_module_access QCUser --calibration
```

`itp_all_sales_orders` should normally be given to QC managers who must manage inspection across all orders. Other ITP users are limited to Sales Orders where they are project manager, document controller, responsible VDRL person, or belong to the responsible department.

## 7. Add model permissions to users/groups

Module access activates the icon and URL. Django model permissions still control what the user can create or approve.

Recommended groups:

### VDRL Users
Keep the existing VDRL permissions.

### ITP / NOI Users
Typical permissions:

- View ITP document, clause, annexure, mapping and NOI
- Add ITP document and annexure
- Add Notice of Inspection
- Change activity execution

### ITP / NOI QC Managers
Additionally:

- `activate_itp`
- `activate_annexure`
- `release_hold_point`
- `override_hold_point`
- Change ITP clauses and mappings

### Calibration Users
Typical permissions:

- View instrument, calibration cycle and history
- Add/change instrument
- Add calibration cycle

### Calibration QC
Additionally:

- `verify_calibration_cycle`
- `release_calibrated_instrument`
- `print_calibration_master_list`

## 8. First-time master setup

In Django Admin create:

1. Instrument categories
2. Calibration laboratories
3. User module access records
4. Appropriate Django groups and permissions

The ITP module reuses the existing `core.SalesOrder`. The Calibration module reuses the existing `core.Department` and Django users.

## 9. Automated daily checks

Run these commands daily using Render Cron Jobs:

```text
python manage.py process_noi_followups
python manage.py process_calibration_alerts
```

The calibration command creates reminders 15 days before the due date and overdue alerts. The NOI command sends/creates next-day completion follow-up tasks and Hold Point alerts.

## Main URLs

```text
/                      Integrated three-icon home page
/work-bucket/          Existing VDRL page (configurable)
/itp/                  Send for TPI NOI
/calibration/          Calibration dashboard
/admin/                 Administration
```

## Access behaviour

- Logged-in users always reach the integrated first page.
- Authorised modules are active and clickable.
- Unauthorised modules are grey and inactive.
- Manually entering an unauthorised module URL returns HTTP 403.
- A superuser has access to all modules.
