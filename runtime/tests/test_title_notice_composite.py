"""Composite after native menu foreground sprites, before that render target is submitted."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class NoticeCompositeTests(unittest.TestCase):
    def test_only_the_final_menu_submission_composites_the_notice(self):
        header=ROOT/'runtime/source/title_notice_composite.hpp'
        self.assertTrue(header.exists(),'final menu composition point is missing')
        body=r'''
#include "title_notice_composite.hpp"
#include <string>
using namespace isaac::runtime::notice;
int main() {
    std::string order="title";unsigned draws=0;
    const auto draw=[&]{order+=",notice";++draws;};
    const std::uintptr_t base=0x7100000000;
    const auto expected=base+0x3FEB5C;
    if(kMenuForegroundReturnOffset!=0x3FEB5C)return 3;
    CompositeAfterForeground(base+0x3fe8b0,expected,draw); // title child completed
    order+=",foreground";
    CompositeAfterForeground(expected,expected,draw);
    order+=",present";
    if(order!="title,foreground,notice,present"||draws!=1)return 1;
    CompositeAfterForeground(base+0x3f9b44,expected,draw); // regular MC_POST_RENDER
    CompositeAfterForeground(0,0,draw); // unconfigured / unsupported build
    if(draws!=1)return 2;
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='notice-composite-')as tmp:
            p=Path(tmp);(p/'test.cpp').write_text(body)
            r=subprocess.run([shutil.which('c++'),'-std=c++17','-Wall','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
