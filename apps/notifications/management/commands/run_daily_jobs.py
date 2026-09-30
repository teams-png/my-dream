from django.core.management.base import BaseCommand

from apps.notifications.daily import run_daily_jobs


class Command(BaseCommand):
    help = "Runs the once-a-day jobs (reminders, overdue, expiry, recurring invoices, daily reports) for every company."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Run again even if it already ran today.")

    def handle(self, *args, **options):
        self.stdout.write(str(run_daily_jobs(force=options["force"])))
