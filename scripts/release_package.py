"""Build single-file Windows/Linux installers from one checksum-verified bundle."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def canonical(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')


def build(output, *, version, source_sha, app_image, web_image, channel='release', compatible_from=(), allow_dirty=False):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',version):
        raise ValueError('Version must be X.Y.Z')
    if not re.fullmatch(r'[0-9a-f]{40}',source_sha):raise ValueError('Full source SHA required')
    pinned=all(re.fullmatch(r'[a-z0-9./:_-]+@sha256:[a-f0-9]{64}',value) for value in (app_image,web_image))
    if channel!='test' and not pinned:raise ValueError('Distributed installers require digest-pinned images')
    if not allow_dirty and subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():
        raise ValueError('Commit the tested source before distributing a package')
    if any(not re.fullmatch(r'\d+\.\d+\.\d+',v) for v in compatible_from):raise ValueError('Exact compatible versions required')
    lock=json.loads((ROOT/'deploy/images.lock.json').read_text(encoding='utf-8'))
    manifest={'format':1,'version':version,'source_sha':source_sha,'channel':channel,'images_pinned':pinned,
              'architecture':'linux/amd64','database_major':18,'schema_migration':'024_installation_bootstrap.sql',
              'compatible_from':list(compatible_from),'images':{'app':app_image,'web':web_image,'db':lock['postgres']},
              'requirements':{'docker_compose_min':'2.24.0','disk_gib':10,'memory_gib_recommended':8},
              'platforms':['Windows 11 x64 / Docker Desktop WSL2','Ubuntu 24.04 LTS amd64'],
              'limitations':['No automatic model downloads','Telegram is not implemented in the source baseline','Offline installation and EXE packaging are not supported in this iteration']}
    files={'compose.yaml':(ROOT/'deploy/compose.yaml').read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8'),
           'images.env':f'FIXRATE_APP_IMAGE={app_image}\nFIXRATE_WEB_IMAGE={web_image}\nFIXRATE_DB_IMAGE={lock["postgres"]}\n'.encode(),
           'release.json':canonical(manifest),'compatible-from.txt':('\n'.join(compatible_from)+'\n').encode()}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    files['bundle-checksums.json']=canonical(hashes)
    files['bundle.sha256']=''.join(f'{hashes[name]}  {name}\n' for name in sorted(hashes)).encode()
    windows=io.BytesIO()
    with zipfile.ZipFile(windows,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o600<<16;archive.writestr(info,data)
    linux=io.BytesIO()
    with gzip.GzipFile(fileobj=linux,mode='wb',mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as archive:
            for name,data in sorted(files.items()):
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;info.mtime=0
                archive.addfile(info,io.BytesIO(data))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    artifacts={}
    for template,name,payload in [('FixRateAI-Setup.ps1.in','FixRateAI-Setup.ps1',windows.getvalue()),('fixrate-install.sh.in','fixrate-install.sh',linux.getvalue())]:
        content=(ROOT/'deploy'/template).read_text(encoding='utf-8').replace('@@PAYLOAD_SHA256@@',hashlib.sha256(payload).hexdigest())
        lines=[base64.b64encode(payload).decode()[i:i+100] for i in range(0,len(base64.b64encode(payload)),100)]
        encoded='\n'.join(('#'+line if name.endswith('.ps1') else line) for line in lines)
        content=content.replace('@@PAYLOAD@@',encoded)
        data=content.encode('utf-8');(output/name).write_bytes(data);artifacts[name]=hashlib.sha256(data).hexdigest()
    (output/'release-manifest.json').write_bytes(canonical(manifest))
    artifacts['release-manifest.json']=hashlib.sha256((output/'release-manifest.json').read_bytes()).hexdigest()
    notes=f'FixRate AI {version}\nSource: {source_sha}\nChannel: {channel}\n\nInstallers use prebuilt digest-pinned images. No production deploy is performed by CI.\nBootstrap is one-time; backup covers database and file storage.\nSupported: Windows 11 x64/WSL2, Ubuntu 24.04 amd64.\nNo EXE, offline bundle or Telegram implementation is claimed.\n'
    (output/'RELEASE-NOTES.md').write_text(notes,encoding='utf-8')
    artifacts['RELEASE-NOTES.md']=hashlib.sha256((output/'RELEASE-NOTES.md').read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name,value in sorted(artifacts.items())),encoding='ascii')
    return manifest


def verify(output):
    output=Path(output)
    expected={'FixRateAI-Setup.ps1','fixrate-install.sh','release-manifest.json','RELEASE-NOTES.md'}
    seen=set()
    for line in (output/'SHA256SUMS').read_text(encoding='ascii').splitlines():
        digest,name=line.split('  ',1)
        if name not in expected or name in seen:raise ValueError('Unexpected/duplicate artifact')
        if hashlib.sha256((output/name).read_bytes()).hexdigest()!=digest:raise ValueError('Artifact checksum mismatch')
        seen.add(name)
    if seen!=expected:raise ValueError('Missing artifact')
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true')
    p.add_argument('--version');p.add_argument('--sha');p.add_argument('--app-image');p.add_argument('--web-image')
    p.add_argument('--channel',choices=('release','ci','test'),default='release')
    p.add_argument('--compatible-from',action='append',default=[]);p.add_argument('--allow-dirty',action='store_true')
    a=p.parse_args()
    if not a.verify:
        build(a.output,version=a.version,source_sha=a.sha,app_image=a.app_image,web_image=a.web_image,channel=a.channel,compatible_from=a.compatible_from,allow_dirty=a.allow_dirty)
    verify(a.output)
    print('Installer package checksums: PASS')

if __name__=='__main__':main()
