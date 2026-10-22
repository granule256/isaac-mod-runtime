"""旧内嵌菜单不能从正常或失败路径重新注册，原生模组页继续使用共享服务。"""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
class EmbeddedModMenuRemovalTests(unittest.TestCase):
    def test_no_embedded_registration_or_fallback(self):
        for name in ('hook_manager.cpp', 'lua_runtime.cpp', 'lua_runtime.hpp'):
            text = (ROOT/'runtime/source'/name).read_text()
            for retired in ('LoadEmbeddedMenuMod', 'InitializeEmbeddedMenuMod', 'kEmbeddedModMenuScript', 'g_LoadingEmbeddedMod'):
                self.assertNotIn(retired, text, f'{name}仍可装入旧菜单: {retired}')
        self.assertFalse((ROOT/'runtime/source/program/embedded_mod_menu_script.hpp').exists())
    def test_native_menu_keeps_shared_toggle_service(self):
        text = (ROOT/'runtime/source/mod_menu_native.cpp').read_text()
        for entry in ('ModMenuSetEnabled', 'ModMenuSaveToggles', 'ModMenuDiscoveredDirectory'):
            self.assertIn(entry, text)
if __name__ == '__main__':
    unittest.main()
