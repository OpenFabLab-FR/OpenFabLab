"""Reproducible, allowlisted application distribution (never user data)."""

import argparse
import hashlib
import json
import re
import shlex
from openfablab import __version__
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "dist" / f"OpenFabLab-{__version__}.zip"
FILES = (
    'v215_schema.py','v215_routes.py','resource_loans.py','user_participation.py','admin_search.py','admin_summary.py',
    'updater_client.py','update_wire.py','resource_portal.py','resource_documents.py','pdf_guard.py',
    'localized_formats.py','settings_groups.py','configuration_flow.py','setup_routes.py',
    'resource_sort.py','resource_editor.py','static/resource-page.js',
    'static/v215.css','static/admin-search.js','static/updates.js','package.json',
    'requirements-dev.txt','requirements-dev.lock','package-lock.json','tools/check_candidate_215.py',
    'tools/check_public_tree.py','tools/run_checks.py',
    'docs/evolution-2.15.0.md','docs/update-agent.md','docs/upgrade-2.15.0.md','docs/wordpress-2.15.0.md',
    'docs/utilisation.md','docs/resources-maintenance.md','docs/wordpress-2.14.4.md','docs/publication-2.14.4.md',
    'v2144_schema.py','resource_lifecycle.py','public_calendar_history.py','docs/corrections-2.14.4.md',
    'enrollment_feedback.py',
    'docs/corrections-2.14.3.md',
    'public_resource_labels.py','docs/corrections-2.14.2.md',
    'v2141_schema.py','docs/corrections-2.14.1.md','docs/tests-2.14.1.md',
    'docs/evolution-2.14.0.md','docs/wordpress-2.14.0.md','docs/i18n.md','docs/tests-2.14.0.md',
    'v214_schema.py','v214_routes.py','machine_maintenance.py','openlab_openings.py','automatic_reminders.py','reservation_calendar.py','public_snapshot.py','i18n.py',
    'static/v214.js','static/v214.css','static/i18n.css',
    'static/settings-panels.js',
    'animation_publication.py','booking_presentation.py','docs/ergonomie-2.13.0.md',
    'statistics_quality.py','installation_health.py','visual_report.py',
    'docs/consolidation-2.12.0.md','docs/maintenance.md',
    'animation_attendance.py', 'v211_routes.py', 'docs/evolution-2.11.0.md',
    'docs/corrections-2.10.1.md',
    'v210_schema.py','v210_config.py','v210_routes.py','memberships.py','membership_notices.py','sync_incidents.py','kiosk_feedback.py',
    'static/kiosk-sound.js','static/memberships.css','docs/evolution-2.10.0.md',
    'retention_notices.py',
    'v290_schema.py', 'waitlist_limits.py', 'attendance_analysis.py', 'client_categories.py',
    'static/attendance-analysis.js', 'static/attendance-analysis.css', 'docs/evolution-2.9.0.md',
    'docs/corrections-2.8.6.md',
    'booking_account_links.py',
    "docs/corrections-2.8.5.md", "docs/installation-common.md", "docs/installation-linux.md",
    "docs/installation-windows.md", "docs/installation-raspberry-pi.md", "docs/installation-synology.md",
    "docs/platform-compatibility.md",
    "reservation_notifications.py", "reservation_email_templates.py", "animation_information.py", "participant_search.py", "static/participant-picker.js",
    "app.py", "billing.py", "annual_report.py", "animation_report.py", "calendar_export.py",
    "badge_palette.py", "usability.py", "docs/usability-2.8.3.md", "enrollment_privacy.py", "docs/corrections-2.8.4.md",
    "pin_security.py", "profile_archive.py", "reservations_sync.py", "animation_slots.py", "branding.py",
    "private_backup.py", "runtime_policy.py", "docs/private-backup.md",
    "outbound_actions.py", "outbound_sync.py", "docs/outbound-2.8.1.md", "docs/reservations-2.8.2.md",
    'evolution_schema.py', 'evolution_users.py', 'evolution_routes.py', 'welcome_mail.py', 'resource_booking.py', 'fablab_calendar.py', 'tablet_reservations.py', 'family_model.py', 'family_routes.py', 'family_reservations.py', 'family_reservation_routes.py', 'family_waitlist.py',
    "build_openfablab.py", "Dockerfile", ".dockerignore", "compose.yaml", "AppStart.command",
    "requirements.txt", "requirements-nas.txt", "LICENSE", "README.md",
    ".env.example",
    "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", "ROADMAP.md",
    "docs/installation.md", "docs/architecture.md", "docs/configuration.md",
    "docs/wordpress.md", "docs/animation-slots.md", "docs/email-templates.md",
    "docs/backup-restore.md", "docs/upgrade.md", "docs/legacy-migration.md", "docs/development.md", "docs/branding.md",
    'docs/evolution-2.7.md',
    'docs/corrections-2.7.1.md',
    'docs/families-2.8.md',
    'docs/candidate-2.8-guide.md',
    "static/app.js", "static/qr-scanner.js", "static/style.css", "static/animation-slots.js",
    'static/evolution.js', 'static/public-enrollment.js',
    "static/vendor/jsQR-1.4.0.js", "static/vendor/jsQR-LICENSE.txt",
    "static/fonts/LibreFranklin-Regular.ttf", "static/fonts/LibreFranklin-Bold.ttf",
    "static/fonts/OFL.txt", "static/fonts/AUTHORS.txt", "static/fonts/SOURCE.md",
    "static/icons/OpenFabLab-icon.svg", "static/icons/OpenFabLab-icon-192.png",
    "static/icons/OpenFabLab-icon-512.png", "static/icons/OpenFabLab-favicon.ico",
    "static/brand/OpenFabLab-logo-horizontal.svg", "static/brand/OpenFabLab-logo-complet.svg",
    "badge_templates/OpenFabLab-template.svg",
)
DIRECTORIES = {
    "updater_agent": {".py"},
    "tests": {".py", ".php", ".js"},
    "docs": {".md"},
    "translations": {".json"},
    "openfablab": {".py"},
    "templates": {".html"},
}
FORBIDDEN_PARTS = {".venv", "__pycache__", "Saves", "data", "branding", "wordpress", "dist"}
MACOS_METADATA = {".DS_Store", ".AppleDouble", ".AppleDesktop", "__MACOSX",
                  ".LSOverride", ".Spotlight-V100", ".Trashes", ".TemporaryItems",
                  ".fseventsd", ".VolumeIcon.icns", ".apdisk"}


