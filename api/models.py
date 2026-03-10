"""
Models — mirrors the desktop app's models exactly so sync works seamlessly.
Only includes the models needed for sync (no FaceSample, no ManualExcuseLog).
"""
from __future__ import annotations
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')


class AcademicYear(models.Model):
    year = models.CharField(max_length=9, unique=True, help_text="Format: YYYY-YYYY")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.year


class SchoolClass(models.Model):
    grade = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    section = models.CharField(max_length=2)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, default=1)

    class Meta:
        unique_together = ("academic_year", "grade", "section")
        verbose_name_plural = "School Classes"

    def __str__(self):
        return f"Class {self.grade}-{self.section.upper()} ({self.academic_year})"

    def save(self, *args, **kwargs):
        if self.section:
            self.section = self.section.upper()
        super().save(*args, **kwargs)


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    classes = models.ManyToManyField(SchoolClass, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='students',
    )
    roll_number = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='students/', blank=True, null=True)
    face_encodings = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('school_class', 'roll_number')

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
    confidence = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    created_at = models.DateTimeField(auto_now_add=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)

    # Sync tracking
    sync_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_synced = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('student', 'school_class', 'date')

    def __str__(self):
        return f"{self.student} - {self.school_class} on {self.date}: {self.get_status_display()}"
