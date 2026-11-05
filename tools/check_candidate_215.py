"""Targeted candidate regression suite; fictitious files and no outgoing IP."""
import os,socket,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUITES=['tests.test_v215_core','tests.test_v215_resources','tests.test_v215_views','tests.test_v215_settings','tests.test_v215_search',
 'tests.test_resource_documents','tests.test_updater_agent','tests.test_updater_socket','tests.test_updater_data',
 'tests.test_updater_files','tests.test_updater_executor','tests.test_updater_integration','tests.test_updater_installation',
 'tests.test_v215_distribution','tests.test_families.FamilyTests','tests.test_v2144.Lifecycle',
 'tests.test_v2143_enrollment','tests.test_enrollment_privacy']
def deny(event,args):
    if event in ('socket.connect','socket.sendto') and getattr(args[0],'family',None)==socket.AF_UNIX:return
    if event in ('socket.connect','socket.sendto','socket.getaddrinfo'):raise OSError('CANDIDATE_TEST_OUTGOING_DENIED')
if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='openfablab-215-tests-') as folder:
        reference=os.environ.get('OPENFABLAB_TEST_SOURCE_2144')
        for key in list(os.environ):
            if key.startswith(('OPENFABLAB_','COMPTEUR_')):os.environ.pop(key)
        os.environ.update(OPENFABLAB_DATABASE=str(Path(folder)/'import.db'),OPENFABLAB_SECRET_KEY_FILE=str(Path(folder)/'import.secret'),
            OPENFABLAB_EXTERNAL_ACTIONS='0',OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0',PYTHONDONTWRITEBYTECODE='1')
        if reference:os.environ['OPENFABLAB_TEST_SOURCE_2144']=reference
        sys.path[:0]=[str(ROOT),str(ROOT/'tests')];sys.addaudithook(deny)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(SUITES))
        raise SystemExit(not result.wasSuccessful())
