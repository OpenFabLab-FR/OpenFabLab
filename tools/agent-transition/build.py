"""Package only the two reviewed agent sources and offline preparation tool."""
from pathlib import Path
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

here=Path(__file__).resolve().parent
if __name__=='__main__':
    items={name:here/name for name in ('prepare.py','README.md')}
    items.update({'payload/'+name:here.parents[1]/'updater_agent'/name for name in ('__init__.py','security.py')})
    items['LICENSE']=here.parents[1]/'LICENSE'
    with ZipFile(sys.argv[1],'x') as z:
        for name,path in sorted(items.items()):
            info=ZipInfo(name);info.compress_type=ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,path.read_bytes())
