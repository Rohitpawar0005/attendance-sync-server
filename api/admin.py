from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, AcademicYear, SchoolClass, Teacher, Student, AttendanceRecord


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('year', 'is_active')
    list_editable = ('is_active',)


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('grade', 'section', 'academic_year')
    list_filter = ('academic_year', 'grade')
    ordering = ('academic_year', 'grade', 'section')


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('user', 'class_list')
    filter_horizontal = ('classes',)

    @admin.display(description='Classes')
    def class_list(self, obj):
        return ', '.join(str(c) for c in obj.classes.all()[:5])


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'roll_number', 'school_class')
    list_filter = ('school_class__academic_year', 'school_class__grade')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'roll_number')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'school_class', 'date', 'status', 'is_synced')
    list_filter = ('status', 'is_synced', 'date', 'academic_year')
    date_hierarchy = 'date'
    readonly_fields = ('sync_id', 'is_synced', 'synced_at', 'created_at')
