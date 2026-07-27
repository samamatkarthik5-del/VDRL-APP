from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ITPClauseIntervention


def _sync_hold_flag(clause_id) -> None:
    from .models import ITPClause

    is_hold = ITPClauseIntervention.objects.filter(
        clause_id=clause_id, point_code__istartswith="H"
    ).exists()
    ITPClause.objects.filter(pk=clause_id).update(is_hold_point=is_hold)


@receiver(post_save, sender=ITPClauseIntervention)
def intervention_saved(sender, instance, **kwargs):
    _sync_hold_flag(instance.clause_id)


@receiver(post_delete, sender=ITPClauseIntervention)
def intervention_deleted(sender, instance, **kwargs):
    _sync_hold_flag(instance.clause_id)
