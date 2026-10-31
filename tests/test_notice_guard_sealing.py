"""Policy constants and weak inline state cannot remain a replaceable ABI."""
import unittest
from tools.seal_notice_guard import local_symbols, PUBLIC_NOTICE_ABI


class NoticeGuardSealingTests(unittest.TestCase):
    def test_preserves_only_required_notice_entries_and_seals_policy_data(self):
        private = [
            '_ZN5isaac7runtime6notice13kLocaleAssetsE',
            '_ZN5isaac7runtime6notice9integrity17IsOwnedNoticePathEPKc',
            '_ZN5isaac7runtime6notice5State4TickEjbbj',
            'g_NoticeIntegrityExpectedRoot', 'sha256ContextGetHash', 'memcmp', 'memmove',
        ]
        lines = [f'00000000 u {name}' for name in private]
        lines += [f'00000000 T {name}' for name in PUBLIC_NOTICE_ABI]
        lines += ['00000000 T g_NoticeIntegrityState', '00000000 T unrelated_entry']
        self.assertEqual(set(local_symbols('\n'.join(lines))), set(private))
