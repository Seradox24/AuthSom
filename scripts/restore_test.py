#!/usr/bin/env python3
"""Restore latest complete backup into a temporary internal network, no published ports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from stt import ROOT, profile, read_env
from admin import request, token

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--env-file',required=True)
    p.add_argument('--evidence',required=True)
    a = p.parse_args()
    c = profile(a.env_file)
    copies = sorted(x for x in Path(c['BACKUP_ROOT']).iterdir() if x.is_dir() and (x/'SHA256SUMS').is_file() and not x.name.endswith('.partial'))
    source = copies[-1]
    for line in (source/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ')
        assert Path(name).name == name
        with (source/name).open('rb') as stream: assert hashlib.file_digest(stream,'sha256').hexdigest() == digest
    evidence = Path(a.evidence)
    scratch = Path(tempfile.mkdtemp(prefix='authsom-restore-',dir=evidence.parent)).resolve()
    os.chmod(scratch,0o700)
    for filename,label in [('configuration.tar.gz','configuration'),('secrets.tar.gz','secrets')]:
        with tarfile.open(source/filename) as archive:
            for member in archive.getmembers():
                rel = Path(member.name)
                if rel.is_absolute() or '..' in rel.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    raise ValueError('Unsafe archive entry')
            archive.extractall(scratch,filter='data')
    restored = read_env(scratch/'configuration/profile.env')
    restored['COMPOSE_PROJECT_NAME'] = 'stt-authsom-restore-'+source.name.replace('_','-')
    restored.update(CONFIG_ROOT=str(scratch/'configuration'),SECRET_ROOT=str(scratch/'secrets'),
                    DATA_ROOT=str(scratch/'data'),BACKUP_ROOT=str(scratch/'backups'),KEYCLOAK_HTTP_PORT='18182')
    profile_path = scratch/'restore.env'
    profile_path.write_text(''.join(k+'='+v+'\n' for k,v in restored.items()))
    restore_secrets = scratch/'secrets/secrets.env'
    private = read_env(restore_secrets)
    assert not private.get('KEYCLOAK_ADMIN_PASSWORD')
    r = profile(profile_path)
    override = scratch/'isolated.yaml'
    override.write_text('services:\n  keycloak:\n    ports: !reset []\nnetworks:\n  default:\n    internal: true\n')
    env = dict(os.environ)
    env.update({k:v for k,v in r.items() if not k.startswith('_')})
    command = ['docker','compose','--project-directory',str(ROOT),'--env-file',str(profile_path),
               '--env-file',str(restore_secrets),'-f',str(ROOT/'compose.stt.yaml'),'-f',str(override),'-p',r['COMPOSE_PROJECT_NAME']]
    def dc(*args,**kwargs): return subprocess.run(command+list(args),env=env,check=True,**kwargs)
    success = False
    try:
        dc('up','-d','--wait','db',stdout=subprocess.DEVNULL)
        with (source/'database.dump').open('rb') as stream:
            dc('exec','-T','db','pg_restore','--exit-on-error','--no-owner','-U',r['KEYCLOAK_DB_USER'],'-d',r['KEYCLOAK_DB_NAME'],stdin=stream,stdout=subprocess.DEVNULL)
        dc('up','-d','--wait','--wait-timeout','300',stdout=subprocess.DEVNULL)
        container = dc('ps','-q','keycloak',capture_output=True,text=True).stdout.strip()
        inspect = json.loads(subprocess.check_output(['docker','inspect',container]))[0]
        assert not inspect['HostConfig'].get('PortBindings')
        network = next(iter(inspect['NetworkSettings']['Networks'].values()))
        net_info = json.loads(subprocess.check_output(['docker','network','inspect',network['NetworkID']]))[0]
        assert net_info['Internal']
        base = 'http://'+network['IPAddress']+':8080'
        # Requests originate on the host bridge; TLS edge is emulated solely in the isolated test.
        from urllib.request import Request, urlopen
        from urllib.parse import urlencode
        credentials = json.loads((scratch/'secrets/admin.json').read_text())
        def api(path,data=None,bearer=None):
            headers = {'X-Forwarded-Proto':'https','X-Forwarded-Host':r['KEYCLOAK_HOSTNAME'].split('://')[1],'X-Forwarded-Port':'443'}
            if bearer: headers['Authorization'] = 'Bearer '+bearer
            if data is not None:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                data = urlencode(data).encode()
            with urlopen(Request(base+path,data=data,headers=headers),timeout=30) as response: return json.load(response)
        bearer = api('/realms/master/protocol/openid-connect/token',{'grant_type':'password','client_id':'admin-cli','username':credentials['username'],'password':credentials['password']})['access_token']
        realm = api('/admin/realms/'+r['KEYCLOAK_REALM'],bearer=bearer)
        assert not realm['resetPasswordAllowed']
        clients = api('/admin/realms/'+r['KEYCLOAK_REALM']+'/clients',bearer=bearer)
        expected = {'moodle','flutter-desktop','launcher-windows','web-login','lrs-bridge'}
        assert {x['clientId'] for x in clients if x['clientId'] in expected} == expected
        assert all(not x['enabled'] for x in clients if x['clientId'] in expected)
        assert api('/realms/'+r['KEYCLOAK_REALM']+'/protocol/openid-connect/certs')['keys']
        assert not api('/admin/realms/master/users?username=stt-bootstrap&exact=true',bearer=bearer)
        evidence.write_text(json.dumps({'backup':source.name,'restored':True,'admin_original_password':True,
            'clients_disabled':True,'jwks':True,'internal_network':True,'published_ports':False},indent=2)+'\n')
        evidence.chmod(0o600)
        success = True
    finally:
        dc('down',stdout=subprocess.DEVNULL)
        if success:
            assert scratch.parent == evidence.parent.resolve() and scratch.name.startswith('authsom-restore-')
            shutil.rmtree(scratch)
    print('Isolated restoration verified; temporary containers, network and files removed')

if __name__ == '__main__': main()
