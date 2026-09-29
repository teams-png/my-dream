from django.contrib import admin
from .models import MembershipPlan, GymMember, Attendance

admin.site.register(MembershipPlan)
admin.site.register(GymMember)
admin.site.register(Attendance)
