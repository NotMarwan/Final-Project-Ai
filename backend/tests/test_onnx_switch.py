import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest

spec=importlib.util.spec_from_file_location('runtime_switch',Path(__file__).resolve().parents[2]/'scripts/select_onnx_runtime.py')
switcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(switcher)

def test_tampered_wheel_cannot_change_environment(tmp_path,monkeypatch):
    wheel=tmp_path/'onnxruntime_gpu-1.18.0-cp312-cp312-win_amd64.whl'
    wheel.write_bytes(b'not the verified wheel')
    calls=[]
    monkeypatch.setattr(switcher,'pip',lambda *args:calls.append(args))
    with pytest.raises(RuntimeError,match='hash mismatch'):
        switcher.verified_wheel('cuda',tmp_path)
    assert calls==[]

def test_failed_gpu_install_restores_previous_cpu(tmp_path,monkeypatch):
    monkeypatch.setattr(switcher.platform,'system',lambda:'Windows')
    monkeypatch.setattr(switcher.platform,'machine',lambda:'AMD64')
    monkeypatch.setattr(switcher,'installed_device',lambda:'cpu')
    monkeypatch.setattr(switcher,'verified_wheel',lambda device,directory:directory/f'{device}.whl')
    commands=[]
    def pip(*args):
        commands.append(args)
        if args[0]=='install' and args[-1].endswith('cuda.whl'):
            raise subprocess.CalledProcessError(1,['pip'])
    monkeypatch.setattr(switcher,'pip',pip)
    with pytest.raises(subprocess.CalledProcessError):switcher.switch('cuda',tmp_path)
    assert commands[-2]==('uninstall','-y','onnxruntime-gpu')
    assert commands[-1][-1].endswith('cpu.whl')

def test_overlapping_distributions_are_rejected(monkeypatch):
    monkeypatch.setattr(switcher,'version',lambda package:'1.18.0')
    with pytest.raises(RuntimeError,match='Both CPU and GPU'):
        switcher.installed_device()
