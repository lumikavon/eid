"""生成明确白名单候选源码及校验清单，不包含运行时密钥。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.remote_environment import ROOT, source_files, source_digest


def prepare(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('候选目录已存在，拒绝覆盖')
    files = source_files(ROOT)
    for name in ('deployment/pack.compose.yaml', 'deployment/ocr-weights/README.md'):
        files[name] = (ROOT / name).read_bytes()
    for path in (ROOT / 'tests').rglob('*.py'):
        if '__pycache__' not in path.parts and not path.is_symlink():
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    output.mkdir(parents=True)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    metadata = {'schema_version': 1, 'source_sha256': source_digest(files), 'files': manifest,
                'baseline': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'target': 'openEuler 24.03 LTS-SP2', 'runtime_verified': False}
    (output / 'SOURCE.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    hashes = manifest | {'SOURCE.json': hashlib.sha256((output / 'SOURCE.json').read_bytes()).hexdigest()}
    (output / 'SOURCE.sha256').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())), encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), ensure_ascii=False))
