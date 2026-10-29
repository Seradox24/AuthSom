#!/usr/bin/env python3
"""Install this instance's backup timer from explicit profile and calendar."""
import argparse
import json
from pathlib import Path
import subprocess
from stt import ROOT, profile

p = argparse.ArgumentParser()
p.add_argument('--env-file',required=True)
p.add_argument('--calendar',required=True)
a = p.parse_args()
c = profile(a.env_file)
if any(x in a.calendar for x in '\r\n%'):
    raise ValueError('Invalid systemd calendar')
subprocess.run(['systemd-analyze','calendar',a.calendar],check=True,stdout=subprocess.DEVNULL)
name = c['COMPOSE_PROJECT_NAME']+'-backup'
command = ' '.join(json.dumps(x) for x in ['/usr/bin/python3',str(ROOT/'scripts/stt.py'),'--env-file',c['_profile'],'backup'])
units = {
    'service':'[Unit]\nDescription=Consistent AuthSom PostgreSQL backup\nRequires=docker.service\nAfter=docker.service\n[Service]\nType=oneshot\nUMask=0077\nExecStart='+command+'\n',
    'timer':'[Unit]\nDescription=Daily AuthSom backup\n[Timer]\nOnCalendar='+a.calendar+'\nPersistent=true\n[Install]\nWantedBy=timers.target\n'}
for suffix,content in units.items():
    path = Path('/etc/systemd/system')/(name+'.'+suffix)
    if path.exists() and path.read_text() != content:
        raise ValueError('Existing unit differs; review before replacing')
    path.write_text(content)
    path.chmod(0o644)
subprocess.run(['systemd-analyze','verify',name+'.service',name+'.timer'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now',name+'.timer'],check=True)
print('Backup timer installed: '+name)
