"""Build a successor image. Never install or stop an agent."""
import argparse
import hashlib
import inspect
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

NAME = 'openfablab-updater-agent'
OLD = {'security.py':'7936987d03479a6d8ad6eb84760381d2f9c800f095e4c41a8b368d9557e664de',
       '__init__.py':'054aa4c54a0a9d72f33d21cdae690936a4d32b22020799b55d47902d4b9f07e3'}

def check_image(image):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',image):
        raise ValueError('Image locale immuable attendue.')

def verify_old(root):
    root=Path(root)
    for name, sha in OLD.items():
        path=root/name
        if path.resolve()!=path or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('Agent source non reconnu : aucune modification.')

def context(image, payload):
    check_image(image)
    files={name:(payload/name).read_bytes() for name in OLD}
    files['Dockerfile']=('FROM '+image+'\nCOPY security.py __init__.py /opt/agent/updater_agent/\n').encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as archive:
        for name,data in files.items():
            entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o644
            archive.addfile(entry,io.BytesIO(data))
    return buffer.getvalue()

def prepare(docker,payload,run=subprocess.run):
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','DOCKER_HOST':'unix:///var/run/docker.sock','DOCKER_BUILDKIT':'0'}
    def cli(args, data=None):
        return run([docker,*args],input=data,env=env,check=True,stdout=subprocess.PIPE).stdout.decode().strip()
    current=['container','inspect','--format','{{.Image}}',NAME]
    image=cli(current)
    check_image(image)
    locked=['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--entrypoint','python']
    check='from pathlib import Path\nimport hashlib\nOLD='+repr(OLD)+'\n'+inspect.getsource(verify_old)+"\nverify_old('/opt/agent/updater_agent')"
    cli(locked+[image,'-IB','-c',check])
    candidate=cli(['build','--network','none','--pull=false','--quiet','-'],context(image,payload))
    check_image(candidate)
    check=("from updater_agent.security import version,Refused\nfrom updater_agent import AGENT_VERSION,AGENT_PROTOCOL\n"
           "assert AGENT_VERSION=='1.2' and AGENT_PROTOCOL==1\nassert version('2.17')==version('2.17.0')>version('2.16.1')\n"
           "try: version('2.17-rc1')\nexcept Refused: pass\nelse: raise RuntimeError('Version invalide acceptée')")
    cli(locked+[candidate,'-B','-c',check])
    if cli(current)!=image:
        raise ValueError('Agent actif changé durant la préparation.')
    return {'previous_image':image,'prepared_image':candidate,'activated':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker',required=True,type=Path)
    opts=parser.parse_args()
    if not opts.docker.is_absolute() or not opts.docker.is_file():
        parser.error('Chemin absolu du client Docker local requis.')
    print(json.dumps(prepare(str(opts.docker),Path(__file__).resolve().parent/'payload')))
