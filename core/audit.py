from datetime import (
    date,
    datetime,
)

from decimal import Decimal

from django.core.files import File

from django.db.models import Model

from .request_context import (
    get_current_request,
)


AUDIT_EXCLUDED_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "password",
    "last_login",
}


def serialize_audit_value(
    value,
):
    """
    Convert values into JSON-safe audit values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        Model,
    ):
        return {
            "id": value.pk,
            "text": str(
                value
            ),
        }

    if isinstance(
        value,
        File,
    ):
        return (
            value.name
            if value
            else ""
        )

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    return str(
        value
    )


def snapshot_instance(
    instance,
):
    """
    Capture the concrete database fields of a model.
    """

    snapshot = {}

    for field in (
        instance
        ._meta
        .concrete_fields
    ):
        if (
            field.name
            in AUDIT_EXCLUDED_FIELDS
        ):
            continue

        try:
            raw_value = getattr(
                instance,
                field.attname,
            )

        except (
            AttributeError,
            ValueError,
        ):
            continue

        snapshot[
            field.name
        ] = serialize_audit_value(
            raw_value
        )

    return snapshot


def compare_snapshots(
    old_snapshot,
    new_snapshot,
):
    """
    Return only fields that actually changed.
    """

    changes = {}

    all_fields = (
        set(
            old_snapshot
            or {}
        )
        |
        set(
            new_snapshot
            or {}
        )
    )

    for field_name in sorted(
        all_fields
    ):
        old_value = (
            old_snapshot
            .get(
                field_name
            )
            if old_snapshot
            else None
        )

        new_value = (
            new_snapshot
            .get(
                field_name
            )
            if new_snapshot
            else None
        )

        if old_value != new_value:
            changes[
                field_name
            ] = {
                "old": old_value,
                "new": new_value,
            }

    return changes


def get_client_ip(
    request,
):
    if not request:
        return None

    forwarded_for = (
        request.META.get(
            "HTTP_X_FORWARDED_FOR",
            "",
        )
    )

    if forwarded_for:
        return (
            forwarded_for
            .split(",")[0]
            .strip()
        )

    return request.META.get(
        "REMOTE_ADDR"
    )


def resolve_actor(
    instance=None,
    request=None,
    actor=None,
):
    if actor:
        return actor

    if (
        request
        and hasattr(
            request,
            "user",
        )
        and request.user.is_authenticated
    ):
        return request.user

    if instance is not None:
        for field_name in [
            "updated_by",
            "created_by",
            "uploaded_by",
            "performed_by",
            "prepared_by",
        ]:
            possible_actor = getattr(
                instance,
                field_name,
                None,
            )

            if possible_actor:
                return possible_actor

    return None


def resolve_related_records(
    instance,
):
    """
    Resolve the related Sales Order, VDRL Document
    and CRS record where possible.
    """

    from .models import (
        CRSComment,
        CRSRegister,
        DocumentFile,
        DocumentTransaction,
        SalesOrder,
        SalesOrderVDRL,
        SalesOrderVDRLDocument,
    )

    sales_order = None

    document = None

    crs = None

    if isinstance(
        instance,
        SalesOrder,
    ):
        sales_order = instance

    elif isinstance(
        instance,
        SalesOrderVDRL,
    ):
        sales_order = (
            instance.sales_order
        )

    elif isinstance(
        instance,
        SalesOrderVDRLDocument,
    ):
        document = instance

        sales_order = (
            instance
            .vdrl
            .sales_order
        )

    elif isinstance(
        instance,
        (
            DocumentTransaction,
            DocumentFile,
        ),
    ):
        document = (
            instance.document
        )

        sales_order = (
            document
            .vdrl
            .sales_order
        )

    elif isinstance(
        instance,
        CRSRegister,
    ):
        crs = instance

        document = (
            instance.document
        )

        sales_order = (
            document
            .vdrl
            .sales_order
        )

    elif isinstance(
        instance,
        CRSComment,
    ):
        crs = (
            instance.crs
        )

        document = (
            instance
            .crs
            .document
        )

        sales_order = (
            document
            .vdrl
            .sales_order
        )

    return (
        sales_order,
        document,
        crs,
    )


def record_audit_event(
    *,
    action,
    instance=None,
    actor=None,
    description="",
    changes=None,
    event_data=None,
    request=None,
    model_label="",
    object_id="",
    object_repr="",
):
    """
    Create one permanent AuditLog record.
    """

    from .models import (
        AuditLog,
    )

    if request is None:
        request = (
            get_current_request()
        )

    actor = resolve_actor(
        instance=instance,
        request=request,
        actor=actor,
    )

    sales_order = None

    document = None

    crs = None

    if instance is not None:
        try:
            (
                sales_order,
                document,
                crs,
            ) = resolve_related_records(
                instance
            )

        except Exception:
            sales_order = None

            document = None

            crs = None

        if not model_label:
            model_label = (
                instance
                ._meta
                .label
            )

        if not object_id:
            object_id = str(
                instance.pk
                if instance.pk is not None
                else ""
            )

        if not object_repr:
            try:
                object_repr = str(
                    instance
                )[:500]

            except Exception:
                object_repr = (
                    model_label
                )

    request_method = ""

    request_path = ""

    user_agent = ""

    ip_address = None

    if request is not None:
        request_method = (
            request.method
            or ""
        )

        request_path = (
            request.path
            or ""
        )[:500]

        user_agent = (
            request.META.get(
                "HTTP_USER_AGENT",
                "",
            )
        )[:2000]

        ip_address = get_client_ip(
            request
        )

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        model_label=model_label,
        object_id=object_id,
        object_repr=object_repr[:500],
        description=description,
        changes=(
            changes
            or {}
        ),
        event_data=(
            event_data
            or {}
        ),
        sales_order=sales_order,
        document=document,
        crs=crs,
        request_method=request_method,
        request_path=request_path,
        ip_address=ip_address,
        user_agent=user_agent,
    )