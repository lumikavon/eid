"""为 seadee-test 新候选生成隔离 Compose；不读取或接管既有部署。"""
import argparse
import json
from pathlib import Path
import secrets
import yaml

from scripts.remote_environment import image_source_fingerprint


def prepare(candidate, output, project):
    import re
    if not re.fullmatch(r'eid-epic5-[a-z0-9-]+', project):
        raise ValueError('测试项目名称无效')
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('运行目录已存在，拒绝覆盖')
    manifest = json.loads((candidate / 'SOURCE.json').read_text(encoding='utf-8'))
    files = {name: (candidate / name).read_bytes() for name in manifest['files']}
    import hashlib
    if any(hashlib.sha256(data).hexdigest() != manifest['files'][name] for name, data in files.items()):
        raise ValueError('候选校验失败')
    compose = yaml.safe_load(files['deployment/compose.yaml'])
    compose['name'] = project
    owner = secrets.token_hex(16)
    fingerprints = {name: image_source_fingerprint(name, files) for name in ('api', 'worker', 'web')}
    root = candidate.as_posix()
    for name, service in compose['services'].items():
        service['labels'] = {'io.eid.owner': owner, 'io.eid.environment': 'seadee-test'}
        service.pop('ports', None)
        if name in ('api', 'worker', 'worker-scheduler', 'web'):
            source = 'worker' if name == 'worker-scheduler' else name
            service['image'] = f'{project}-{source}:{fingerprints[source][7:23]}'
            service.pop('build', None)
        mounts = service.get('volumes', [])
        service['volumes'] = [root + '/deployment/' + mount[2:] if mount.startswith('./') else mount
                              for mount in mounts]
    compose['services']['postgres']['ports'] = ['127.0.0.1:25432:5432']
    compose['services']['nginx']['ports'] = ['127.0.0.1:28080:8080']
    for name in ('rabbitmq', 'redis'):
        compose['services'][name]['volumes'] = [f'eid-{name}:' + ('/var/lib/rabbitmq' if name == 'rabbitmq' else '/data')]
        compose['volumes'][f'eid-{name}'] = {}
    compose['services']['rabbitmq']['healthcheck']['timeout'] = '20s'
    for name, volume in compose['volumes'].items():
        volume.update(name=f'{project}-{name.removeprefix("eid-")}',
                      labels={'io.eid.owner': owner, 'io.eid.environment': 'seadee-test'})
    compose['networks'] = {'default': {'name': project + '_default', 'labels': {'io.eid.owner': owner}}}
    output.mkdir(parents=True, mode=0o700)
    (output / 'compose.yaml').write_text(yaml.safe_dump(compose, sort_keys=False, width=4096), encoding='utf-8')
    (output / 'runtime.env').write_text(
        f'EID_EVIDENCE_WAKE_KEY={secrets.token_hex(32)}\nEID_MODEL_WAKE_KEY={secrets.token_hex(32)}\n',
        encoding='utf-8')
    (output / 'runtime.env').chmod(0o600)
    receipt = {'project': project, 'source_sha256': manifest['source_sha256'], 'fingerprints': fingerprints,
               'runtime_verified': False}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.candidate, args.output, args.project)))
