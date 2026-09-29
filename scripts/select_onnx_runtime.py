"""Reproducible Windows/Python 3.12 runtime switch with verified local rollback.

Run with the project virtual environment after stopping the backend. The wheel
hashes identify the same ORT 1.18.0 builds measured on this project installation.
"""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import subprocess
import sys

WHEELS = {
    "cpu": ("onnxruntime", "1fa175bd43f610465d5787ae06050c81f7ce09da2bf3e914eb282cb8eab363ef"),
    "cuda": ("onnxruntime_gpu", "97df451777322a534dbedff49d43a4f6f74bd5258ccf31b2161e1af606bc724d"),
}

def installed_device():
    found=[]
    for device,(package,_) in WHEELS.items():
        try:
            current=version(package.replace('_','-'))
        except PackageNotFoundError:
            continue
        if current!='1.18.0':
            raise RuntimeError(f"Unexpected {package} version {current}; preserve it and review before switching")
        found.append(device)
    if len(found)>1:
        raise RuntimeError('Both CPU and GPU distributions are installed; resolve overlapping packages first')
    return found[0] if found else None

def pip(*arguments):
    subprocess.run([sys.executable,'-m','pip','--isolated',*arguments],check=True,timeout=360)

def verified_wheel(device, directory):
    package, expected=WHEELS[device]
    wheel=directory/f'{package}-1.18.0-cp312-cp312-win_amd64.whl'
    if not wheel.exists():
        pip('download','--index-url','https://pypi.org/simple','--only-binary=:all:','--no-deps','--dest',str(directory),package.replace('_','-')+'==1.18.0')
    with wheel.open('rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected:
        raise RuntimeError('Wheel hash mismatch; no package changes were made')
    return wheel

def switch(device, directory):
    if platform.system()!='Windows' or sys.version_info[:2]!=(3,12) or platform.machine().lower() not in ('amd64','x86_64'):
        raise RuntimeError('This installer is validated only for Windows x64 and Python 3.12')
    previous=installed_device()
    directory.mkdir(parents=True,exist_ok=True)
    target=verified_wheel(device,directory)
    rollback=verified_wheel(previous,directory) if previous else None
    if previous==device:
        return {'device':device,'changed':False}
    if previous:
        pip('uninstall','-y',WHEELS[previous][0].replace('_','-'))
    try:
        pip('install','--no-index','--no-deps',str(target))
        # Fresh process avoids Windows DLL locks during install or rollback.
        check="import torch; import onnxruntime as o; assert o.__version__=='1.18.0'"
        if device=='cuda':
            check+="; assert torch.version.cuda=='11.8' and torch.cuda.is_available(); assert 'CUDAExecutionProvider' in o.get_available_providers()"
        subprocess.run([sys.executable,'-c',check],check=True,timeout=45)
    except Exception:
        pip('uninstall','-y',WHEELS[device][0].replace('_','-'))
        if rollback:
            pip('install','--no-index','--no-deps',str(rollback))
        raise
    return {'device':device,'changed':True,'previous':previous,'wheel_sha256':WHEELS[device][1],
            'validation':'Package/provider check only. Run the full benchmark before promotion.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',choices=WHEELS)
    parser.add_argument('--wheelhouse',type=Path,default=Path(__file__).resolve().parents[1]/'.runtime-wheels')
    args=parser.parse_args()
    result=switch(args.device,args.wheelhouse.resolve()) if args.device else {'installed_device':installed_device(),'version':'1.18.0'}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
