#!/usr/bin/env python3
"""Explicit STT deployment profile. Never prints secrets or expanded Compose."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

def read_env(path):
    result = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result:
            raise ValueError('Invalid or duplicate profile key')
        if any(c in value for c in '\r\n$`\x00'):
            raise ValueError('Unsupported profile expansion')
        result[key] = value
    return result

def profile(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Profile path must be absolute')
    c = read_env(path)
    required = ['COMPOSE_PROJECT_NAME','KEYCLOAK_IMAGE','POSTGRES_IMAGE','KEYCLOAK_HOSTNAME',
                'KEYCLOAK_HTTP_PORT','KEYCLOAK_REALM','KEYCLOAK_REALM_DISPLAY_NAME',
                'KEYCLOAK_DB_NAME','KEYCLOAK_DB_USER','CONFIG_ROOT','SECRET_ROOT','DATA_ROOT',
                'BACKUP_ROOT','BACKUP_KEEP']
    if any(not c.get(k) for k in required):
        raise ValueError('Missing required profile option')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]+', c['COMPOSE_PROJECT_NAME']):
        raise ValueError('Invalid Compose identity')
    for key in ['KEYCLOAK_REALM','KEYCLOAK_DB_NAME','KEYCLOAK_DB_USER']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', c[key]):
            raise ValueError('Invalid identifier: '+key)
    u = urlsplit(c['KEYCLOAK_HOSTNAME'])
    if u.scheme != 'https' or not u.hostname or u.path or u.query or u.fragment or u.username or u.port:
        raise ValueError('Public hostname must be an HTTPS origin')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', u.hostname):
        raise ValueError('Invalid public DNS name')
    if not 1024 <= int(c['KEYCLOAK_HTTP_PORT']) <= 65535 or not 1 <= int(c['BACKUP_KEEP']) <= 100:
        raise ValueError('Invalid port or retention')
    roots = [Path(c[k]) for k in ['CONFIG_ROOT','SECRET_ROOT','DATA_ROOT','BACKUP_ROOT']]
    if any(not p.is_absolute() or p == Path('/') or '..' in p.parts for p in roots):
        raise ValueError('Explicit absolute non-root directories required')
    for i, p in enumerate(roots):
        for q in roots[i+1:]:
            if p == q or p in q.parents or q in p.parents:
                raise ValueError('Installation areas must not overlap')
    for key in ['KEYCLOAK_IMAGE','POSTGRES_IMAGE']:
        if not re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}', c[key]):
            raise ValueError('Images must be pinned by digest')
    secret_path = Path(c['SECRET_ROOT'])/'secrets.env'
    secrets = read_env(secret_path)
    if set(c) & set(secrets):
        raise ValueError('Duplicate public/private profile option')
    c.update(secrets)
    if not c.get('KEYCLOAK_DB_PASSWORD'):
        raise ValueError('Database password required')
    if bool(c.get('KEYCLOAK_ADMIN_USERNAME')) != bool(c.get('KEYCLOAK_ADMIN_PASSWORD')):
        raise ValueError('Bootstrap credentials must be supplied together')
    if any(k in os.environ for k in c):
        raise ValueError('Managed environment variables must not be exported')
    c['_profile'] = str(path)
    c['_secrets'] = str(secret_path)
    return c

def compose(c, *args, **kwargs):
    env = dict(os.environ)
    env.update({k:v for k,v in c.items() if not k.startswith('_')})
    command = ['docker','compose','--project-directory',str(ROOT),
        '--env-file',c['_profile'],'--env-file',c['_secrets'],'-f',str(ROOT/'compose.stt.yaml'),
        '-p',c['COMPOSE_PROJECT_NAME']]
    if c.get('KEYCLOAK_ADMIN_PASSWORD'):
        command += ['-f',str(ROOT/'compose.bootstrap.yaml')]
    return subprocess.run(command+list(args), env=env, check=True, **kwargs)

def render(c):
    realm = json.loads((ROOT/'keycloak/educacion-realm.json').read_text())
    realm.update(realm=c['KEYCLOAK_REALM'], displayName=c['KEYCLOAK_REALM_DISPLAY_NAME'],
                 resetPasswordAllowed=False)
    for client in realm['clients']:
        client['enabled'] = False
        client.pop('secret', None)
        client['redirectUris'] = []
        client['webOrigins'] = []
        client.get('attributes', {}).pop('post.logout.redirect.uris', None)
    destination = Path(c['CONFIG_ROOT'])/'import'
    destination.mkdir(parents=True, exist_ok=True, mode=0o755)
    target = destination/(c['KEYCLOAK_REALM']+'-realm.json')
    target.write_text(json.dumps(realm, indent=2)+'\n')
    target.chmod(0o644)

def nginx(c, tls):
    host = urlsplit(c['KEYCLOAK_HOSTNAME']).hostname
    print('server { listen 80; listen [::]:80; server_name '+host+'; location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; } location / { return '+('301 https://'+host+'$request_uri' if tls else '503')+'; } }')
    if tls:
        print('server { listen 443 ssl; listen [::]:443 ssl; http2 on; server_name '+host+'; ssl_certificate /etc/letsencrypt/live/'+host+'/fullchain.pem; ssl_certificate_key /etc/letsencrypt/live/'+host+'/privkey.pem; ssl_protocols TLSv1.2 TLSv1.3; ssl_session_tickets off; client_max_body_size 10m; location ~ ^/(health|metrics)(/|$) { return 404; } location / { proxy_pass http://127.0.0.1:'+c['KEYCLOAK_HTTP_PORT']+'; proxy_http_version 1.1; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-Host $host; proxy_set_header X-Forwarded-Port 443; proxy_set_header Forwarded ""; proxy_read_timeout 90s; } }')

def backup(c):
    import fcntl
    os.umask(0o077)
    destination = Path(c['BACKUP_ROOT']).resolve()
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (destination/'.backup.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        states = compose(c,'ps','--format','json','keycloak','db',capture_output=True,text=True).stdout
        services = [json.loads(line) for line in states.splitlines() if line.strip()]
        if len(services) != 2 or any(s.get('State') != 'running' or s.get('Health') != 'healthy' for s in services):
            raise ValueError('Both services must be running and healthy before backup')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        pending = destination/(stamp+'.partial')
        pending.mkdir(mode=0o700)
        try:
            compose(c, 'stop','--timeout','30','keycloak', stdout=subprocess.DEVNULL)
            with (pending/'database.dump').open('wb') as stream:
                compose(c,'exec','-T','db','pg_dump','-Fc','-U',c['KEYCLOAK_DB_USER'],c['KEYCLOAK_DB_NAME'],stdout=stream)
            for key, label in [('CONFIG_ROOT','configuration'),('SECRET_ROOT','secrets')]:
                with tarfile.open(pending/(label+'.tar.gz'),'w:gz') as archive:
                    archive.add(c[key],arcname=label)
            (pending/'images.json').write_text(json.dumps({k:c[k] for k in ['KEYCLOAK_IMAGE','POSTGRES_IMAGE']}))
            (pending/'revision.txt').write_bytes(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']))
            subprocess.run(['git','-C',str(ROOT),'bundle','create',str(pending/'source.bundle'),'HEAD'],check=True)
        finally:
            compose(c,'start','--wait','--wait-timeout','300','keycloak',stdout=subprocess.DEVNULL)
        checks = []
        for file in sorted(pending.iterdir()):
            with file.open('rb') as stream:
                checks.append(hashlib.file_digest(stream,'sha256').hexdigest()+'  '+file.name)
        (pending/'SHA256SUMS').write_text('\n'.join(checks)+'\n')
        subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=pending,check=True,stdout=subprocess.DEVNULL)
        pending.rename(destination/stamp)
        complete = sorted(p for p in destination.iterdir() if re.fullmatch(r'\d{8}_\d{6}',p.name) and p.is_dir() and not p.is_symlink() and (p/'SHA256SUMS').is_file())
        for old in complete[:-int(c['BACKUP_KEEP'])]:
            if old.resolve().parent != destination:
                raise ValueError('Invalid retention target')
            shutil.rmtree(old)
        print('Complete backup verified: '+stamp)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--env-file',required=True)
    p.add_argument('action',choices=['check','render','nginx','backup','up','restart'])
    p.add_argument('--tls',action='store_true')
    a = p.parse_args()
    c = profile(a.env_file)
    if a.action == 'check':
        model = json.loads(compose(c,'config','--format','json',capture_output=True).stdout)
        app = model['services']['keycloak']
        assert len(app['ports']) == 1 and app['ports'][0]['host_ip'] == '127.0.0.1'
        assert not model['services']['db'].get('ports')
        assert all(not x.get('container_name') for x in model['services'].values())
        print('Profile, images, isolation and loopback valid')
    elif a.action == 'render': render(c)
    elif a.action == 'nginx': nginx(c,a.tls)
    elif a.action == 'backup': backup(c)
    elif a.action == 'up': compose(c,'up','-d','--wait','--wait-timeout','300')
    elif a.action == 'restart': compose(c,'restart','--wait','--wait-timeout','300')

if __name__ == '__main__':
    main()
