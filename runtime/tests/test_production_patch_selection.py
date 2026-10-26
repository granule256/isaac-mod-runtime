"""用真实GNU Make条件规则核对生产与诊断选择，防止旧IPS先改写动态入口。"""
from pathlib import Path
import re,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
class ProductionPatchSelectionTests(unittest.TestCase):
 def selected(self,stage=''):
  text=(ROOT/'runtime/Makefile').read_text();section=text[text.index('# Module deployments use'):text.index('# 每份SDK都按其实际NSO占用配预算')]
  variables=set(re.findall(r'\$\((DEPLOY_[A-Z_]+)\)',section))
  prefix='SALTYNX_PLUGIN=0\nLAYERED_RUNTIME=1\nSKIP_DEFAULT_PC_MODS=1\nBUILD=build\nDIAGNOSTIC_STAGE='+stage+'\n'+''.join(f'{v}:={v}\n' for v in variables)
  with tempfile.TemporaryDirectory()as tmp:
   path=Path(tmp)/'Makefile';path.write_text(prefix+section+'\nall:\n\t@echo SELECTED: $^\n%:\n\t@:\n')
   r=subprocess.run(['make','-n','-s','-f',str(path),'all'],capture_output=True,text=True)
   self.assertNotIn('***',r.stderr,r.stderr)
   return set(re.search(r'SELECTED: (.*)$',r.stdout,re.M).group(1).split())
 def test_production_does_not_emit_legacy_entry_patches(self):
  selected=self.selected()
  for key in ['DEPLOY_RELAY_IPS','DEPLOY_RENDER_RELAY_IPS','DEPLOY_RENDER_PRESENT_RELAY_IPS','DEPLOY_PRE_GET_COLLECTIBLE_RELAY_IPS','DEPLOY_REBUILD_MOUNT_POINTS_RELAY_IPS']:self.assertNotIn(key,selected)
  self.assertIn('DEPLOY_LIFECYCLE_RELAY_IPS',selected);self.assertIn('DEPLOY_NATIVE_HEAP_IPS',selected)
 def test_diagnostics_keep_their_original_ips(self):
  self.assertIn('DEPLOY_RELAY_IPS',self.selected('13'))
  self.assertNotIn('DEPLOY_RELAY_IPS',self.selected('127'))
  self.assertIn('DEPLOY_SAVE_LOAD_RELAY_IPS',self.selected('127'))
if __name__=='__main__':unittest.main()
