from django.contrib.auth.decorators import (
    login_required,
)
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import (
    ProjectTeam,
    ProjectTeamMember,
)


def _user_label(user):
    return (
        user.get_full_name().strip()
        or user.username
    )


@login_required
def project_team_members(
    request,
    team_id,
):
    team = get_object_or_404(
        ProjectTeam.objects.select_related(
            "project_manager",
        ),
        pk=team_id,
        is_active=True,
    )

    memberships = (
        ProjectTeamMember.objects
        .filter(
            project_team=team,
            is_active=True,
            user__is_active=True,
        )
        .select_related(
            "user",
        )
        .order_by(
            "role",
            "user__first_name",
            "user__last_name",
            "user__username",
        )
    )

    application_engineers = []
    document_controllers = []

    for membership in memberships:
        item = {
            "id": membership.user_id,
            "name": _user_label(
                membership.user
            ),
        }

        if (
            membership.role
            == ProjectTeamMember
            .Role
            .APPLICATION_ENGINEER
        ):
            application_engineers.append(
                item
            )

        elif (
            membership.role
            == ProjectTeamMember
            .Role
            .DOCUMENT_CONTROLLER
        ):
            document_controllers.append(
                item
            )

    return JsonResponse(
        {
            "project_manager": {
                "id": team.project_manager_id,
                "name": _user_label(
                    team.project_manager
                ),
            },
            "application_engineers": (
                application_engineers
            ),
            "document_controllers": (
                document_controllers
            ),
        }
    )