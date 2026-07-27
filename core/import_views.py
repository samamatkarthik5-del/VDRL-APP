from io import BytesIO

from django.contrib import messages

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)

from django.core.exceptions import (
    PermissionDenied,
)

from django.http import (
    HttpResponse,
)

from django.shortcuts import (
    render,
)


from .access import (
    filter_documents_for_user,
    filter_sales_orders_for_user,
    user_has_global_vdrl_access,
)


from .forms import (
    CRSCommentExcelImportForm,
    CustomerTemplateExcelImportForm,
    SalesOrderVDRLExcelImportForm,
)


from .import_services import (
    IMPORT_CRS_COMMENTS,
    IMPORT_CUSTOMER_TEMPLATE,
    IMPORT_SALES_ORDER_VDRL,
    build_import_template,
    import_crs_comments,
    import_customer_template_items,
    import_sales_order_vdrl_documents,
)


from .models import (
    CRSRegister,
    CustomerVDRLTemplate,
    SalesOrder,
    SalesOrderVDRL,
    SalesOrderVDRLDocument,
)


@login_required
@permission_required(
    "core.bulk_import_vdrl_data",
    raise_exception=True,
)
def import_center(
    request,
):
    context = {
        "can_import_customer_templates": (
            user_has_global_vdrl_access(
                request.user
            )
        ),

        "can_import_sales_order_vdrl": (
            request.user.has_perm(
                (
                    "core."
                    "manage_vdrl_"
                    "document_details"
                )
            )
        ),

        "can_import_crs": (
            request.user.has_perm(
                "core.manage_crs"
            )
        ),
    }

    return render(
        request,
        "core/import_center.html",
        context,
    )


@login_required
@permission_required(
    "core.bulk_import_vdrl_data",
    raise_exception=True,
)
def import_customer_template(
    request,
):
    if not user_has_global_vdrl_access(
        request.user
    ):
        raise PermissionDenied

    template_queryset = (
        CustomerVDRLTemplate
        .objects
        .filter(
            is_active=True
        )
        .select_related(
            "customer"
        )
        .order_by(
            "customer__name",
            "template_name",
        )
    )

    result = None

    if request.method == "POST":
        form = (
            CustomerTemplateExcelImportForm(
                request.POST,
                request.FILES,
                template_queryset=(
                    template_queryset
                ),
            )
        )

        if form.is_valid():
            result = (
                import_customer_template_items(
                    uploaded_file=(
                        form
                        .cleaned_data[
                            "excel_file"
                        ]
                    ),

                    template=(
                        form
                        .cleaned_data[
                            "template"
                        ]
                    ),

                    import_mode=(
                        form
                        .cleaned_data[
                            "import_mode"
                        ]
                    ),

                    dry_run=(
                        form
                        .cleaned_data[
                            "dry_run"
                        ]
                    ),
                )
            )

            if (
                result["success"]
                and not result["dry_run"]
            ):
                messages.success(
                    request,
                    (
                        "Customer VDRL "
                        "Template import "
                        "completed successfully."
                    ),
                )

    else:
        form = (
            CustomerTemplateExcelImportForm(
                template_queryset=(
                    template_queryset
                )
            )
        )

    context = {
        "page_title": (
            "Import Customer VDRL Template"
        ),

        "description": (
            "Bulk create or update document "
            "requirements in a Customer VDRL "
            "Template."
        ),

        "form": form,

        "result": result,

        "template_type": (
            IMPORT_CUSTOMER_TEMPLATE
        ),
    }

    return render(
        request,
        "core/excel_import.html",
        context,
    )


@login_required
@permission_required(
    "core.bulk_import_vdrl_data",
    raise_exception=True,
)
def import_sales_order_vdrl(
    request,
):
    if not request.user.has_perm(
        (
            "core."
            "manage_vdrl_"
            "document_details"
        )
    ):
        raise PermissionDenied

    sales_orders = (
        filter_sales_orders_for_user(
            request.user,
            (
                SalesOrder
                .objects
                .filter(
                    is_active=True
                )
            ),
        )
    )

    vdrl_queryset = (
        SalesOrderVDRL
        .objects
        .filter(
            sales_order__in=(
                sales_orders
            ),
            is_current=True,
        )
        .select_related(
            "sales_order",
            "sales_order__customer",
        )
        .order_by(
            (
                "sales_order__"
                "sales_order_number"
            )
        )
    )

    result = None

    if request.method == "POST":
        form = (
            SalesOrderVDRLExcelImportForm(
                request.POST,
                request.FILES,
                vdrl_queryset=(
                    vdrl_queryset
                ),
            )
        )

        if form.is_valid():
            result = (
                import_sales_order_vdrl_documents(
                    uploaded_file=(
                        form
                        .cleaned_data[
                            "excel_file"
                        ]
                    ),

                    vdrl=(
                        form
                        .cleaned_data[
                            "vdrl"
                        ]
                    ),

                    import_mode=(
                        form
                        .cleaned_data[
                            "import_mode"
                        ]
                    ),

                    dry_run=(
                        form
                        .cleaned_data[
                            "dry_run"
                        ]
                    ),
                )
            )

            if (
                result["success"]
                and not result["dry_run"]
            ):
                messages.success(
                    request,
                    (
                        "Sales Order VDRL "
                        "import completed "
                        "successfully."
                    ),
                )

    else:
        form = (
            SalesOrderVDRLExcelImportForm(
                vdrl_queryset=(
                    vdrl_queryset
                )
            )
        )

    context = {
        "page_title": (
            "Import Sales Order VDRL"
        ),

        "description": (
            "Bulk create or update the "
            "document rows of an actual "
            "Sales Order VDRL."
        ),

        "form": form,

        "result": result,

        "template_type": (
            IMPORT_SALES_ORDER_VDRL
        ),
    }

    return render(
        request,
        "core/excel_import.html",
        context,
    )


