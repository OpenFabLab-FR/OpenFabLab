"""Isolated browser fixture. No real identity, private asset or external service."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.update(OPENFABLAB_ENABLE_SCHEDULER='0',COMPTEUR_ENABLE_SCHEDULER='0',
                  OPENFABLAB_ENABLE_WEATHER='0',COMPTEUR_ENABLE_WEATHER='0')
from tests import test_app as fixtures
from tests.test_branding import TEMPLATE
from app import get_database,write_setting

fixture=fixtures.OpenFabLabTestCase();fixture.setUp()
branding=Path(fixture.database_path).parent/'branding'
(branding/'badge-template.svg').write_bytes(TEMPLATE)
with fixture.app.app_context():
    db=get_database()
    for key,value in {'structure_dpo':'Service DPO — Atelier fictif','structure_dpo_email':'dpo@example.invalid',
                       'structure_data_controller':'Association des ateliers fictifs','structure_data_controller_address':'Adresse de démonstration',
                       'structure_data_controller_representative':'Camille Exemple','structure_data_controller_representative_role':'Présidente',
                       'structure_badge_template':'badge-template.svg'}.items():write_setting(db,key,value)
    db.commit()
try:fixture.app.run(host='127.0.0.1',port=int(sys.argv[1]),debug=False,use_reloader=False)
finally:fixture.tearDown()
