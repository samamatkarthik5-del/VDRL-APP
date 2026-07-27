from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from operations_portal.models import UserModuleAccess


class Command(BaseCommand):
    help = "Grant VDRL, ITP/NOI and/or Calibration module access to a user."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--vdrl", action="store_true")
        parser.add_argument("--itp", action="store_true")
        parser.add_argument("--calibration", action="store_true")
        parser.add_argument("--all", action="store_true", dest="all_modules")
        parser.add_argument("--vdrl-all-sales-orders", action="store_true")
        parser.add_argument("--itp-all-sales-orders", action="store_true")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("User does not exist.") from exc

        access, _ = UserModuleAccess.objects.get_or_create(user=user)
        all_modules = options["all_modules"]
        if options["vdrl"] or all_modules:
            access.can_access_vdrl = True
        if options["itp"] or all_modules:
            access.can_access_itp_noi = True
        if options["calibration"] or all_modules:
            access.can_access_calibration = True
        if options["vdrl_all_sales_orders"]:
            access.vdrl_all_sales_orders = True
        if options["itp_all_sales_orders"]:
            access.itp_all_sales_orders = True
        access.is_active = True
        access.save()
        self.stdout.write(self.style.SUCCESS(f"Module access updated for {user.username}."))
