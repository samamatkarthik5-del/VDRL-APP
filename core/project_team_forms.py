from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import (
    ProjectTeam,
    ProjectTeamMember,
    SalesOrder,
)


User = get_user_model()


class SalesOrderTeamForm(forms.ModelForm):
    backup_document_controllers = (
        forms.ModelMultipleChoiceField(
            queryset=User.objects.none(),
            required=False,
            widget=forms.SelectMultiple(
                attrs={
                    "size": 6,
                }
            ),
        )
    )

    class Meta:
        model = SalesOrder

        fields = [
            "sales_order_number",
            "customer",
            "project",
            "project_team",
            "application_engineer",
            "project_manager",
            "document_controller",
            "backup_document_controllers",
            "order_date",
            "is_active",
            "authorized_users",
            "sales_manager",
        ]

        widgets = {
            "order_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.current_user = user
        self.fields[
    "sales_manager"
].queryset = (
    User.objects
    .filter(
        is_active=True,
        groups__name__iexact=(
            "SALES MANAGER"
        ),
    )
    .distinct()
    .order_by(
        "first_name",
        "last_name",
        "username",
    )
)

        self.fields[
            "project_team"
        ].queryset = (
            ProjectTeam.objects
            .filter(
                is_active=True,
            )
            .select_related(
                "project_manager",
            )
            .order_by(
                "team_code",
            )
        )

        self.fields[
            "application_engineer"
        ].queryset = User.objects.none()

        self.fields[
            "document_controller"
        ].queryset = User.objects.none()

        self.fields[
            "backup_document_controllers"
        ].queryset = User.objects.none()

        self.fields[
            "project_manager"
        ].queryset = User.objects.filter(
            is_active=True,
        )

        self.fields[
            "project_manager"
        ].disabled = True

        team_id = self._get_selected_team_id()

        if team_id:
            self._set_team_member_querysets(
                team_id
            )

        self._restrict_team_for_application_engineer()

        url_template = reverse(
            "core:project_team_members",
            args=[999999],
        ).replace(
            "999999",
            "__team_id__",
        )

        self.fields[
            "project_team"
        ].widget.attrs[
            "data-members-url-template"
        ] = url_template

    def _get_selected_team_id(self):
        if self.is_bound:
            return self.data.get(
                self.add_prefix(
                    "project_team"
                )
            )

        if (
            self.instance
            and self.instance.pk
        ):
            return (
                self.instance.project_team_id
            )

        if (
            self.current_user
            and self.current_user.is_authenticated
        ):
            membership = (
                ProjectTeamMember.objects
                .filter(
                    user=self.current_user,
                    role=(
                        ProjectTeamMember
                        .Role
                        .APPLICATION_ENGINEER
                    ),
                    is_active=True,
                    project_team__is_active=True,
                )
                .first()
            )

            if membership:
                return membership.project_team_id

        return None

    def _set_team_member_querysets(
        self,
        team_id,
    ):
        try:
            team_id = int(team_id)
        except (
            TypeError,
            ValueError,
        ):
            return

        team = (
            ProjectTeam.objects
            .filter(
                pk=team_id,
                is_active=True,
            )
            .select_related(
                "project_manager",
            )
            .first()
        )

        if not team:
            return

        ae_user_ids = (
            ProjectTeamMember.objects
            .filter(
                project_team=team,
                role=(
                    ProjectTeamMember
                    .Role
                    .APPLICATION_ENGINEER
                ),
                is_active=True,
                user__is_active=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        dc_user_ids = (
            ProjectTeamMember.objects
            .filter(
                project_team=team,
                role=(
                    ProjectTeamMember
                    .Role
                    .DOCUMENT_CONTROLLER
                ),
                is_active=True,
                user__is_active=True,
            )
            .values_list(
                "user_id",
                flat=True,
            )
        )

        self.fields[
            "application_engineer"
        ].queryset = (
            User.objects
            .filter(
                pk__in=ae_user_ids,
            )
            .order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

        document_controllers = (
            User.objects
            .filter(
                pk__in=dc_user_ids,
            )
            .order_by(
                "first_name",
                "last_name",
                "username",
            )
        )

        self.fields[
            "document_controller"
        ].queryset = document_controllers

        self.fields[
            "backup_document_controllers"
        ].queryset = document_controllers

        self.fields[
            "project_manager"
        ].initial = team.project_manager

    def _restrict_team_for_application_engineer(
        self,
    ):
        user = self.current_user

        if (
            not user
            or not user.is_authenticated
            or user.is_superuser
            or user.has_perm(
                "core.view_all_vdrl_data"
            )
        ):
            return

        ae_memberships = (
            ProjectTeamMember.objects
            .filter(
                user=user,
                role=(
                    ProjectTeamMember
                    .Role
                    .APPLICATION_ENGINEER
                ),
                is_active=True,
                project_team__is_active=True,
            )
        )

        if ae_memberships.exists():
            team_ids = (
                ae_memberships.values_list(
                    "project_team_id",
                    flat=True,
                )
            )

            self.fields[
                "project_team"
            ].queryset = (
                self.fields[
                    "project_team"
                ]
                .queryset
                .filter(
                    pk__in=team_ids,
                )
            )

            if not self.instance.pk:
                self.fields[
                    "application_engineer"
                ].initial = user

    def clean(self):
        cleaned_data = super().clean()

        team = cleaned_data.get(
            "project_team"
        )

        application_engineer = (
            cleaned_data.get(
                "application_engineer"
            )
        )

        document_controller = (
            cleaned_data.get(
                "document_controller"
            )
        )

        backup_controllers = (
            cleaned_data.get(
                "backup_document_controllers"
            )
        )

        if not team:
            return cleaned_data

        self.instance.project_manager = (
            team.project_manager
        )

        if application_engineer:
            valid_ae = (
                ProjectTeamMember.objects
                .filter(
                    project_team=team,
                    user=application_engineer,
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
                self.add_error(
                    "application_engineer",
                    (
                        "Select an Application Engineer "
                        "from the selected Project Team."
                    ),
                )

        if document_controller:
            valid_dc = (
                ProjectTeamMember.objects
                .filter(
                    project_team=team,
                    user=document_controller,
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
                self.add_error(
                    "document_controller",
                    (
                        "Select a Document Controller "
                        "from the selected Project Team."
                    ),
                )

        for backup_controller in (
            backup_controllers or []
        ):
            valid_backup = (
                ProjectTeamMember.objects
                .filter(
                    project_team=team,
                    user=backup_controller,
                    role=(
                        ProjectTeamMember
                        .Role
                        .DOCUMENT_CONTROLLER
                    ),
                    is_active=True,
                )
                .exists()
            )

            if not valid_backup:
                self.add_error(
                    "backup_document_controllers",
                    (
                        f"{backup_controller} does not "
                        f"belong to {team}."
                    ),
                )

        if (
            document_controller
            and backup_controllers
            and document_controller
            in backup_controllers
        ):
            self.add_error(
                "backup_document_controllers",
                (
                    "The primary Document Controller "
                    "cannot also be selected as backup."
                ),
            )

        return cleaned_data

    class Media:
        js = (
            "core/js/sales_order_team.js",
        )