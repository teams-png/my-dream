from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.common.exporting import export_company_zip
from apps.tenants.models import Company


class Command(BaseCommand):
    help = "Export all data of one business to a zip file: export_company_data --company SLUG [--out FILE] [--media]"

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company slug (or 'all' for every business)")
        parser.add_argument("--out", default="", help="Output file or folder (default: ./exports/)")
        parser.add_argument("--media", action="store_true", help="Also include uploaded files (logos, photos)")

    def handle(self, *args, **opts):
        companies = Company.objects.all() if opts["company"] == "all" else Company.objects.filter(slug=opts["company"])
        if not companies.exists():
            raise CommandError("No company with that slug.")
        out = Path(opts["out"] or "exports")
        for company in companies:
            data, counts = export_company_zip(company, include_media=opts["media"])
            target = out if out.suffix == ".zip" else out / f"{company.slug}.zip"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.stdout.write(self.style.SUCCESS(f"{company.name}: {sum(counts.values())} rows in {len(counts)} tables -> {target}"))
