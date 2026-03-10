"""
Sync API views — the only 3 endpoints this server exposes.
"""
from __future__ import annotations
import json
import uuid
from datetime import date

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .models import (
    AcademicYear,
    AttendanceRecord,
    SchoolClass,
    Student,
    Teacher,
    User,
)


# ── Auth helper ─────────────────────────────────────────────────────────

def _check_auth(request: HttpRequest) -> str | None:
    """Return an error string if auth fails, None if OK."""
    expected = settings.SYNC_API_KEY
    if not expected:
        return "SYNC_API_KEY not configured on the server."
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Bearer "):
        return "Missing Bearer token."
    token = auth[7:].strip()
    if token != expected:
        return "Invalid API key."
    return None


# ── 1. Receive attendance from the desktop app ──────────────────────────

@csrf_exempt
@require_POST
def sync_receive(request: HttpRequest) -> JsonResponse:
    """Accept batched attendance records from the desktop client."""
    err = _check_auth(request)
    if err:
        return JsonResponse({"error": err}, status=403)

    try:
        records = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(records, list):
        return JsonResponse({"error": "Expected a JSON array"}, status=400)

    imported = 0
    skipped = 0
    errors = []

    for idx, rec in enumerate(records):
        try:
            sync_id = uuid.UUID(rec["sync_id"])

            # Skip if already imported
            if AttendanceRecord.objects.filter(sync_id=sync_id).exists():
                skipped += 1
                continue

            # Resolve foreign keys
            student_user = User.objects.get(username=rec["student_username"])
            student = Student.objects.get(user=student_user)

            school_class = SchoolClass.objects.get(
                grade=rec["school_class_grade"],
                section=rec["school_class_section"].upper(),
            )

            academic_year = AcademicYear.objects.get(year=rec["academic_year"])

            AttendanceRecord.objects.update_or_create(
                student=student,
                school_class=school_class,
                date=date.fromisoformat(rec["date"]),
                defaults={
                    "status": rec.get("status", "present"),
                    "confidence": rec.get("confidence", 0.0),
                    "academic_year": academic_year,
                    "sync_id": sync_id,
                    "is_synced": True,
                    "synced_at": timezone.now(),
                },
            )
            imported += 1

        except Exception as exc:
            errors.append(f"Record {idx}: {exc}")

    return JsonResponse({
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:20],  # cap error list
    })


# ── 2. Export data to the desktop app ───────────────────────────────────

@csrf_exempt
@require_GET
def sync_export(request: HttpRequest) -> JsonResponse:
    """Return all reference data for the desktop app to pull."""
    err = _check_auth(request)
    if err:
        return JsonResponse({"error": err}, status=403)

    academic_years = [
        {"year": ay.year, "is_active": ay.is_active}
        for ay in AcademicYear.objects.all()
    ]

    classes = [
        {
            "grade": sc.grade,
            "section": sc.section,
            "academic_year": str(sc.academic_year),
        }
        for sc in SchoolClass.objects.select_related("academic_year").all()
    ]

    students = []
    for stu in Student.objects.select_related(
        "user", "school_class", "school_class__academic_year"
    ).all():
        students.append({
            "username": stu.user.username,
            "first_name": stu.user.first_name,
            "last_name": stu.user.last_name,
            "email": stu.user.email,
            "roll_number": stu.roll_number,
            "school_class_grade": stu.school_class.grade if stu.school_class else None,
            "school_class_section": stu.school_class.section if stu.school_class else None,
            "academic_year": str(stu.school_class.academic_year) if stu.school_class else None,
            "face_encodings": stu.face_encodings or [],
        })

    teachers = []
    for teacher in Teacher.objects.select_related("user").prefetch_related(
        "classes__academic_year"
    ).all():
        teachers.append({
            "username": teacher.user.username,
            "first_name": teacher.user.first_name,
            "last_name": teacher.user.last_name,
            "email": teacher.user.email,
            "classes": [
                {
                    "grade": c.grade,
                    "section": c.section,
                    "academic_year": str(c.academic_year),
                }
                for c in teacher.classes.all()
            ],
        })

    return JsonResponse({
        "ok": True,
        "academic_years": academic_years,
        "classes": classes,
        "students": students,
        "teachers": teachers,
    })


# ── 3. Health / status ──────────────────────────────────────────────────

@csrf_exempt
def sync_status(request: HttpRequest) -> JsonResponse:
    """Simple health check — confirms the server is running and auth works."""
    err = _check_auth(request)
    if err:
        return JsonResponse({"ok": False, "error": err}, status=403)
    return JsonResponse({
        "ok": True,
        "server": "eduattend-sync",
        "records": AttendanceRecord.objects.count(),
    })
