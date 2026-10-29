#!/usr/bin/env python3
"""Initial admin transition and read-only contract verification over HTTPS."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from stt import profile

def request(url, data=None, token=None, method=None, form=False):
    headers = {}
    if token: headers['Authorization'] = 'Bearer '+token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urlencode(data) if form else json.dumps(data)).encode()
    with urlopen(Request(url,data=data,headers=headers,method=method),timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None

def token(base, user, password):
    return request(base+'/realms/master/protocol/openid-connect/token',
        {'grant_type':'password','client_id':'admin-cli','username':user,'password':password},form=True)['access_token']

def verify(c, credentials):
    base = c['KEYCLOAK_HOSTNAME']
    bearer = token(base,credentials['username'],credentials['password'])
    realm = c['KEYCLOAK_REALM']
    settings = request(base+'/admin/realms/'+realm,token=bearer)
    assert not settings['resetPasswordAllowed'] and not settings['registrationAllowed']
    clients = request(base+'/admin/realms/'+realm+'/clients',token=bearer)
    expected = {'moodle','flutter-desktop','launcher-windows','web-login','lrs-bridge'}
    assert {x['clientId'] for x in clients if x['clientId'] in expected} == expected
    assert all(not x['enabled'] for x in clients if x['clientId'] in expected)
    discovery = request(base+'/realms/'+realm+'/.well-known/openid-configuration')
    assert discovery['issuer'] == base+'/realms/'+realm
    assert discovery['authorization_endpoint'].startswith(base+'/')
    assert request(discovery['jwks_uri'])['keys']
    admins = request(base+'/admin/realms/master/users?username='+credentials['username']+'&exact=true',token=bearer)
    assert len(admins) == 1 and admins[0]['enabled']
    assert not request(base+'/admin/realms/master/users?username=stt-bootstrap&exact=true',token=bearer)
    try:
        request(base+'/admin/realms/'+realm)
        raise AssertionError('Anonymous administration allowed')
    except HTTPError as e:
        assert e.code == 401
    print('HTTPS admin, issuer, JWKS, disabled clients and bootstrap removal verified')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--env-file',required=True)
    p.add_argument('--initialize',action='store_true')
    a = p.parse_args()
    c = profile(a.env_file)
    credentials = json.loads((Path(c['SECRET_ROOT'])/'admin.json').read_text())
    base = c['KEYCLOAK_HOSTNAME']
    if a.initialize:
        bearer = token(base,c['KEYCLOAK_ADMIN_USERNAME'],c['KEYCLOAK_ADMIN_PASSWORD'])
        existing = request(base+'/admin/realms/master/users?username='+credentials['username']+'&exact=true',token=bearer)
        if existing: raise ValueError('Permanent account already exists; initialization refused')
        request(base+'/admin/realms/master/users',{
            'username':credentials['username'],'enabled':True,
            'credentials':[{'type':'password','value':credentials['password'],'temporary':False}]},token=bearer)
        user = request(base+'/admin/realms/master/users?username='+credentials['username']+'&exact=true',token=bearer)[0]
        role = request(base+'/admin/realms/master/roles/admin',token=bearer)
        request(base+'/admin/realms/master/users/'+user['id']+'/role-mappings/realm',[role],token=bearer)
        permanent = token(base,credentials['username'],credentials['password'])
        assert request(base+'/admin/realms/master/roles/admin',token=permanent)['name'] == 'admin'
        old = request(base+'/admin/realms/master/users?username='+c['KEYCLOAK_ADMIN_USERNAME']+'&exact=true',token=permanent)[0]
        request(base+'/admin/realms/master/users/'+old['id'],token=permanent,method='DELETE')
    verify(c,credentials)

if __name__ == '__main__': main()
