"""NVN分离顶点阶段需要显式内置输出块；经真实XML转换链检查送入编译器的文本。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_shader_pipeline import HARNESS, ROOT


class ShaderVertexInterfaceTests(unittest.TestCase):
    def test_stageapi_and_capture_vertex_redeclare_position(self):
        guard = '''if(!std::strstr(view.vertex,"out gl_PerVertex") || !std::strstr(view.vertex,"vec4 gl_Position;")){std::fputs("missing separable vertex position interface\\n",stderr);return false;}if(std::strstr(std::strstr(view.vertex,"out gl_PerVertex")+1,"out gl_PerVertex") || std::strstr(view.fragment,"out gl_PerVertex"))return false;'''
        source = HARNESS.replace('bool Compile(const ShaderProgramView& view,void** out){',
                                 'bool Compile(const ShaderProgramView& view,void** out){' + guard)
        with tempfile.TemporaryDirectory(prefix='isaac-shader-interface-') as folder:
            cpp, exe = Path(folder)/'interface.cpp', Path(folder)/'interface'
            cpp.write_text(source)
            result = subprocess.run(['c++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                                     '-I'+str(ROOT/'runtime/src'), str(cpp),
                                     str(ROOT/'runtime/src/application/shader/shader_pipeline.cpp'),
                                     '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            cases = [[], [str(ROOT/'analysis/mod-corpus/BOIStageAPI15/content/shaders.xml')]]
            for index, prefix in enumerate(['out gl_PerVertex { vec4 gl_Position; };',
                                            '// gl_PerVertex\n/* gl_PerVertex */\n',
                                            'float gl_PerVertexSuffix;']):
                xml = Path(folder)/f'input{index}.xml'
                xml.write_text('<shaders><shader name="Alpha"><parameters/>'
                               '<vertex><![CDATA['+prefix+'\nuniform mat4 Transform;attribute vec3 Position;'
                               'void main(){gl_Position=Transform*vec4(Position,1.);}]]></vertex>'
                               '<fragment><![CDATA[void main(){gl_FragColor=vec4(1.);}]]></fragment>'
                               '</shader></shaders>')
                cases.append([str(xml)])
            for args in cases:
                with self.subTest(args=args):
                    result = subprocess.run([str(exe), *args], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
