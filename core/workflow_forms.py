from django import forms
from django.contrib.auth import (
    get_user_model,
)

from .models import (
    Department,
    DocumentOpenPoint,
    EmployeeProfile,
)


User = get_user_model()


class AssignDepartmentForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=(
            Department.objects.filter(
                is_active=True
            )
        ),
        label="Responsible Department",
    )

    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )


class AssignContributorForm(forms.Form):
    contributor = forms.ModelChoiceField(
        queryset=User.objects.none(),
    )

    planned_submission_date = forms.DateField(
        widget=forms.DateInput(
            attrs={
                "type": "date",
            }
        ),
    )

    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    def __init__(
        self,
        *args,
        department=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if department:
            self.fields[
                "contributor"
            ].queryset = (
                User.objects.filter(
                    is_active=True,
                    employee_profile__department=(
                        department
                    ),
                )
                .order_by(
                    "first_name",
                    "last_name",
                    "username",
                )
            )


class ReassignContributorForm(
    AssignContributorForm
):
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )

    comment = None


class RaiseOpenPointForm(forms.ModelForm):
    attachment = forms.FileField(
        required=False,
    )

    class Meta:
        model = DocumentOpenPoint

        fields = [
            "subject",
            "description",
            "priority",
            "required_by",
            "is_blocking",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                }
            ),

            "required_by": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


class OpenPointResponseForm(forms.Form):
    response = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 6,
            }
        ),
    )

    attachment = forms.FileField(
        required=False,
    )


class OpenPointDecisionForm(forms.Form):
    DECISIONS = [
        (
            "CLOSE",
            "Information is sufficient — Close",
        ),
        (
            "MORE_INFORMATION",
            "More information is required",
        ),
    ]

    decision = forms.ChoiceField(
        choices=DECISIONS,
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 5,
            }
        ),
    )


class WorkflowCommentForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            }
        ),
    )


class DepartmentReviewForm(forms.Form):
    DECISIONS = [
        (
            "APPROVE",
            "Approve for Customer Submission",
        ),
        (
            "RETURN",
            "Return to Contributor for Rework",
        ),
    ]

    decision = forms.ChoiceField(
        choices=DECISIONS,
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
            }
        ),
    )
    