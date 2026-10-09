FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Paris

WORKDIR /app

COPY requirements.txt requirements-nas.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-nas.txt

COPY app.py billing.py annual_report.py animation_report.py calendar_export.py pin_security.py profile_archive.py reservations_sync.py animation_slots.py branding.py ./
COPY evolution_schema.py evolution_users.py evolution_routes.py enrollment_privacy.py welcome_mail.py resource_booking.py fablab_calendar.py usability.py ./
COPY private_backup.py runtime_policy.py ./
COPY badge_palette.py ./
COPY outbound_actions.py outbound_sync.py ./
COPY tablet_reservations.py ./
COPY family_model.py family_routes.py family_reservations.py family_reservation_routes.py family_waitlist.py ./
COPY openfablab ./openfablab
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY templates ./templates
COPY static ./static
COPY badge_templates ./badge_templates

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/stat/sante', timeout=2).read()"]

CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=1", "--threads=4", "--timeout=30", "--access-logfile=-", "--error-logfile=-", "app:app"]
