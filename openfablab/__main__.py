"""Run with ``python -m openfablab reset-admin-pin`` on the application host."""

import argparse
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pin_security import issue_recovery_token, migrate_legacy_admin_pin


def main():
    parser = argparse.ArgumentParser(prog="python -m openfablab")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-admin-pin", help="Générer un lien local à usage unique valable 10 minutes")
    reset.add_argument("--database", default=os.environ.get("OPENFABLAB_DATABASE", str(Path.cwd() / "openfablab.db")))
    migrate = commands.add_parser("migrate-legacy-admin-pin", help="Conserver le PIN de l'archive applicative historique")
    migrate.add_argument("--database", required=True, help="Base historique présente dans le même dossier persistant")
    migrate.add_argument("--archive", required=True, help="Archive applicative V2.4.4 sauvegardée")
    args = parser.parse_args()
    database_path = Path(args.database)
    if not database_path.is_file():
        parser.error("Base OpenFabLab introuvable : indiquez --database")
    if args.command == "migrate-legacy-admin-pin":
        try:
            migrate_legacy_admin_pin(database_path, Path(args.archive))
        except (OSError, ValueError, SyntaxError, UnicodeError, KeyError, zipfile.BadZipFile) as error:
            parser.error(str(error))
        print("PIN administrateur historique conservé sous forme dérivée dans le dossier persistant.")
        return
    if args.command != "reset-admin-pin":
        parser.error("Commande inconnue")
    token = issue_recovery_token(database_path)
    with sqlite3.connect(database_path) as database:
        database.execute(
            "INSERT INTO security_events (event_type, created_at, details_json) VALUES (?, ?, ?)",
            ("admin_recovery_requested", datetime.now(timezone.utc).isoformat(timespec="seconds"), "{}"),
        )
    prefix = "/" + os.environ.get("OPENFABLAB_URL_PREFIX", os.environ.get("COMPTEUR_URL_PREFIX", "")).strip("/")
    if prefix == "/":
        prefix = ""
    print("Ouvrez ce chemin sur votre installation OpenFabLab dans les 10 minutes :")
    print(f"{prefix}/admin/recuperation?token={token}")
    print("Ne partagez pas ce lien ; il ne pourra être utilisé qu'une seule fois.")


if __name__ == "__main__":
    main()
