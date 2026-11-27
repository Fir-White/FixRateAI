"""Publish only tested OCI images; semver releases require protected environment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import shutil
import hashlib
import time
from urllib.request import urlopen

from scripts.release_package import build,verify,ROOT


def github(path):
    return json.loads(subprocess.check_output(['gh','api',path],text=True))


def validate_release_environment(environment):
    reviewers=[r for r in environment.get('protection_rules',[]) if r.get('type')=='required_reviewers']
    if not reviewers or not reviewers[0].get('reviewers'):
        raise ValueError('Release environment must have required reviewers configured')
    if not reviewers[0].get('prevent_self_review',False):
        raise ValueError('Release environment must prevent self approval')
    if environment.get('can_admins_bypass',True):
        raise ValueError('Disable administrator bypass on the release environment')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();sha=os.environ['GITHUB_SHA'];repo=os.environ['GITHUB_REPOSITORY'];ref=os.environ['GITHUB_REF']
    if repo!='Fir-White/FixRateAI':raise ValueError('Publishing is configured only for the audited repository')
    if not ref.startswith('refs/tags/') or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
        raise ValueError('Publication requires a manual workflow run on a release tag')
    tag=ref.removeprefix('refs/tags/')
    if not re.fullmatch(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)',tag):raise ValueError('Invalid release tag')
    if os.environ.get('FIXRATE_RELEASES_ENABLED')!='true':raise ValueError('Owner has not enabled official releases')
    validate_release_environment(github('repos/'+repo+'/environments/release'))
    subprocess.run(['git','merge-base','--is-ancestor',sha,'origin/main'],check=True,cwd=ROOT)
    previous=subprocess.run(['gh','release','view',tag,'--repo',repo,'--json','isDraft'],capture_output=True,text=True)
    if previous.returncode==0:
        if json.loads(previous.stdout)['isDraft']:raise ValueError('Existing draft requires owner inspection; it will not be overwritten')
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(['gh','release','download',tag,'--repo',repo,'--dir',td],check=True)
            verify(td)
            old=json.loads((Path(td)/'release-manifest.json').read_text())
            if old['source_sha']!=sha:raise ValueError('Existing version refers to another source')
            args.output.mkdir(parents=True,exist_ok=True)
            names=('FixRateAI-Setup.ps1','fixrate-install.sh','release-manifest.json','RELEASE-NOTES.md','SHA256SUMS')
            if old.get('quick_start'):names += (old['quick_start'],)
            for name in names:
                shutil.copyfile(Path(td)/name,args.output/name)
        print('Existing identical release verified; no duplicate publication.')
        return
    with tempfile.TemporaryDirectory(prefix='fixrate-registry-') as td:
        env=dict(os.environ,DOCKER_CONFIG=td)
        token=os.environ['GH_TOKEN']
        subprocess.run(['docker','login','ghcr.io','-u',os.environ['GITHUB_ACTOR'],'--password-stdin'],input=token.encode(),check=True,env=env)
        images={}
        for component in ('app','web'):
            local=f'fixrate-ci-{component}:{sha}'
            metadata=json.loads(subprocess.check_output(['docker','image','inspect',local],env=env,text=True))[0]
            if metadata['Config'].get('Labels',{}).get('org.opencontainers.image.revision')!=sha or metadata['Architecture']!='amd64':
                raise ValueError('Image source/platform does not match the tested commit')
            target=f'ghcr.io/{repo.lower()}-{component}:sha-{sha}'
            subprocess.run(['docker','tag',local,target],check=True,env=env)
            subprocess.run(['docker','push',target],check=True,env=env)
            data=json.loads(subprocess.check_output(['docker','image','inspect',target],env=env,text=True))[0]
            images[component]=next(d for d in data['RepoDigests'] if d.startswith(target.split(':')[0]+'@'))
        # Installers must be usable without inheriting the CI login.
        with tempfile.TemporaryDirectory(prefix='fixrate-anonymous-') as anon:
            anonymous=dict(os.environ,DOCKER_CONFIG=anon)
            for image in images.values():
                subprocess.run(['docker','buildx','imagetools','inspect',image],check=True,env=anonymous,stdout=subprocess.DEVNULL)
    policy=json.loads((ROOT/'deploy/release-policy.json').read_text())
    build(args.output,version=tag[1:],source_sha=sha,app_image=images['app'],web_image=images['web'],
          channel='release',compatible_from=policy['compatible_from'])
    verify(args.output)
    assets=[str(path) for path in args.output.iterdir() if path.is_file()]
    subprocess.run(['gh','release','create',tag,'--repo',repo,'--target',sha,'--draft','--title','FixRate AI '+tag,
                    '--notes-file',str(args.output/'RELEASE-NOTES.md'),*assets],check=True)
    # Download uploaded bytes and validate before changing the draft to public.
    with tempfile.TemporaryDirectory(prefix='fixrate-release-download-') as td:
        subprocess.run(['gh','release','download',tag,'--repo',repo,'--dir',td],check=True)
        verify(td)
    subprocess.run(['gh','release','edit',tag,'--repo',repo,'--draft=false'],check=True)
    published=github('repos/'+repo+'/releases/tags/'+tag)
    for asset in published['assets']:
        local=args.output/asset['name']
        if not local.is_file():continue
        expected=hashlib.sha256(local.read_bytes()).digest()
        for attempt in range(5):
            try:
                with urlopen(asset['browser_download_url'],timeout=30) as response:data=response.read()
                if hashlib.sha256(data).digest()!=expected:raise ValueError('Published asset checksum differs')
                break
            except OSError:
                if attempt==4:raise
                time.sleep(2)
    print('Official release published; uploaded installer checksums verified.')

if __name__=='__main__':main()
