"""Reproducible, allowlisted application distribution (never user data)."""

import argparse
import re
from openfablab import __version__
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "dist" / f"OpenFabLab-{__version__}.zip"
FILES = (
    "app.py", "billing.py", "annual_report.py", "animation_report.py", "calendar_export.py",
    "pin_security.py", "profile_archive.py", "reservations_sync.py", "animation_slots.py", "branding.py",
    "private_backup.py", "runtime_policy.py", "docs/private-backup.md",
    'evolution_schema.py', 'evolution_users.py', 'evolution_routes.py', 'welcome_mail.py', 'resource_booking.py', 'fablab_calendar.py',
    "build_openfablab.py", "Dockerfile", ".dockerignore", "compose.yaml", "AppStart.command",
    "requirements.txt", "requirements-nas.txt", "LICENSE", "README.md",
    ".env.example",
    "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md",
    "docs/installation.md", "docs/architecture.md", "docs/configuration.md",
    "docs/wordpress.md", "docs/animation-slots.md", "docs/email-templates.md",
    "docs/backup-restore.md", "docs/upgrade.md", "docs/legacy-migration.md", "docs/development.md", "docs/branding.md",
    'docs/evolution-2.7.md',
    "static/app.js", "static/qr-scanner.js", "static/style.css", "static/animation-slots.js",
    'static/evolution.js',
    "static/vendor/jsQR-1.4.0.js", "static/vendor/jsQR-LICENSE.txt",
    "static/fonts/LibreFranklin-Regular.ttf", "static/fonts/LibreFranklin-Bold.ttf",
    "static/fonts/OFL.txt", "static/fonts/AUTHORS.txt", "static/fonts/SOURCE.md",
    "static/icons/OpenFabLab-icon.svg", "static/icons/OpenFabLab-icon-192.png",
    "static/icons/OpenFabLab-icon-512.png", "static/icons/OpenFabLab-favicon.ico",
    "static/brand/OpenFabLab-logo-horizontal.svg", "static/brand/OpenFabLab-logo-complet.svg",
    "badge_templates/OpenFabLab-template.svg",
)
DIRECTORIES = {
    "openfablab": {".py"},
    "templates": {".html"},
}
FORBIDDEN_PARTS = {".venv", "__pycache__", "Saves", "data", "branding", "wordpress", "dist"}


def included_paths(root=ROOT):
    root = Path(root)
    paths = [root / name for name in FILES]
    for directory, suffixes in DIRECTORIES.items():
        base = root / directory
        paths.extend(path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)
    for path in paths:
        relative = path.relative_to(root)
        if not path.is_file() or path.is_symlink() or any(part in FORBIDDEN_PARTS or (part.startswith(".") and part not in {".dockerignore", ".env.example"}) for part in relative.parts):
            raise ValueError(f"Fichier de distribution manquant ou interdit : {relative}")
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def build(output=OUTPUT, root=ROOT):
    root, output = Path(root), Path(output)
    paths = included_paths(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(root).as_posix()
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o755 if path.name == "AppStart.command" else 0o644) << 16
            archive.writestr(info, path.read_bytes())
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