def is_macos_metadata(relative):
    return any(part in MACOS_METADATA or part.startswith("._") for part in Path(relative).parts)


def included_paths(root=ROOT):
    root = Path(root)
    paths = [root / name for name in FILES]
    for directory, suffixes in DIRECTORIES.items():
        base = root / directory
        paths.extend(path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in suffixes
                     and not is_macos_metadata(path.relative_to(root)))
    for path in paths:
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink() or is_macos_metadata(relative) or any(part in FORBIDDEN_PARTS or (part.startswith(".") and part not in {".dockerignore", ".env.example"}) for part in relative.parts):
            raise ValueError(f"Fichier de distribution manquant ou interdit : {relative}")
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def update_manifest(paths,root=ROOT):
    root=Path(root)
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    runtime={}
    for line in (root/'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):continue
        for name in shlex.split(line)[1:-1]:
            origin=root/name
            for path in ([origin] if origin.is_file() else origin.rglob('*')):
                if path.is_file() and not is_macos_metadata(path.relative_to(root)) and '__pycache__' not in path.parts:
                    relative=path.relative_to(root).as_posix()
                    if relative not in hashes:raise ValueError('Runtime absent de la distribution : '+relative)
                    runtime[relative]=hashes[relative]
    return dict(format=1,version=__version__,agent_protocol=1,schema=26,source_schemas=[26],migration='family_model.migrate',
        new_tables=[],new_settings={},
        notes='En-tête d’administration compact sur smartphone en portrait et nouveau style du Résumé. SQLite 26, sans migration.',
        base_image='python:3.12-slim-bookworm',files=hashes,runtime_files=runtime)


def build(output=OUTPUT, root=ROOT):
    root, output = Path(root), Path(output)
    paths = included_paths(root)
    manifest=update_manifest(paths,root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(root).as_posix()
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o755 if path.name == "AppStart.command" else 0o644) << 16
            archive.writestr(info, path.read_bytes())
        info=ZipInfo('UPDATE-MANIFEST.json',date_time=(2026,1,1,0,0,0));info.compress_type=ZIP_DEFLATED;info.external_attr=0o644<<16
        archive.writestr(info,(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("L'archive OpenFabLab est corrompue.")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Créer l'archive publique de l'application OpenFabLab.")
    parser.add_argument("--version", default=__version__, help="Version à placer dans le nom du ZIP")
    version = parser.parse_args().version
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}(?:-[A-Za-z0-9.]+)?", version):
        parser.error("Version invalide.")
    if version != __version__:
        parser.error("Le nom de distribution doit correspondre à la version des sources.")
    print(build(ROOT / "dist" / f"OpenFabLab-{version}.zip"))
