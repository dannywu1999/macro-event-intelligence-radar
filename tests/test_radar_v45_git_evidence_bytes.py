"""Receipt integrity across Git checkout settings; all Git writes stay in TEMP."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.stage1b_historical_campaign import radar_market_reaction as research


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = [dict(case_id='ecb-2025-06-05', event_date='2025-06-05',
                effective_date='2025-06-11', case_path=research.CASE,
                data_path=research.DATA, event_source=research.EVENT_SOURCE,
                data_source=research.DATA_SOURCE), *research.RESEARCH_CASES]


def load(cfg, packet_path, data_path):
    return research.load_case(packet_path, data_path,
        expected_event_source=cfg['event_source'],
        expected_market_data_source=cfg['data_source'],
        expected_event_date=cfg['event_date'],
        expected_effective_date=cfg['effective_date'], case_id=cfg['case_id'])


class GitEvidenceBytesTests(unittest.TestCase):
    def test_receipt_bytes_survive_windows_and_linux_git_checkout(self):
        attributes = ROOT / '.gitattributes'
        if not attributes.is_file():
            attributes = ROOT / 'docs/public_radar/GITATTRIBUTES'
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        with tempfile.TemporaryDirectory(prefix='ecb-git-evidence-') as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            (source / '.gitattributes').write_bytes(attributes.read_bytes())
            for cfg in CONFIGS:
                for path in (cfg['case_path'], cfg['data_path']):
                    target = source / path.relative_to(research.ROOT)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            def git(*args):
                return subprocess.run(['git', *args], cwd=source, env=env,
                    capture_output=True, check=True, timeout=10).stdout
            git('init', '-q')
            # Exercise the clean filter that corrupted the original release.
            git('-c', 'core.autocrlf=true', 'add', '.')
            for setting in ('false', 'true'):
                checkout = Path(directory) / ('checkout-' + setting)
                checkout.mkdir()
                git('-c', 'core.autocrlf=' + setting, 'checkout-index', '--all',
                    '--prefix=' + checkout.as_posix() + '/')
                for cfg in CONFIGS:
                    with self.subTest(setting=setting, case=cfg['case_id']):
                        csv_name = cfg['data_path'].relative_to(research.ROOT)
                        packet_name = cfg['case_path'].relative_to(research.ROOT)
                        expected = json.loads(cfg['case_path'].read_bytes())['market_data_sha256']
                        raw = (checkout / csv_name).read_bytes()
                        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                        self.assertEqual(git('show', ':' + csv_name.as_posix()), raw)
                        self.assertEqual(load(cfg, checkout / packet_name,
                                              checkout / csv_name)['status'], 'AVAILABLE')

    def test_normalized_or_missing_provider_bytes_remain_not_measured(self):
        with tempfile.TemporaryDirectory(prefix='ecb-invalid-evidence-') as directory:
            csv_path = Path(directory) / 'rates.csv'
            for cfg in CONFIGS:
                with self.subTest(case=cfg['case_id']):
                    original = cfg['data_path'].read_bytes()
                    self.assertIn(b'\r\n', original)
                    csv_path.write_bytes(original.replace(b'\r\n', b'\n'))
                    self.assertEqual(load(cfg, cfg['case_path'], csv_path)['status'],
                                     'NOT_MEASURED')
                    self.assertEqual(load(cfg, cfg['case_path'],
                        Path(directory) / 'missing.csv')['status'], 'NOT_MEASURED')


if __name__ == '__main__':
    unittest.main()
