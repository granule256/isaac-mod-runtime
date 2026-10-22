#pragma once
#include <string_view>
namespace isaac::runtime::shader_identity {
enum class Kind : unsigned char { None, Copy, Pixelation };
// 已核对的完整作者程序，仅以源码和接口识别，不依赖owner或shader名称。
// 来源：BOIStageAPI15/content/shaders.xml。加载时比较；帧上不解析GLSL。
inline constexpr std::string_view kCopyVertex = R"GLSL(
            attribute vec3 Position;
            attribute vec4 Color;
            attribute vec2 TexCoord;
            attribute vec4 RenderData;
            attribute float Scale;

            varying lowp vec4 Color0;
            varying mediump vec2 TexCoord0;
            varying lowp vec4 RenderDataOut;
            varying lowp float ScaleOut;
            uniform sampler2D Texture0;

            uniform mat4 Transform;
            void main(void)
            {
                RenderDataOut = RenderData;
                ScaleOut = Scale;
                Color0 = Color;
                TexCoord0 = TexCoord;
                gl_Position = Transform * vec4(Position.xyz, 1.0);
            }
        )GLSL";
inline constexpr std::string_view kCopyFragment = R"GLSL(
            varying lowp vec4 Color0;
            varying mediump vec2 TexCoord0;
            varying lowp vec4 RenderDataOut;
            varying lowp float ScaleOut;
            uniform sampler2D Texture0;
            void main(void)
            {
                vec4 Color = Color0 * texture2D(Texture0, TexCoord0);
                gl_FragColor = Color;
            }
        )GLSL";
inline constexpr std::string_view kPixelVertex = R"GLSL(

    attribute vec3 Position;
    attribute vec4 Color;
    attribute vec2 TexCoord;
    attribute float PixelAmount;
    attribute vec4 RenderData;
    attribute float Scale;

    varying vec4 Color0;
    varying vec2 TexCoord0;
    varying float OutPixelAmount;
    varying vec4 RenderDataOut;
    varying float ScaleOut;

    uniform mat4 Transform;

    void main(void) {
        OutPixelAmount = PixelAmount;
        RenderDataOut = RenderData;
        Color0 = Color;
        gl_Position = Transform * vec4(Position.xyz, 1.0);
        TexCoord0 = TexCoord;
    }
    )GLSL";
inline constexpr std::string_view kPixelFragment = R"GLSL(
    varying vec4 Color0;
    varying vec2 TexCoord0;
    varying float OutPixelAmount;
    varying vec4 RenderDataOut;
    varying float ScaleOut;
    uniform sampler2D Texture0;

    void main(void)
    {
    if (OutPixelAmount > 0.001) {
        vec2 pa = OutPixelAmount * 0.5 * min(RenderDataOut.z, RenderDataOut.w) / RenderDataOut.zw;

        vec2 center = RenderDataOut.xy * 0.5 / RenderDataOut.zw;
        vec2 snapCoord = TexCoord0.st - mod(TexCoord0.st - center, pa) + pa * 0.5;

        vec4 Color = Color0 * texture2D(Texture0, snapCoord);

        gl_FragColor = Color; //Color0 * texture2D(Texture0, snapCoord);
    } else {
        vec4 Color = Color0 * texture2D(Texture0, TexCoord0);
        gl_FragColor = Color; //Color0 * texture2D(Texture0, TexCoord0);
    }
    }
    )GLSL";

inline bool Space(char c){return c==' '||c=='\t'||c=='\r'||c=='\n';}
inline bool Word(char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';}
inline std::string_view Token(std::string_view& source) {
 while(!source.empty()) {
  if(Space(source.front())){source.remove_prefix(1);continue;}
  if(source.substr(0,2)=="//"){
   const auto end=source.find('\n');source=end==source.npos?std::string_view{}:source.substr(end+1);continue;
  }
  if(source.substr(0,2)=="/*"){
   const auto end=source.find("*/",2);if(end==source.npos)return source;source.remove_prefix(end+2);continue;
  }
  break;
 }
 if(source.empty())return {};
 std::size_t n=1;
 const char c=source.front();
 if((c>='0'&&c<='9')||(c=='.'&&source.size()>1&&source[1]>='0'&&source[1]<='9')){
  while(n<source.size()){
   const char next=source[n],previous=source[n-1];
   if(Word(next)||next=='.'||((next=='+'||next=='-')&&(previous=='e'||previous=='E'||previous=='p'||previous=='P')))++n;
   else break;
  }
 }else if(Word(c)){
  while(n<source.size()&&Word(source[n]))++n;
 }else {
  const auto two=source.substr(0,2),three=source.substr(0,3);
  if(three=="<<="||three==">>=")n=3;
  else if(two=="++"||two=="--"||two=="<="||two==">="||two=="=="||two=="!="||
          two=="&&"||two=="||"||two=="^^"||two=="<<"||two==">>"||
          two=="+="||two=="-="||two=="*="||two=="/="||two=="%="||two=="&="||two=="|="||two=="^=")n=2;
 }
 const auto token=source.substr(0,n);source.remove_prefix(n);return token;
}
inline bool SameCode(std::string_view left,std::string_view right) {
 for(;;){const auto a=Token(left),b=Token(right);if(a!=b)return false;if(a.empty())return true;}
}
inline Kind Classify(std::string_view vertex,std::string_view fragment) {
 if(SameCode(vertex,kCopyVertex)&&SameCode(fragment,kCopyFragment))return Kind::Copy;
 if(SameCode(vertex,kPixelVertex)&&SameCode(fragment,kPixelFragment))return Kind::Pixelation;
 return Kind::None;
}
} // namespace isaac::runtime::shader_identity
