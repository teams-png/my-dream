from django.contrib import admin
from .models import Project, Contractor, ProjectAssignment, ProjectExpense

admin.site.register(Project)
admin.site.register(Contractor)
admin.site.register(ProjectAssignment)
admin.site.register(ProjectExpense)
