# 项目介绍视频制作脚本

也就是说，这组脚本把已经核对过的 Switch 实机录像做成 OpenFilm 工程，通过原生字幕和导出队列交付两分钟中文字幕版。

制作设计、安装过程、失败与修正、最终核验见 `docs/项目介绍视频OpenFilm制作-20261024.md`。原九段录像和 2026-10-21 母版均保留；这一版没有哈基米旁白，使用原创器乐背景音乐。

## 文件与职责

- `captions.json`：29条按阅读节奏安排的介绍字幕，连续覆盖0—120秒。
- `chapter.html`：1920×1080透明章节包装，按时间绘制开场/结尾卡、章节与进度；控制台两段分别标注2倍/1.5倍速。
- `build_film.py`：沿用已确认的素材入点，复制三段原片、核对SHA256，生成21段实机剪辑和8章包装、原创音乐、WebVTT/SRT与素材清单。
- `studio_control.py`：读取本机OpenFilm启动信息，通过其自带API设置字幕样式、提交后台导出、取状态；不输出本机启动密钥。
- `verify_film.py`：正式导出后核对1080p60、7200帧、120秒、29条字幕、原片/副本SHA256，完整解码音视频并检测音量。

## 当前固定环境

工具是 `openfilm@0.2.5`，安装在 `/Users/kelinls/.local/share/isaac-video-tools/openfilm`；Node23.11.0，FFmpeg为已有本机版本。OpenFilm Studio主服务4747，素材预览服务4748，后续以本机实际启动结果为准。

默认工程：`/Users/kelinls/Movies/项目介绍-OpenFilm-20261024`。原片序号沿用旧制作方案的九段Movies顶层MOV，数量改变时脚本拒绝继续，以免使用错误素材。工程素材为独立实文件，不使用指向外部目录的符号链接。

## 使用顺序

```sh
node /Users/kelinls/.local/share/isaac-video-tools/openfilm/node_modules/openfilm/bin/openfilm.mjs open /Users/kelinls/Movies/项目介绍-OpenFilm-20261024
python3 tools/video_intro_20261024/build_film.py
python3 tools/video_intro_20261024/studio_control.py style
python3 tools/video_intro_20261024/studio_control.py preview
```

`preview`提交逐章带字幕画面和五秒技术样片后即返回，编码在后台进行。检查画面、字幕安全边界和素材对应关系后再执行：

```sh
python3 tools/video_intro_20261024/studio_control.py render
python3 tools/video_intro_20261024/studio_control.py status
```

`status`仅取得当前快照，不应循环忙等。正式任务显示done以后，异步运行最终核验：

```sh
python3 tools/video_intro_20261024/verify_film.py
```

核验结果保存于工程的`核验/`；没有完整解码和关键画面检查之前，不将任务提交成功视为成片完成。修改工程时先读取用户最新的film.html与页面，不用生成脚本覆盖用户手动编辑；这组脚本用于本次初次制作及另建版本的复现。

## 字幕与声音

每条原片视频均`muted`，唯一音轨为脚本生成的低音量分解和弦，没有用户原声或其他人声。与背景音乐同名的WebVTT保存介绍文字，让无旁白视频也能使用OpenFilm原生可编辑字幕，不把这些文字描述成音乐的语音转写。

原生导出必须启用`burnSubtitles: true`，否则普通CLI的`render`只输出画面而不会烧录Studio字幕。导出还生成独立SRT。字幕位置通过原生API设置为画面高度的95%，字号约42像素；实际逐章画面已用于查找和纠正初稿下沿裁切，不能仅凭位置数字判断安全。

## 检查范围

只核验媒体与本轮新脚本，不运行游戏全量或fast门禁。OpenFilm的look对九个抽样时刻分别乱序绘制两次，检查确定性；这与对7200帧成片完整解码是两个不同判据，不冒称全部画面已逐帧人工观看。
