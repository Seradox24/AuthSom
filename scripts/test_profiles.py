#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
from stt import ROOT, compose, profile, render

with tempfile.TemporaryDirectory(prefix='authsom-profiles-') as temporary:
    root = Path(temporary)
    models = []
    for i in range(2):
        env = (ROOT/'.env.stt.example').read_text()
        env = env.replace('example-authsom-prod','isolated-'+str(i)).replace('auth.example.com','auth'+str(i)+'.example.com')
        env = env.replace('/srv/example',str(root/str(i))).replace('18081',str(18181+i))
        path = root/(str(i)+'.env')
        path.write_text(env)
        secret = root/str(i)/'secretos/authsom/prod'
        secret.mkdir(parents=True)
        (secret/'secrets.env').write_text('KEYCLOAK_DB_PASSWORD=fixture-only-not-a-real-password\n')
        c = profile(path)
        render(c)
        realm = json.loads((Path(c['CONFIG_ROOT'])/'import/educacion-realm.json').read_text())
        assert len(realm['clients']) == 5 and all(not x['enabled'] for x in realm['clients'])
        assert not realm['resetPasswordAllowed'] and '${' not in json.dumps(realm)
        model = json.loads(compose(c,'config','--format','json',capture_output=True).stdout)
        assert model['services']['keycloak']['ports'][0]['host_ip'] == '127.0.0.1'
        assert not model['services']['db'].get('ports')
        models.append(model)
    assert models[0]['name'] != models[1]['name']
    assert models[0]['networks']['default']['name'] != models[1]['networks']['default']['name']
    assert models[0]['services']['db']['volumes'][0]['source'] != models[1]['services']['db']['volumes'][0]['source']
    for before, after in [('https://auth1.example.com','http://auth1.example.com'),('18182','80'),
                          ('BACKUP_KEEP=7','BACKUP_KEEP=0'),('KEYCLOAK_DB_USER=keycloak','KEYCLOAK_DB_USER='),
                          ('@sha256:','@invalid:')]:
        invalid = root/'invalid.env'
        invalid.write_text(env.replace(before,after))
        try: profile(invalid)
        except ValueError: pass
        else: raise AssertionError('Invalid profile accepted')
print('Two isolated Compose configurations and five invalid profiles verified; no containers created')
