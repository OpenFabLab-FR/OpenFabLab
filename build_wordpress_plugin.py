"""Build the distributable WordPress plugin without local data or secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "wordpress" / "openfablab-reservations"
OUTPUT = ROOT / "dist" / "openfablab-reservations-2.8.1.zip"
INCLUDED = (
    "openfablab-reservations.php",
    "uninstall.php",
    "includes/class-openfablab-database.php",
    "includes/class-openfablab-api.php",
    "includes/class-openfablab-admin.php",
    "assets/admin.css",
    "assets/admin.js",
    "includes/class-openfablab-relay.php",
    "includes/public-link.php",
    "assets/link.js",
    "assets/reservations.css",
    "assets/family.js",
    "assets/OpenFabLab-logo-horizontal.svg",
    "assets/jsQR-1.4.0.js",
    "assets/jsQR-LICENSE.txt",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)
MACOS_METADATA = {".DS_Store", ".AppleDouble", ".AppleDesktop", "__MACOSX",
                  ".LSOverride", ".Spotlight-V100", ".Trashes", ".TemporaryItems",
                  ".fseventsd", ".VolumeIcon.icns", ".apdisk"}


def build(output=OUTPUT):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = [PLUGIN / name for name in INCLUDED]
    for source in sources:
        if not source.is_file() or source.is_symlink() or any(
            part in MACOS_METADATA or part.startswith("._") for part in source.relative_to(PLUGIN).parts
        ):
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
