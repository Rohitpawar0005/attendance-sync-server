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


# ── 4. Receive reference data from the desktop app ─────────────────────

@csrf_exempt
@require_POST
def sync_push_data(request: HttpRequest) -> JsonResponse:
    """
    Accept reference data (academic years, classes, students, teachers)
    pushed from the desktop app and upsert into the server database.
    """
    err = _check_auth(request)
    if err:
        return JsonResponse({"error": err}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    created = 0
    updated = 0
    errors = []

    # 1) Academic years
    for ay in data.get("academic_years", []):
        try:
            obj, was_created = AcademicYear.objects.update_or_create(
                year=ay["year"],
                defaults={"is_active": ay.get("is_active", False)},
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"AcademicYear '{ay.get('year')}': {exc}")

    # 2) Classes
    for cls in data.get("classes", []):
        try:
            academic_year = AcademicYear.objects.filter(
                year=cls["academic_year"]
            ).first()
            if not academic_year:
                errors.append(f"Class: AcademicYear '{cls['academic_year']}' not found")
                continue
            _, was_created = SchoolClass.objects.get_or_create(
                grade=cls["grade"],
                section=cls["section"].upper(),
                academic_year=academic_year,
            )
            if was_created:
                created += 1
        except Exception as exc:
            errors.append(f"Class '{cls.get('grade')}-{cls.get('section')}': {exc}")

    # 3) Students
    for stu in data.get("students", []):
        try:
            user, user_created = User.objects.get_or_create(
                username=stu["username"],
                defaults={
                    "first_name": stu.get("first_name", ""),
                    "last_name": stu.get("last_name", ""),
                    "email": stu.get("email", ""),
                    "role": "student",
                },
            )
            if not user_created:
                changed = False
                for field in ("first_name", "last_name", "email"):
                    val = stu.get(field, "")
                    if val and getattr(user, field) != val:
                        setattr(user, field, val)
                        changed = True
                if changed:
                    user.save()
                    updated += 1

            # Resolve class
            school_class = None
            if stu.get("school_class_grade") and stu.get("academic_year"):
                ay = AcademicYear.objects.filter(year=stu["academic_year"]).first()
                if ay:
                    school_class = SchoolClass.objects.filter(
                        grade=stu["school_class_grade"],
                        section=(stu.get("school_class_section") or "A").upper(),
                        academic_year=ay,
                    ).first()

            _, was_created = Student.objects.update_or_create(
                user=user,
                defaults={
                    "school_class": school_class,
                    "roll_number": stu.get("roll_number", ""),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"Student '{stu.get('username')}': {exc}")

    # 4) Teachers
    for tch in data.get("teachers", []):
        try:
            user, user_created = User.objects.get_or_create(
                username=tch["username"],
                defaults={
                    "first_name": tch.get("first_name", ""),
                    "last_name": tch.get("last_name", ""),
                    "email": tch.get("email", ""),
                    "role": "teacher",
                },
            )
            teacher, was_created = Teacher.objects.get_or_create(user=user)
            if was_created:
                created += 1

            # Sync class assignments
            for cls_data in tch.get("classes", []):
                ay = AcademicYear.objects.filter(year=cls_data["academic_year"]).first()
                if not ay:
                    continue
                sc = SchoolClass.objects.filter(
                    grade=cls_data["grade"],
                    section=cls_data["section"].upper(),
                    academic_year=ay,
                ).first()
                if sc and sc not in teacher.classes.all():
                    teacher.classes.add(sc)
        except Exception as exc:
            errors.append(f"Teacher '{tch.get('username')}': {exc}")

    return JsonResponse({
        "ok": True,
        "created": created,
        "updated": updated,
        "errors": errors[:20],
    })


# ── 4. Temporary debug / diagnostic endpoint ───────────────────────────

@csrf_exempt
def sync_debug(request: HttpRequest) -> JsonResponse:
    """
    Temporary diagnostic endpoint.
    Returns info about database tables, Django version, and any errors.
    Protected by API key.
    """
    err = _check_auth(request)
    if err:
        return JsonResponse({"error": err}, status=403)

    import django
    from django.db import connection
    import traceback

    info = {
        "django_version": django.get_version(),
        "database_engine": settings.DATABASES["default"]["ENGINE"] if "ENGINE" in settings.DATABASES.get("default", {}) else "dj_database_url",
        "debug": settings.DEBUG,
        "allowed_hosts": settings.ALLOWED_HOSTS,
        "csrf_trusted_origins": settings.CSRF_TRUSTED_ORIGINS,
        "tables": [],
        "model_counts": {},
        "errors": [],
    }

    # Check database tables
    try:
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            info["tables"] = tables
    except Exception as exc:
        info["errors"].append(f"DB tables check: {traceback.format_exc()}")

    # Check model counts
    for model_name, model_class in [
        ("User", User),
        ("AcademicYear", AcademicYear),
        ("SchoolClass", SchoolClass),
        ("Student", Student),
        ("Teacher", Teacher),
        ("AttendanceRecord", AttendanceRecord),
    ]:
        try:
            info["model_counts"][model_name] = model_class.objects.count()
        except Exception as exc:
            info["errors"].append(f"{model_name}: {traceback.format_exc()}")

    # Check static files
    try:
        import os
        static_root = str(settings.STATIC_ROOT)
        info["static_root_exists"] = os.path.exists(static_root)
        if os.path.exists(static_root):
            info["static_file_count"] = sum(len(f) for _, _, f in os.walk(static_root))
    except Exception as exc:
        info["errors"].append(f"Static files: {str(exc)}")

    return JsonResponse(info)

