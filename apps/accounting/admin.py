from django.contrib import admin
from .models import Account, FiscalYear, JournalEntry, JournalLine


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "date", "reference", "source_type", "is_void")
    list_filter = ("is_void", "source_type")
    inlines = [JournalLineInline]


admin.site.register(Account)
admin.site.register(FiscalYear)