@login_required
@permission_required(
    "core.bulk_import_vdrl_data",
    raise_exception=True,
)
def import_crs_comment_rows(
    request,
):
    if not request.user.has_perm(
        "core.manage_crs"
    ):
        raise PermissionDenied

    accessible_documents = (
        filter_documents_for_user(
            request.user,
            (
                SalesOrderVDRLDocument
                .objects
                .filter(
                    is_active=True,
                    vdrl__is_current=True,
                )
            ),
        )
    )

    crs_queryset = (
        CRSRegister
        .objects
        .filter(
            document__in=(
                accessible_documents
            )
        )
        .select_related(
            "document",
            "document__vdrl",
            (
                "document__vdrl__"
                "sales_order"
            ),
        )
        .order_by(
            (
                "document__vdrl__"
                "sales_order__"
                "sales_order_number"
            ),
            "-cycle_number",
        )
    )

    result = None

    if request.method == "POST":
        form = (
            CRSCommentExcelImportForm(
                request.POST,
                request.FILES,
                crs_queryset=(
                    crs_queryset
                ),
            )
        )

        if form.is_valid():
            result = (
                import_crs_comments(
                    uploaded_file=(
                        form
                        .cleaned_data[
                            "excel_file"
                        ]
                    ),

                    crs=(
                        form
                        .cleaned_data[
                            "crs"
                        ]
                    ),

                    import_mode=(
                        form
                        .cleaned_data[
                            "import_mode"
                        ]
                    ),

                    imported_by=(
                        request.user
                    ),

                    dry_run=(
                        form
                        .cleaned_data[
                            "dry_run"
                        ]
                    ),
                )
            )

            if (
                result["success"]
                and not result["dry_run"]
            ):
                messages.success(
                    request,
                    (
                        "CRS Comment import "
                        "completed successfully."
                    ),
                )

    else:
        form = (
            CRSCommentExcelImportForm(
                crs_queryset=(
                    crs_queryset
                )
            )
        )

    context = {
        "page_title": (
            "Import CRS Comments"
        ),

        "description": (
            "Bulk create or update "
            "individual customer comments "
            "under a CRS Register."
        ),

        "form": form,

        "result": result,

        "template_type": (
            IMPORT_CRS_COMMENTS
        ),
    }

    return render(
        request,
        "core/excel_import.html",
        context,
    )


@login_required
@permission_required(
    "core.bulk_import_vdrl_data",
    raise_exception=True,
)
def download_excel_import_template(
    request,
    import_type,
):
    valid_types = {
        IMPORT_CUSTOMER_TEMPLATE,
        IMPORT_SALES_ORDER_VDRL,
        IMPORT_CRS_COMMENTS,
    }

    if (
        import_type
        not in valid_types
    ):
        raise PermissionDenied

    if (
        import_type
        == IMPORT_CUSTOMER_TEMPLATE
        and not user_has_global_vdrl_access(
            request.user
        )
    ):
        raise PermissionDenied

    workbook = (
        build_import_template(
            import_type
        )
    )

    output = BytesIO()

    workbook.save(
        output
    )

    workbook.close()

    output.seek(
        0
    )

    file_names = {
        IMPORT_CUSTOMER_TEMPLATE: (
            "Customer_VDRL_Template_"
            "Import.xlsx"
        ),

        IMPORT_SALES_ORDER_VDRL: (
            "Sales_Order_VDRL_"
            "Import.xlsx"
        ),

        IMPORT_CRS_COMMENTS: (
            "CRS_Comments_"
            "Import.xlsx"
        ),
    }

    response = HttpResponse(
        output.getvalue(),

        content_type=(
            "application/"
            "vnd.openxmlformats-"
            "officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response[
        "Content-Disposition"
    ] = (
        "attachment; "
        f'filename="'
        f'{file_names[import_type]}'
        '"'
    )

    return response