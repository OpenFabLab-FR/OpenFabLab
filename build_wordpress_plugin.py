"""Build the distributable WordPress plugin without local data or secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "wordpress" / "openfablab-reservations"
OUTPUT = ROOT / "dist" / "openfablab-reservations-2.6.1.zip"
INCLUDED = (
    "openfablab-reservations.php",
    "uninstall.php",
    "includes/class-openfablab-database.php",
    "includes/class-openfablab-api.php",
    "includes/class-openfablab-bookings.php",
    "includes/class-openfablab-test-maintenance.php",
    "includes/class-openfablab-slots.php",
    "includes/class-openfablab-emails.php",
    "assets/reservations.css",
    "assets/reservations.js",
    "assets/OpenFabLab-logo-horizontal.svg",
    "assets/jsQR-1.4.0.js",
    "assets/jsQR-LICENSE.txt",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)


def build(output=OUTPUT):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = [PLUGIN / name for name in INCLUDED]
    for source in sources:
        if not source.is_file() or source.is_symlink():
            raise ValueError("Fichier de distribution absent ou lien symbolique interdit : " + source.name)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, source in zip(INCLUDED, sources):
            info = ZipInfo("openfablab-reservations/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Le ZIP WordPress n'a pas passé son contrôle d'intégrité.")
    return output


if __name__ == "__main__":
    print(build())
