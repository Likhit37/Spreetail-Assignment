from django.contrib import admin

from .models import FxRate, ImportBatch, ImportRow


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "filename", "group", "status", "created_at")
    inlines = [ImportRowInline]


admin.site.register(FxRate)
