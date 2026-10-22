"""生产事实：早装入口有单独状态，不能用普通安装状态否定其成功。"""
import subprocess,unittest
from unittest.mock import patch
from . import test_startup_mod_image_resources as base
class EarlyImageResourcesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  driver=base.DRIVER.replace('return id==HookId::ImagePcxLoad && installed;','return id==HookId::ContentGetMountedFilePath || (id==HookId::ImagePcxLoad && installed);')
  old='bool EntryRelayInstalled(HookId id)noexcept{return id==HookId::ContentGetMountedFilePath || (id==HookId::ImagePcxLoad && installed);}'
  assert old in driver
  driver=driver.replace(old,'bool EntryRelayInstalled(HookId)noexcept{return false;}')
  with patch.object(base,'DRIVER',driver):base.StartupModImageResourcesTests.setUpClass.__func__(cls)
 @classmethod
 def tearDownClass(cls):base.StartupModImageResourcesTests.tearDownClass.__func__(cls)
 def test_early_path_and_image_success_are_used_without_reinstall(self):
  f=base.ROOT/'dist/change-archive-20261012/440-minimap-curse-questionmark-diagnosis'
  result=subprocess.run([str(self.binary),'enabled',str(f/'native-questionmark.pcx'),str(f/'mod-transparent-original.png')],cwd=self.work,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
