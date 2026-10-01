"""Generate a fictional multipage PDF for local visual QA; no real database."""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_animation_slots import AnimationSlotTests

def main():
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    case=AnimationSlotTests();case.setUp()
    try:
        service,_,_,_=case.create(slot_capacity='2')
        slots=case.slots(service)
        for n in range(58):
            uid=case.add(service,slots[n%4]['slot_uuid'],'confirmed' if n<4 else 'waitlisted',1 if n<2 else None)
            with case.database() as db:
                db.execute('UPDATE animation_bookings SET first_name=?,last_name=?,email=?,phone=? WHERE external_uuid=?',
                    (f'Participant {n+1}','EXEMPLE LOCAL',f'fixture{n}@example.invalid','',uid))
        pdf=case.client.get(f'/admin/animations/{service}/inscriptions.pdf')
        if pdf.status_code!=200:raise RuntimeError('Fictional PDF not generated')
        (output/'inscriptions-creneaux-fictifs.pdf').write_bytes(pdf.data)
        print('Fictional PDF ready')
    finally:case.tearDown()

if __name__=='__main__':main()
