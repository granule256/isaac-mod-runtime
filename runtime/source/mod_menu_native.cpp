#include "application/shader/mod_shader_loader.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "interfaces/lua/rplus_content_names.hpp"
// 生产版：「模组」那一行 + 模组页（换字体那段接线已按真机结论撤掉）。设计与纪律见同名 `.hpp`。
//
// **行为真值源**：`runtime/source/probe/native_mods_menu_probe.cpp`（3021 行，真机验收过一轮）。
// 本文件按它的行为重写、去掉诊断，逐处保留"为什么这么做"的依据；几处刻意的差别写在 `.hpp` 里，
// 并在下面各自的位置重复一遍理由。
//
// 本 TU **不做编译期门控**：三个入口回调必须常编存在（`entry_relay_hook_adapter.cpp` 的
// `RegisterEntryRelayCallbacks` 无条件取它们的地址）。探针与生产的互斥在**安装**这一层：
// 探针构建里由 `hook_manager.cpp` 的 `SkipOptionalHooksPredicate` 跳过这三个挂点，
// 探针自己那套 `TryInstallEntryRelay` 照旧生效。
//
// ## 和引擎打交道的方式（2026-09-24 批次 105 建内存侧、批次 108 补齐调用侧）
//
// 本 TU 的**引擎读、引擎写、整数↔指针转换全部走引擎内存访问层**
// （`runtime/src/infrastructure/memory/engine_field_access.hpp`）：回绕检查、可读/可写判定、
// 取值与落值只在那一个地方发生，这里只写"读/写哪个对象的哪个偏移"。
//
// **"调一个引擎函数"走引擎调用层**（`runtime/src/infrastructure/call/engine_call_access.hpp`，
// 批次 108）：本 TU 的 `VerifiedEntry<Fn>(...)` 一次做完"范围 + 可读 + 逐字节核对序言 +
// 转成带签名的函数指针"，任一条不过就给 `nullptr`。**调用点里不再出现 `reinterpret_cast<签名>`**。
//
//   * 为什么（内存那一半）：诊断文档 `docs/架构诊断-框架为什么失效-20260924.md` 的结论 ——
//     一处**无守卫的写**把内存写坏 ⇒ 之后抛 C++ 异常时栈已坏 ⇒ libgcc 展开失败直接 `abort`
//     ⇒ **静默卡死**。访问层的存在意义就是让"写之前先确认可写"不可能被绕过。
//   * 为什么（调用那一半）：偏移写错会**调到别的函数头上**去改引擎状态，事后极难反查
//     ⇒ "逐字节核对通过才把地址交出去"必须收成**一个名字**，而不是每个调用点各自记得。
//   * **唯一刻意不迁的一处**：`char*` → libnx `u8*` 的类型别名转换
//     （`GameFileReader::ReadTextFile` 的实参）—— 它既不碰引擎内存、也不产生"能调的地址"。

#include "mod_menu_native.hpp"
#include "mod_room_guards.hpp"
#include "lua_runtime_state.hpp"

#include "game_file_reader.hpp"
// 批次 418：`bridge::ImagePcxCacheUsedBytes()`（贴图桥转码缓存的**实际占用**，填状态面 [80]）。
#include "image_pcx_bridge_hook.hpp"
#include "application/mod/content_mount_service.hpp"     // `SessionContentMountService()`（[24] 那一格）
#include "domain/runtime/run_taint_marker.hpp"           // 批次 120：存档分区里那个"污染过"标记
#include "infrastructure/console/console_bridge.hpp"      // 批次 124：控制台总开关（读值 + 拨动）
#include "ports/save_file_port.hpp"
#include "infrastructure/persistence/engine_save_file_adapter.hpp"  // 批次 144：只读 options.ini
#include "infrastructure/call/engine_call_access.hpp"    // 引擎调用层（108 起本 TU 调引擎都走它）
#include "infrastructure/memory/engine_field_access.hpp"  // 引擎内存访问层（105 起本 TU 的引擎读写都走它）
#include "infrastructure/relay/entry_relay_binding.hpp"  // `Original<>`（挂点记下的原函数入口）
#include "interfaces/lua/font_api.hpp"                   // `LastFontLoadWordForProbe()`（[25] 那一格）
#include "interfaces/lua/mod_menu_api.hpp"               // 发现结果 + 开关服务
#include "lua_runtime_state.hpp"                         // `InputIsActionPressedThunk()`
#include "mod_menu_entry_row.hpp"                        // 那一列"多插一格"的算术（有宿主门禁）
#include "mod_page_entries.hpp"                          // 条目布局（有宿主门禁）
#include "mod_page_nav.hpp"                              // 模组页自己的算术（有宿主门禁）
#include "mod_page_runtime_sources.hpp"                  // 发现结果 → 条目来源
#include "module_finder.hpp"                             // `FindTargetModule()`
#include "program/mod_player_names.hpp"                  // 批次 401：模组 players.xml → 名字追加层
#include "program/mod_content_names.hpp"                 // 批次 404：模组 items/pocketitems.xml → 名字追加层
#include "runtime_constants.hpp"

#include <array>
#include <atomic>
#include <cstddef>  // `offsetof`（批次 152 的替身 ModEntry 用它对账布局）
#include <cstdint>
#include <cstring>
#include <optional>

#if defined(__aarch64__)
#include <malloc.h>  // `mallinfo()`（newlib 提供；宿主没有这个口径，所以只在设备构建里包含）
#endif

// 挂载点重建中继的两个观测计数（[22]/[23] 那两格）。定义在
// `source/content/rebuild_content_mount_points_relay.cpp`，是 `extern "C"` 的具名函数
// （**只读**：它们只回一个计数，不改任何状态）。
extern "C" std::uint32_t IsaacModRuntime_RebuildContentMountPointsRelayFiredCount();
extern "C" std::uint32_t IsaacModRuntime_RebuildContentMountPointsRelayFailureCount();

//: 引擎内存访问层的短别名（批次 105）。只为调用点可读：调用点要写的是"哪个对象的哪个偏移"，
//: 一长串限定名会把那件事淹掉。**别名不改变层里的任何判定**（它只是同一个命名空间的另一个名字）。
namespace engine_memory = isaac::runtime::engine_memory;

//: 引擎调用层的短别名（批次 108），理由同上。调用点要写的是"调哪个引擎入口"。
namespace engine_call = isaac::runtime::engine_call;

// ---- 批次 144（2026-09-26）：只读看一眼引擎配置（`options.ini` 的 `EnableMods`）---------
// ★ 放**文件顶层**（而不是 `modmenu` 命名空间里）：探针函数在后面的**全局匿名命名空间**里，
//   埋点若留在 `modmenu` 里就会"未声明"（这次构建就因此判红）。`extern "C"` 保证是裸名符号，
//   读数工具按名字直读 —— 与 `g_ModMenuState` 同一个口径。
extern "C" {
std::uint32_t g_OptionsProbeExists{0};      //: `save:/options.ini` 在不在（1 = 在）
std::uint32_t g_OptionsProbeStatus{0};      //: Exists 的 Status 码（0 = Ok）
std::uint32_t g_OptionsProbeReadStatus{0};  //: Read 的 Status 码（0 = Ok）
std::uint32_t g_OptionsProbeSize{0};        //: 读回多少字节
std::uint32_t g_OptionsProbeEnableMods{0};  //: 0/1 = 那一行的值；0xFFFFFFFF = 没找到这一行
std::uint32_t g_OptionsProbeHeadLow{0};     //: 头 8 字节（小端两半）—— 确认读到的是文本
std::uint32_t g_OptionsProbeHeadHigh{0};
//: 批次 145：我们**每帧**把引擎那个"启用模组"总闸置回 1 的次数（读到 0 才写）。
std::uint32_t g_ModsGateRestores{0};

// ---- 批次 148（2026-09-26）：**我们自己喊一次**引擎那条"扫模组目录 + 加载 content" ---------
// 由来与依据见 `runtime_constants.hpp` 的批次 148 那一段（`ModManager::Reset/ListMods/
// LoadConfigs` 在这版镜像里零引用 ⇒ 引擎从不加载模组的 `content/*.xml`）。
// 触发点**刻意选"用户打开模组页"那一刻**：批次 143/144 把同类操作放在"每帧的第一帧"上，
// 真机各崩一次（`nn::diag::Abort`，引擎的挂载/文件子系统那时还没就绪）；模组页那一刻
// 引擎正在读存档里的模组开关 ⇒ 子系统必然已就绪，且是游戏线程（144c 实测不崩）。
std::uint32_t g_ModEngineScanAttempts{0};    //: 本函数被走过几次（= 进模组页次数）
std::uint32_t g_ModEngineScanStage{0};       //: 0 未做 / 1 两个入口已解析 / 2 全部走完 / 3 失败
std::uint32_t g_ModEngineModEntries{0};      //: 这次**处理了几个模组目录**（发现结果里启用的那些）
std::uint32_t g_ModEngineCostumeLoads{0};    //: `ItemConfig::LoadCostumes()` 被我们调了几次
std::uint32_t g_ModEngineMusicLoads{0};      //: `Music::LoadConfig()` 被我们调了几次
//: ★ 批次 409（2026-10-08）：`ANM2::Load("gfx/ui/mod_defaults.anm2", true)`（引擎
//: `ModManager::LoadConfigs` 的收尾那一步）被我们调了几次 —— **正常 = 1**（进程内只做一次）。
//: 为什么必须有这一格：这一次调用**没有任何别的可观测信号**（不涨容器、不产生回调），
//: 而它漏掉的后果是"暂停屏画模组道具时崩"（真机 2026-10-08 13:45 崩过一次）。
std::uint32_t g_ModEngineModDefaultsAnm2Loads{0};
std::uint32_t g_ModEngineResolveFailures{0}; //: 入口核对失败的位图（bit0 LoadCostumes / bit1 Music::LoadConfig）
//: 挂载解析（`ContentGetMountedFilePath`）**解析不到**的条数 —— 那一条就跳过不加载。
//: 与 `LoadCostumes`/`Music::LoadConfig` 的调用次数合起来看：**调用数 = 解析成功数**；
//: 解析不到 = 那个文件在挂载表里不存在（模组没这个文件，或我们的路径写法不对）。
std::uint32_t g_ModEnginePathResolveMisses{0};
std::uint32_t g_MusicEntryCountBefore{0};    //: 加载前曲目表几条（真机基线 119）
std::uint32_t g_MusicEntryCountAfter{0};     //: 加载后曲目表几条（模组的 music.xml 2 条 ⇒ 121）
std::uint32_t g_CostumeCountBefore{0};       //: 加载前 null 服装容器几条（真机基线 132）
std::uint32_t g_CostumeCountAfter{0};        //: 加载后几条（模组 costumes2.xml 23 条 ⇒ 155）

// ---- 批次 149b（2026-09-26）："喂给引擎的那条路径"必须留证 --------------------------------
//
// 由来：148d 的**真机**读数显示两个加载器**各被调了 1 次**（= 路径解析成功、我们确实调了），
// 但两个容器**一条都没涨**（曲目 119→119、服装 132→132）。能怀疑的只剩"喂进去的路径形态
// 引擎的文件层不认"。
//
// 反汇编引擎**自己**那条路（`ModManager::LoadConfigs` @ `0x41E388`）得到的写法：
//   `adrp/add "costumes2.xml"` → `bl ModEntry::GetContentPath(名)` → `FileManager::Exists(路径)`
//   → `bl ItemConfig::LoadCostumes(路径, ModEntry*)`（`music.xml` 同理 → `Music::LoadConfig`）
// —— 文件名是**裸名**，路径由 `ModEntry::GetContentPath` 拼成**应用根相对**的形式。
// 而 `GetMountedFilePath` 返回的是**带 `rom:/` 的完整路径**（批次 085 真机口径：
// "引擎的挂载解析只认相对应用根的名字"，当时模组页的 `metadata.xml` 就是靠去掉 `rom:/` 才读到的）。
//
// ⇒ 本批**两种口径都试**，判据用客观信号（容器涨没涨），并把 `GetMountedFilePath` 返回的
//   原始串记下来 —— 这样下一轮读数能同时回答两件事：①哪种口径能用；②返回的到底是不是
//   模组自己的那个文件（若返回的是本体的文件，那"没涨"就是另一回事）。
std::uint32_t g_ModEngineCostumeForm{0};  //: 0 两种口径都没让容器涨 / 1 去掉 rom:/ 后涨了 / 2 带 rom:/ 才涨
std::uint32_t g_ModEngineMusicForm{0};    //: 同上（音乐侧）
std::uint32_t g_ModEngineCostumeCalls{0}; //: `LoadCostumes` **实际调用**次数（两种口径各算一次）
std::uint32_t g_ModEngineMusicCalls{0};   //: `Music::LoadConfig` **实际调用**次数
char g_ModEngineResolvedCostumes[256];    //: `GetMountedFilePath` 为服装返回的原始串（带 rom:/）
char g_ModEngineResolvedMusic[256];       //: 同上（音乐）
//: 曲目表**最后一条**的两个留证：`+0x00` 的编号、`+0x08` 起 32 字节的原始串字节。
//:
//: 为什么是"原始字节"而不是"读成字符串"：名字那一段是 libc++ 的 `std::string`
//: （短串把长度放在首字节、长串在首 8 字节放指针）⇒ **解码放在读数工具里做**，
//: 运行时只负责把 32 字节原样搬回来。这样"条目里到底有什么"这件事不被任何一方的
//: ABI 猜测污染（第一版就是在 C++ 里按"逐字节到 NUL"读的，读到 `'x'` 才发现偏移错了）。
std::uint32_t g_ModEngineMusicLastEntryId{0};
std::uint64_t g_ModEngineMusicLastEntryRaw[4] = {0, 0, 0, 0};
}

namespace isaac::runtime::modmenu {
std::uint32_t g_ModRoomLoadState[8]{}; // 成功合并次数、源条数、阶段、模式、未就绪、接收者失败、标志失败、源位图。


//: 状态面本体。**外部链接 + 固定符号名**：读数工具按裸名 `g_ModMenuState` 取它
//: （放进匿名命名空间就会让 `nm` 查不到 —— 2026-09-19 的 D6 事故）。字段顺序见 `.hpp`。
//:
//: ★★ 为什么用**块形式** `extern "C" { ... }` 而不是 `extern "C" State x = {...};`：
//: 后者在 gcc 下报 `'g_ModMenuState' initialized and declared 'extern'`，而本构建是 `-Werror`
//: ⇒ 直接编译失败（2026-09-23 批次 077 实测）。块形式同样给**C 语言链接**（符号名仍是裸名
//: `g_ModMenuState`，不带命名空间前缀、不做名称改编），但不会被判成那条告警 ——
//: **别改回去**。判据见 `runtime/tests/test_mod_menu_native_production.py`。
extern "C" {
State g_ModMenuState = {
    1,  // [0] armed：本功能编进来了（生产构建恒 1）
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0,  // [22]..[25]：2026-09-23 加的观测四格（每帧由 `ModMenuNativeUpdate` 填）
    0,           // [26] 开模组禁成就（每帧写 1；见常量那段注释）
    0, 0, 0, 0,  // [27]..[30]：metadata.xml 三种结果 + 开着的真实模组个数（每帧填）
    0,           // [31] 成就 #4（打过妈妈）解锁没（每帧问一次）
    0,           // [32] 成就位数组抽样（id 0..3 各一字节，自证位置）
    0,           // [33] 我们写进 `PersistentGameData+0x1` 的只读位（真正挡成就的那一位）
    0,           // [34] 每帧 +1 的计数器（证明我们的更新还在跑）
    0, 0, 0, 0, 0,  // [35]..[39]：成就闸门中继的调用/拦截/解锁/最后成就号/原函数缺失（2026-09-24 加）
    0,           // [40] 处于**启用状态**的真实模组个数（批次 107 加；判据就是它，见 `.hpp`）
    0, 0, 0, 0,  // [41]..[44]：发现清单自证四格（批次 116 加：条数 / 启用位图 / 加载位图 / 发现跑过没）
    0, 0, 0, 0, 0, 0,  // [45]..[50]：局内单向闩锁六格（批次 117 加：闩锁值 / 置位次数 /
                       //   清零次数 / 上次清零来源 / `GameExit` 被调到几次 / 闩锁可用否）
    0, 0, 0,           // [51]..[53]：批次 118 加：在一局里吗 / 边沿写位调用几次 / 边沿写位的结果
    0, 0,              // [54]..[55]：批次 119 加：出局时留存的污染 / 把留存接回来过几次
    0, 0,              // [56]..[57]：批次 120 加：存档分区里那个标记（我们认为它是几 / 读写失败几次）
    0, 0,              // [58]..[59]：批次 135 加：本模块堆的**空闲**字节数 / **已用**字节数（每 60 帧采一次）
    0,                 // [60] 批次 153 加：「喂模组 content 给引擎」是从哪个时机跑起来的
                       //   （0 = 还没跑 / 1 = 模组脚本之前 / 2 = 进模组页 / 3 = 每帧重试）
    0,                 // [61] 批次 154 加：「模组脚本之前」那一次走到了哪一步（0..3，值域同阶段字）
    0, 0,              // [62]..[63]：批次 159 加：引擎说「继续游戏」可不可选（1/0/2 = 读不到）/
                       //   因为它不可选而跳过它的次数
    0, 0, 0, 0,        // [64]..[67]：批次 180 加：进程内存总量 / 已用、系统资源池总量 / 已用
                       //   （`svcGetInfo` 的 6 / 7 / 16 / 17；0xFFFFFFFF = 调用失败。每 60 帧采一次）
    0, 0, 0, 0, 0, 0,  // [68]..[73]：批次 378 加：16 项入口解析成功位图 / 解析失败位图 /
                       //   14 项加载器调用次数 / `PostLoadMods` 调用次数（正常 1）/
                       //   `LoadCustomResources` 调用次数（正常 = 启用模组数）/
                       //   真 `ModEntry` 构造次数（正常 = 启用模组数）
    0,                 // [74] 批次 409 加：引擎 `ModManager::LoadConfigs` 尾部那一步
                       //   （`ANM2::Load("gfx/ui/mod_defaults.anm2", true)` 到 `ModManager+0x368`）
                       //   被我们调了几次 —— **正常 = 1**；0 = 那一步没做
                       //   ⇒ 暂停屏画模组道具（id ≥ 733）时会写 `0x80` 崩
    0,                 // [75] 批次 417 加：**Lua 状态自己占多少字节**（`lua_gc` 的 GCCOUNT）。
                       //   用来把 [59] 的"已用"拆成 Lua 侧与其它：其它 = [59] − [75]。
                       //   每 60 帧采一次（与 [58]/[59] 同一个节拍）；宿主构建/还没采到时为 0
    0,                 // [76] 批次 418 加：`mallinfo().uordblks`（分配器自认已分配的字节）
    0,                 // [77] 批次 418 加：`mallinfo().ordblks`（空闲块个数 = 碎片读数）
    0,                 // [78] 批次 418 加：`mallinfo().hblks`（mmap 区个数，newlib 下恒 0）
    0,                 // [79] 批次 418 加：`mallinfo().keepcost`（堆顶那块空闲的字节）
    0,                 // [80] 批次 418 加：贴图桥转码结果缓存的**实际占用**（不是 24 MiB 预算）
    0, 0,              // [81]..[82]：批次 420 加：问内核"还剩多少内存"两格 ——
                       //   不含系统池的进程可用/已用（`svcGetInfo` 21/22）。
                       //   `0xFFFFFFFF` = 调用失败。每 60 帧采一次（与 [58]/[59] 同节拍）
                       //   ★ 本批第一版还调了 `svcGetSystemInfo`（3 格），真机当场崩
                       //     （`Undefined System Call` / svc 0x6f）⇒ 已删掉。
    0, 0,              // [83]..[84]：批次 420（续）加：**resource limit 那条路** ——
                       //   内存配额上限 / 当前已用（`InfoType_ResourceLimit` 9 + svc 0x30/0x31，
                       //   `which = LimitableResource_Memory = 0`）⇒ **还剩 = [83] − [84]**。
    0, 0, 0, 0,        // [85]..[88]：批次 421 加：扫地址空间按 `MemType` 分类（**KiB**）——
                       //   `Normal` / `Heap` / 代码 / `Mapped`+`ThreadLocal`+`TransferMem`+`ProcessMem`
    0,                 // [89]：批次 421 加：**私有/真实占用合计**（KiB，含游戏+兼容层+模组）
                       //   ★ 批次 424：原来这里还有第 90 项（"所有非 `Unmapped` 合计"）——
                       //     它**恒溢出 u32**（IO/保留区的虚拟范围是 TiB 量级）⇒ 已删。
};
}  // extern "C"

} // namespace isaac::runtime::modmenu

// ---- 批次 144（2026-09-26）：**只读**看一眼引擎的配置真相（`options.ini` 的 `EnableMods`）--
//
// 为什么查它：三次读数拼出的链条是"引擎扫目录那一刻总闸是 0，而我们的运行时**后来**才在内存里
// 把它改成 1"（**就是本文件 `EnterModsPage()` 第 8 步做的**）—— 太晚。按 PC 逻辑，这个值来自
// 存档分区里的 `options.ini`（`Manager::Init` 读它：`INIParser::GetBool("EnableMods", 默认 1)`）。
//
// ★ 为什么挂在这里（`EnterModsPage`）：144 的第一版把这段放在"每帧更新的**第一帧**"，
//   真机**直接崩**（`nn::diag::Abort`，栈是 `runtime + 0x27388 ← runtime + 0x4670`）——
//   那时引擎的文件/存档子系统还没就绪。**用户打开模组页**这一刻才是确定安全的：
//   模组页本身就在读存档里的开关 ⇒ 存档子系统必然已就绪，而且是游戏线程。
void ProbeEngineOptionsFile() {
    // 本仓源码不许用 bool 版原子量（门禁 `test_runtime_source_contains_no_bool_atomics`
    // 逐文件扫**文本**，覆盖 `source` 与 `src` 两个根），统一用 `std::atomic<std::uint32_t>`。
    // ★ 门禁是文本匹配 —— 连注释里也**不要**原样写出那个被禁的写法。
    static std::atomic<std::uint32_t> attempted{0};
    std::uint32_t expected = 0;
    if (!attempted.compare_exchange_strong(expected, 1U, std::memory_order_acq_rel)) {
        return;
    }
    // ★ 走项目**现成的那条通道**（`SessionSaveFilePort()`）：模组数据容器与"污染标记"都走它，
    //   真机上验证过可用；自己 new 一个 `EngineSaveFileAdapter` 会解析不到能力（144 第一次读数
    //   就是这么得到 `Status = Unsupported(3)` 的 —— 那条路要的是"已发布"的端口）。
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    g_OptionsProbeStatus = (storage == nullptr) ? 3U : 0U;
    if (storage == nullptr) {
        return;
    }
    static char buffer[isaac::runtime::EngineSaveFileAdapter::kMaximumFileBytes];
    std::size_t size = 0;
    const isaac::runtime::Status readStatus =
        storage->Read("options.ini", buffer, sizeof(buffer), &size);
    g_OptionsProbeReadStatus = static_cast<std::uint32_t>(readStatus.code());
    g_OptionsProbeSize = static_cast<std::uint32_t>(size);
    g_OptionsProbeExists = (readStatus.code() == isaac::runtime::StatusCode::NotFound) ? 0U : 1U;
    g_OptionsProbeEnableMods = 0xFFFFFFFFU;
    if (readStatus.ok() && size != 0) {
        for (std::size_t i = 0; i + 10 <= size; ++i) {
            if (std::memcmp(buffer + i, "EnableMods", 10) != 0) {
                continue;
            }
            std::size_t j = i + 10;
            while (j < size && (buffer[j] == ' ' || buffer[j] == '\t')) {
                ++j;
            }
            if (j < size && buffer[j] == '=') {
                ++j;
                while (j < size && (buffer[j] == ' ' || buffer[j] == '\t')) {
                    ++j;
                }
                g_OptionsProbeEnableMods = (j < size && buffer[j] == '1') ? 1U : 0U;
            } else {
                g_OptionsProbeEnableMods = 0U;
            }
            break;
        }
        std::uint64_t head = 0;
        const std::size_t headBytes = size < 8 ? size : 8;
        std::memcpy(&head, buffer, headBytes);
        g_OptionsProbeHeadLow = static_cast<std::uint32_t>(head & 0xFFFFFFFFULL);
        g_OptionsProbeHeadHigh = static_cast<std::uint32_t>(head >> 32);
    }
}

namespace {

using isaac::runtime::modmenu::g_ModMenuState;

//: 本模块**自己的堆**还剩多少 / 用了多少（批次 135；填状态面 `[58]`/`[59]`）。
//:
//: 为什么存在：`PngToPcx`（贴图桥转码）的峰值曾把这块堆撞满 ⇒ `std::bad_alloc` ⇒
//: 2026-09-25 无声卡死、09-26 可见崩溃。有这两格，"是不是堆撞满"在现场直接可读。
//: 口径 = newlib `mallinfo()`：`arena` = 堆总量、`fordblks` = 其中空闲。
//:
//: 为什么**每 60 帧**才采一次：`mallinfo()` 要遍历空闲块链表，堆碎时不是免费操作；
//: 而我们要回答的是"撞满前还剩多少"，一秒一次的粒度足够。
//: 宿主（x86_64）没有这个口径 ⇒ 两格写 0（门禁不会据此断言真值）。
//:
//: 批次 180（2026-09-28）：同一次调用里再采四格 —— **这个进程一共还有多少内存**。
//: 为什么必须量它：本批把 `HeapSize` 抬到 128 MiB（见 `program/setting.hpp` 那段），
//: 而"128 MiB 装不装得下"**上游没有任何文档能回答**（Atmosphere 的加载器只要求"把 exefs 里的
//: 各个 NSO 连续装进进程"）。与其再猜一次，不如把四个数读出来：
//:   * 6 = 进程可用内存总量、7 = 其中已用（`InfoType_TotalMemorySize` / `UsedMemorySize`）；
//:   * 16 = "进程内存管理池"总量、17 = 其中已用（`InfoType_SystemResourceSizeTotal` / `Used`）——
//:     加载器把我们的段（含这块假堆）映射进进程时吃的就是这一类额度。
//: ★★ 2026-09-28 真机读数之后的更正（批次 181）：**上面前两条的用途没兑现** ——
//:   实测 `[64]`/`[65]` 两边几乎相等（3189.0 MB / 3188.0 MB），而同一刻游戏完全正常
//:   ⇒ 那个口径下"余量"算不出有意义的值（见 `.hpp` 里那段的完整实测与结论）。
//:   所以这四格**只作记录、不作判据**；"128 MiB 够不够"由贴图桥的
//:   `实际转码 13 / 失败 0` 与模块堆 arena 47.4 MB（> 旧的 32 MiB）来回答。
//: ★ 失败存 **`0xFFFFFFFF`**（哨兵）：`svcGetInfo` 出错与"真的只剩 0 字节"必须能分开，
//:   否则读到一个 0 会被读成"内存耗尽"（本项目在这一点上踩过：见服装查表那几格的约定）。
//: ★ 它**只记录、不参与任何判定** —— 没有任何行为跟着这四个数变。
void NoteHeapUsagePeriodically() noexcept {
#if defined(__aarch64__)
    if ((g_ModMenuState.drivenFrames % 60U) != 0U) {
        return;
    }
    const struct mallinfo info = mallinfo();
    const std::uint32_t arena = static_cast<std::uint32_t>(info.arena > 0 ? info.arena : 0);
    const std::uint32_t freeBytes =
        static_cast<std::uint32_t>(info.fordblks > 0 ? info.fordblks : 0);
    g_ModMenuState.heapFreeBytes = freeBytes;
    g_ModMenuState.heapUsedBytes = (arena > freeBytes) ? (arena - freeBytes) : 0U;
    // 批次 418：同一个 `mallinfo()` 里再取四格账目（**不多扫一遍空闲链表**）。
    // 判读表（这是本批真正要回答的那个问题）：
    //   [76] `uordblks` 与 [59] 几乎相等 ⇒ [59] 没高估，那 ≈84 MB 是**真实的分配**；
    //   [76] 远小于 [59]              ⇒ `mallinfo` 口径高估，先修量具再谈省内存。
    //   [77] `ordblks` 很大（几千）而 [58] 还有几 MB ⇒ 碎片（"8115 个碎块"那条独立观测与此互证）；
    //   [79] `keepcost` 很小而 [58] 不小        ⇒ 释放的块**无法与堆顶合并** ⇒ 只增不减 + 碎片。
    // ★ 取负值一律夹到 0（`mallinfo` 的字段是 `int`，堆统计异常时可能是负的）。
    const auto clampNonNegative = [](int value) -> std::uint32_t {
        return value > 0 ? static_cast<std::uint32_t>(value) : 0U;
    };
    g_ModMenuState.heapAllocatedBytes = clampNonNegative(info.uordblks);
    g_ModMenuState.heapFreeChunkCount = clampNonNegative(info.ordblks);
    g_ModMenuState.heapMmappedRegions = clampNonNegative(info.hblks);
    g_ModMenuState.heapTopFreeBytes = clampNonNegative(info.keepcost);
    // 批次 418：贴图桥转码结果缓存的**实际占用**（它 24 MiB 的预算是上限、不是占用）。
    // ★ 走 `bridge::ImagePcxCacheUsedBytes()` 这个函数，**不**按对象偏移硬读 `used_bytes_`
    //   —— 那个偏移会随 `BudgetedLruCache` 的布局漂，硬编码偏移会**静默读错**。
    g_ModMenuState.imagePcxCacheUsedBytes = isaac::runtime::bridge::ImagePcxCacheUsedBytes();
    // 批次 417：同一次节拍里再采一格 —— **Lua 状态自己占多少**。
    // 有了它，"已用 122.8 MB"才拆得开：其它 = `heapUsedBytes` − 本格。
    // ★ 只读、只记录（`LuaStateMemoryBytes()` 只查 `lua_gc` 的两个计数，不触发 GC）。
    g_ModMenuState.luaStateBytes = LuaRuntime::LuaStateMemoryBytes();
    // 批次 180：进程内存四格（同一个 60 帧节拍里问内核，开销可忽略）。
    // `CUR_PROCESS_HANDLE` = libnx 定义的"当前进程"伪句柄（0xFFFF8001），不需要任何权限。
    const auto query = [](u32 infoType) -> std::uint32_t {
        u64 value = 0;
        if (R_FAILED(svcGetInfo(&value, infoType, CUR_PROCESS_HANDLE, 0)) ||
            value > 0xFFFFFFFFULL) {
            return 0xFFFFFFFFu;  // 哨兵：调用失败（**不是** 0 字节）
        }
        return static_cast<std::uint32_t>(value);
    };
    g_ModMenuState.processTotalMemoryBytes = query(InfoType_TotalMemorySize);
    g_ModMenuState.processUsedMemoryBytes = query(InfoType_UsedMemorySize);
    g_ModMenuState.systemResourceTotalBytes = query(InfoType_SystemResourceSizeTotal);
    g_ModMenuState.systemResourceUsedBytes = query(InfoType_SystemResourceSizeUsed);
    // 批次 420：问内核"还剩多少内存"（口径见 `.hpp` 里那两格）。
    // `svcGetInfo` 的 21/22 = **不含"进程内存管理池"**的可用 / 已用（6.0.0+）——
    // 比 6/7 更有信息量：那两格含系统池、实测**恒几乎相等**（答不了"还剩多少"）。
    // ★★ 本批第一版**还调了 `svcGetSystemInfo`**（想直接读"应用档物理内存"）——
    //    真机第一次上卡**当场崩**：`Type = Undefined System Call`、`Svc Id = 0x6f`、
    //    `PC = runtime + 0x9901c`（崩溃报告 `01791635311_010021c000b6a000.log`）
    //    ⇒ **那个 svc 在用户态的 Application 里不存在**。已删掉，只留下面两行。
    g_ModMenuState.processTotalNonSystemBytes = query(InfoType_TotalNonSystemMemorySize);
    g_ModMenuState.processUsedNonSystemBytes = query(InfoType_UsedNonSystemMemorySize);
    // 批次 420（续）：★ **resource limit 那条路** —— 内核源码级的"还剩多少"（见 `.hpp`）。
    // 三个调用都**没有权限检查**（与 svcGetSystemInfo 那个死路完全不同）；失败一律落哨兵。
    // ★ 注意 `InfoType_ResourceLimit` 的 `handle` 必须传 **INVALID_HANDLE**（内核写着
    //   `R_UNLESS(handle == InvalidHandle, …)`），不是别的 `svcGetInfo` 用的 `CUR_PROCESS_HANDLE`。
    // ★ 注意：libnx 的 `svcGetInfo` 第一个参数是 **`u64*`**（内核按 64 位回），
    //   而 `Handle` 是 **32 位** ⇒ 直接用 `Handle*` 会编译不过（本批实撞）。
    u64 resourceLimitRaw = 0;
    if (R_SUCCEEDED(svcGetInfo(&resourceLimitRaw, InfoType_ResourceLimit, INVALID_HANDLE, 0)) &&
        resourceLimitRaw != 0) {
        const Handle resourceLimit = static_cast<Handle>(resourceLimitRaw);
        u64 limitValue = 0;
        u64 currentValue = 0;
        const bool okLimit = R_SUCCEEDED(
            svcGetResourceLimitLimitValue(&limitValue, resourceLimit, LimitableResource_Memory));
        const bool okCurrent = R_SUCCEEDED(
            svcGetResourceLimitCurrentValue(&currentValue, resourceLimit, LimitableResource_Memory));
        svcCloseHandle(resourceLimit);
        g_ModMenuState.resourceLimitMemoryBytes =
            (okLimit && limitValue > 0 && limitValue <= 0xFFFFFFFFULL)
                ? static_cast<std::uint32_t>(limitValue)
                : 0xFFFFFFFFu;
        g_ModMenuState.resourceMemoryUsedBytes =
            (okCurrent && currentValue <= 0xFFFFFFFFULL)
                ? static_cast<std::uint32_t>(currentValue)
                : 0xFFFFFFFFu;
    } else {
        g_ModMenuState.resourceLimitMemoryBytes = 0xFFFFFFFFu;
        g_ModMenuState.resourceMemoryUsedBytes = 0xFFFFFFFFu;
    }
    // 批次 421：★★ **`svcQueryMemory`(0x06) 扫地址空间、按 `MemType` 分类求和** ——
    // 这才是"看得见的内存占用"：**游戏本体 + 我们的兼容层 + 模组**都在 `[89]`（私有合计）里
    // （兼容层与模组的 `malloc` 用的就是游戏的堆/映射）。
    // ★ 单位 **KiB**：字节会溢出 u32 格（第一版实测"所有已映射" > 4 GiB）。
    //   ★ 424 起那一格（`memMappedTotalKiB`）**已删除** —— 它恒溢出、没有意义；
    //     删它是最后一格，不影响前面任何字段的编号。
    // ★ **只扫一次**（一次扫要几千次 svc 调用，绝不能每帧做）。
    // ★ 第一版试过的 `svcGetInfo` 区域大小四格（3/5/13）在 Application 上**直接调用失败**
    //   （只有 15 栈区成功）⇒ 已删掉那四格。
    {
        static bool s_memScanDone = false;   // POD ⇒ 无动态初始化（`__cxa_guard` 保持 0）
        if (!s_memScanDone) {
            s_memScanDone = true;
            u64 normal = 0;
            u64 heap = 0;
            u64 code = 0;
            u64 mappedLike = 0;
            u64 privateTotal = 0;
            u64 cursor = 0;
            for (int guard = 0; guard < 200000; ++guard) {
                MemoryInfo info{};
                u32 pageInfo = 0;
                if (R_FAILED(svcQueryMemory(&info, &pageInfo, cursor)) || info.size == 0) {
                    break;
                }
                const u32 type = info.type & MemState_Type;
                if (type != MemType_Unmapped) {
                    switch (type) {
                        case MemType_Normal:      normal += info.size; break;
                        case MemType_Heap:        heap += info.size; break;
                        case MemType_CodeStatic:
                        case MemType_CodeMutable: code += info.size; break;
                        case MemType_MappedMemory:
                        case MemType_ThreadLocal:
                        case MemType_TransferMem:
                        case MemType_ProcessMem:  mappedLike += info.size; break;
                        default: break;
                    }
                    // "私有/真实占用" = 除 IO / 共享 / 保留 之外的一切（含上面那几类）。
                    if (type != MemType_Io && type != MemType_SharedMem &&
                        type != MemType_Reserved) {
                        privateTotal += info.size;
                    }
                }
                const u64 next = info.addr + info.size;
                if (next <= cursor) {
                    break;   // 回绕 / 溢出保护
                }
                cursor = next;
            }
            const auto toKiB = [](u64 bytes) -> std::uint32_t {
                const u64 kib = bytes >> 10;
                return (kib <= 0xFFFFFFFFULL) ? static_cast<std::uint32_t>(kib) : 0xFFFFFFFFu;
            };
            g_ModMenuState.memNormalKiB = toKiB(normal);
            g_ModMenuState.memHeapKiB = toKiB(heap);
            g_ModMenuState.memCodeKiB = toKiB(code);
            g_ModMenuState.memMappedKiB = toKiB(mappedLike);
            g_ModMenuState.memPrivateKiB = toKiB(privateTotal);
        }
    }
#else
    g_ModMenuState.heapFreeBytes = 0;
    g_ModMenuState.heapUsedBytes = 0;
    // 批次 418：四格 `mallinfo` 账目与贴图桥缓存占用在宿主上一律 0（这套口径在 x86_64 上不存在，
    // 门禁不据此断言真值）。★ 贴图桥那个访问器**只在 aarch64 分支里调** ——
    // 宿主 harness 不一定把 `image_pcx_bridge_hook.cpp` 链接进来。
    g_ModMenuState.heapAllocatedBytes = 0;
    g_ModMenuState.heapFreeChunkCount = 0;
    g_ModMenuState.heapMmappedRegions = 0;
    g_ModMenuState.heapTopFreeBytes = 0;
    g_ModMenuState.imagePcxCacheUsedBytes = 0;
    // 宿主构建：四格保持 0（= 这套口径在 x86_64 上不存在，门禁不据此断言真值）。
    g_ModMenuState.processTotalMemoryBytes = 0;
    g_ModMenuState.processUsedMemoryBytes = 0;
    g_ModMenuState.systemResourceTotalBytes = 0;
    g_ModMenuState.systemResourceUsedBytes = 0;
#endif
}

// ─────────────────────────────────────────────────────────────────────────────
// 偏移与入口指纹
// ─────────────────────────────────────────────────────────────────────────────
//
// 来源：探针 `native_mods_menu_probe.cpp`（逐字节照搬，一个数字都没改）。
// 单例都是**经 GOT 槽的两级取值**，`Menu_Mods::Init` 的原话可作模板：
//
//     00410164  adrp x8, 0xaad000
//     00410168  ldr  x8, [x8, #0x1b0]   ; 槽 → &g_MenuManager（模块内 bss 0xABCD48）
//     0041016c  ldr  x0, [x8]           ; 再取一次才是 MenuManager*
//
// 槽号 0xAAD1B0 / 0xAAC648 都在重定位表里登记过（分别对应 `g_MenuManager` / `g_Manager`），
// 是加载器写进去的，所以这两条读法是"加载器保证"的，不是我们猜的。
constexpr std::uintptr_t kMenuManagerSlotOffset = 0xAAD1B0;
constexpr std::uintptr_t kManagerSlotOffset = 0xAAC648;
//: `g_Manager` 里"引擎自己那份模组表"的偏移（与 `kManagerToModManagerOffset` 同一个数）。
constexpr std::uintptr_t kManagerModsVectorOffset = 0x36800;
//: 模组总开关（PC 的"启用模组"）：`g_Manager` 上的一个字节。`Menu_Mods::Render` 读它选颜色；
//: 为 0 时它**只用一个颜色画所有行**（不读条目自己的启用位）⇒ 切换开关在屏幕上看不出来。
constexpr std::uintptr_t kManagerModsEnabledOffset = 0x36519;
//: `g_Manager + 0x2B688` 的**两个字节** = 引擎自己判"继续游戏可不可选"的依据（批次 159）。
//:
//: 反汇编依据（`tools/nro_disasm.py 0x40d5e0 0x700`，四处用法逐条对上）：
//:   * `Menu_Game::Init @0x40D1A4` / `Reset @0x40D428`：`byte0 != 0` 才把选中项默认设成 1
//:     并预渲染 continue 那张小图；
//:   * `Menu_Game::Update @0x40D5E0` 的导航两处（`0x40D7C0` 上键 / `0x40D84C` 下键）：
//:     **两个字节都为 0 ⇒ 跳过 index 1**；
//:   * 同一函数收尾（`0x40D9F0`）：把已经停在 1 上的选中项**拨回 0**；
//:   * 同一函数末尾（`0x40DB5C`）：按这两格选**第 2 层行图**的帧 —— `byte0 != 0` → 0、
//:     `byte0 == 0 && byte1 != 0` → 2、两个都 0 → 1（"灰"就是这么来的，不用我们碰美术）。
//: ⇒ 我们那一列的导航判据与它**逐条一致**：**任一个非 0 ⇒ 可选**。
constexpr std::uintptr_t kManagerContinueAvailableOffset = 0x2B688;

// ── 「开模组 ⇒ 禁成就」（2026-09-23 批次 084，取证后实现）────────────────────────
//
// `g_Manager + 0x36D4D` 的一个字节 = **本局不给成就**（1 = 禁、0 = 允许）。逐字节证据：
//   * `Game::StartDebug`（`0x34FAF0`）：`mov w10,#1` → `mov/movk w11,#0x36D4D`
//     → `strb w10,[x0,x9]` ⇒ **调试局把这一位置 1**（调试局不给成就，符合直觉）；
//   * `Manager::check_game_data_modified()`（`0x3FA980`，整个函数只有三行）：
//     `mov/movk w8,#0x36D4D` → `strb wzr,[x0,x8]` ⇒ **无条件写 0**。
//     ⇒ **Switch 移植版把"游戏数据被改过"这项检查砍成了恒假**（PC 上它会因为"开了模组"
//       而置 1）⇒ 所以现在模组开着也照样给成就。
//   * **读它的四处**（都在开局那一刻，抄进本局状态）：
//     `Game::Start`（`0x34E584`）、`Game::StartDailyChallenge`（`0x34EB88`）、
//     `Game::RestoreState`（`0x34F12C`）、`Game::StartFromRerunState`（`0x34F714`）
//     —— 全是 `ldrb w?, [x?, x9]` 形式，且都在函数开头附近。
//   ⇒ 我们只要**在每次开局之前**把它置 1 就行；这里选择**每帧写一次**（一个字节的代价，
//     免去"谁什么时候会把它清回 0"这个不确定问题）。
//   * 引擎自带的 `Manager::AchievementUnlocksDisallowed(bool)`（`0x3FA978`）我们**不调**：
//     它是个空实现（`mov w0,wzr; ret`），真正写这一位的代码在它后面那个函数里；
//     而 `Game::AchievementUnlocksDisallowed()`（`0x34EAA8`）问的是 **Seeds**（特殊种子），
//     与模组无关 —— 两条都不是我们要的语义。
//
// **策略（用户 2026-09-23 定案：最忠实 PC）**：**只要这个运行时在跑（= 用了模组）就置 1**。
// 代价要说清楚：**这样就用不了成就了** —— 这正是 PC 的语义，也是这条功能的意义。
constexpr std::uintptr_t kManagerAchievementsDisallowedOffset = 0x36D4D;

// ── 「打完妈妈之前用模组 ⇒ 锁成就」：**一比一照 PC 的判据**（2026-09-23 批次 086）──────
//
// 用户口径（原话的意思）："PC 上打完妈腿**前**使用模组的话无法解锁成就，打完过后使用模组
// 都不会有什么影响"。**去 PC 那边查证过，用户是对的**：
//
// * PC/Afterbirth+ 里那条判据是 `ModManager::AchievementsLocked()` —— 逐条反汇编
//   （`AfterbirthPlus.nro` 有符号，`0x250CB8`）：
//   ```
//   遍历模组列表（`this+0x60` 的 begin/end）：任一模组的 `+0x121` 字节非 0 ⇒ 进入下面这支
//       读 `g_Manager` → `*(g_Manager)` → `add x0, x8, #0x18`（= **PersistentGameData 嵌在
//       `Manager+0x18`**）→ `mov w1, #4` → `bl PersistentGameData::Unlocked(eAchievement)`
//       → `eor w8, w0, #1` ⇒ **返回 `!Unlocked(4)`**
//   列表为空 ⇒ 返回 0（没有模组就不锁）
//   ```
//   ⇒ **PC 的规则 = "有任意模组开着" 且 "成就 #4 未解锁" ⇒ 锁成就。**
// * **成就 #4 是什么**：`resources/achievements.xml` 里 id=4 =
//   `You unlocked "The Womb" -Chapter 4- Mother sleeps` ⇒ **打过妈妈（解锁"子宫"那一章）**。
//   ⇒ 与用户说的"打完妈腿"**完全对上**。
//
// **Switch 侧要用的入口**（都在 `Repentance.nro` 里，逐字节核过）：
//   * `g_Manager` 的 GOT 槽 `0xAAC648`（= 我们已有的 `kManagerSlotOffset`）；
//   * `PersistentGameData` 嵌在 **`Manager + 0x18`**（证据：`0x3C10D4` 那段
//     `ldr x8,[x8,#0x648]; ldr x8,[x8]; add x0,x8,#0x18; bl Unlocked`）；
//   * `PersistentGameData::Unlocked(eAchievement)` @ `0x439654`（x0 = `Manager+0x18`，
//     w1 = 成就号，返回 w0 = bool）。
constexpr std::uintptr_t kManagerPersistentGameDataOffset = 0x18;
//: 成就解锁位在 `PersistentGameData + 0x28`，**按成就号逐字节索引**
//: （证据：`Unlocked` 自己的实现 `0x439678`：`add x8,x0,x8; ldrb w8,[x8,#0x28]`）。
constexpr std::uintptr_t kPersistentAchievementArrayOffset = 0x28;
//: ★★ 为什么**不调 `PersistentGameData::Unlocked()`**：它不是"历史上有没有解锁过"的纯查询 ——
//: 持久位为 0 时它会再去看**本局**的状态（`0x43968C` 起：读 `Game+0x26FA8D` 的 word 与字节，
//: 非 0 就照样返回 true）。2026-09-23 真机实测过这一点：用户存档里成就 #4 的持久字节是 **0**
//: （没打过妈妈），而 `Unlocked(4)` 返回 **true** ⇒ 我们那版判据判反了、成就照给。
//: PC 的 `AchievementsLocked()` 是在**开局那一刻**问的（那时本局状态还没建立）⇒ 等价于直接读持久位。
//: ⇒ 这里直接读那个字节，**并且把数组抽样也记进读数**（`[32]`）自证位置没读错。
constexpr std::uintptr_t kPersistentAchievementArrayOffsetProbe = 0x28;
//: 成就 #4 = `You unlocked "The Womb" -Chapter 4- Mother sleeps` ⇒ **打过妈妈**。
constexpr std::uint32_t kAchievementWomb = 4;
//: ★★ **真正的判据**：`PersistentGameData + 0x1` 那个字节 = "只读/不许解锁成就"。
//:
//: 为什么它才是判据（2026-09-23 真机定位，之前几版都没打到点上）：
//:   * `PersistentGameData::TryUnlock(eAchievement)`（`0x4393D0`）**只查两个东西**：
//:     `ldrb w8,[x0,#0x1]; cbnz w8 → 直接返回不解锁`（+0x1 非 0 ⇒ 拒绝），
//:     以及"这一位是不是已经解锁了"。**它不看 `Manager+0x36D4D`**。
//:   * 而 `Manager+0x36D4D` 只在**开局那一刻**被 `Game::Start` 抄进本局状态（`Seeds+0x8`），
//:     之后 `Game::Start` 再根据"本局该不该禁"去调 `PersistentGameData::SetReadOnly(bool)`
//:     （`0x34E6F0`，`w1=1` 的那条路 = 禁）。
//:   * **Switch 移植版把这条链掐断了**：`Manager::AchievementUnlocksDisallowed(bool)` 是**空实现**
//:     （`0x3FA978` = `mov w0,wzr; ret`），`Manager::check_game_data_modified()` 又**无条件写 0**
//:     且**没有任何调用点**（死代码）⇒ 真机上那个只读位**永远是 0**。
//:   * 真机实证：`Game::AddShopVisits`（`0x35AF84`，买东西触发的那条）**直接尾调用**
//:     `TryUnlock(成就 #379)`，中间**没有任何"禁不禁"的检查**；而现场读数里
//:     `PersistentGameData+0x1 = 0` ⇒ 照样解锁（用户 2026-09-23 复现的那次）。
//:   ⇒ 所以除了写 `Manager+0x36D4D`（保留，它与 PC 的链一致、也无害），**还必须把这个只读位设上**。
//:
//: 安全性：`PersistentGameData::Save()`（`0x433E44`）读的是 `this+0x10` 的位、**不是这一位**
//: ⇒ 设它**不会锁掉存档**，只挡住"新解锁成就"。
constexpr std::uintptr_t kPersistentReadOnlyOffset = 0x1;
//: `PersistentGameData::Unlocked(eAchievement)` 的入口 + 16 字节守卫。
constexpr std::uintptr_t kPersistentGameDataUnlockedOffset = 0x439654;
constexpr std::array<std::uint8_t, 16> kPersistentGameDataUnlockedExpected = {
    0x3F, 0x08, 0x00, 0x31, 0x80, 0x00, 0x00, 0x54,
    0x41, 0x01, 0xF8, 0x37, 0x3F, 0xF4, 0x09, 0x71,
};
//: 字体对象在 `g_Manager` 里的偏移（`Menu_Mods::Render` 画每一行的 `"%d.%s"` 用的就是它：
//: 反汇编里 `add x25, x8, #0x117120`）。**本批起只读不写**（见下面"引擎字体对象"那一段注释）。
constexpr std::uintptr_t kManagerFontOffset = 0x117120;
//: `MenuManager::eState` 在 `MenuManager+0x38`（`Update` 里 `ldr w8,[x19,#0x38]`）。
constexpr std::uintptr_t kMenuManagerStateOffset = 0x38;
//: 页面**共享的画布原点**：`MenuManager+0x3c` 起的那两组 float。引擎每个页面 `Render` 都是
//: `ldp w9, w8, [MenuManager, #0x3c]` 读出这两组 float，再与页面自己的位置相加
//: ⇒ "页面画在哪" = 这个偏移 + 页面自己的偏移。它朝 `get_target_offset()` 收敛，而那个函数算的是
//: `((画面宽-480)/2, (画面高-270)/2)` ⇒ **页面坐标空间是 480×270，可见屏幕比它小、居中裁切**。
constexpr std::uintptr_t kMenuManagerCanvasOffset = 0x3c;
//: `IsaacRepentance::WIDTH` / `HEIGHT` 的 GOT 槽（`get_target_offset` 里就是这么取的：
//: `adrp x8,0xaac000; ldr x8,[x8,#0x650]; ldr s0,[x8]` ⇒ 槽里放的是**指向 float 的指针**）。
constexpr std::uintptr_t kWidthSlotOffset = 0xAAC650;
constexpr std::uintptr_t kHeightSlotOffset = 0xAAC658;

// ── 那一列（选择界面）：`Menu_Game` 那一屏 ─────────────────────────────────────
//
// 三条引擎事实（都反汇编核过）：
//   ① `Menu_Game::Render` 对每行做 `GetLayer(i); s0=[layer+0x48]; s0+=k; [layer+0x48]=s0`
//      ⇒ **`图层+0x48` 是每行自己的 X 偏移、`+0x4C` 是 Y**，我们也能写（"把下面几行挪下去"的抓手）；
//   ② 光标帧由 `Menu_Game::Update` 设，**Render 自己不碰**；而我们的中继在 Render 入口
//      ⇒ **我们这一帧设的帧号，在本帧的绘制里一定生效**；
//   ③ 引擎只认 5 项（`cmp w8,#4`）。**我们绝不让索引越界**：写回的是**行号**、再夹在 0..4，
//      第 6 格（我们最后一格）的光标靠"我们自己设帧号"实现 —— 所以不存在"越界查表"的风险。
constexpr std::uintptr_t kMenuGamePageOffsetInMenuManager = 0x813A0;
constexpr std::uintptr_t kPageSelectedIndexOffset = 0x4;
constexpr std::uintptr_t kPagePositionOffset = 0x8;
//: 页面对象里的 ANM2（`Menu_Game::Render` 里 `add x21, x19, #0x10` 之后交给 `ANM2::Render`）。
constexpr std::uintptr_t kPageAnm2Offset = 0x10;
//: ANM2 对象里的**图层数**（`int`）。证据：`ANM2::GetLayer(int)` 与 `ANM2::Load` 都读它当上界
//: （`ldr w8,[x20,#0xb0]; cmp w8,w19; b.gt` 之后按 `[x20,#0xa8] + index*0xB0` 取图层）。
//: ⚠️ **`GetLayer` 越界时不返回空指针**（它只打一条日志、照样算出界地址），所以判"有没有那一层"
//: 必须读这个计数，**绝不能**用 `GetLayer(12)` 是不是空来判 —— 那是读越界内存。
constexpr std::uintptr_t kAnm2LayerCountOffset = 0xB0;
//: 引擎自己那份菜单动画在"补回 `Item6`"之后的图层数（原版 12 层 + 我们补回去的那一层）。
//: 补层工具与门禁见 `tools/gamemenu_mod_row.py --emit-menu-anm2`。
constexpr std::uint32_t kMenuGameLayerCountWithModRow = 13;
//: `MenuManager::eState` 的"选择界面"那一格（`Menu_Game`）。
//: 静态表：3 = Menu_Game（`MenuManager+0x813A0`），与 `Menu_Game::Update` 开头的 `cmp w8,#0x3` 互证。
constexpr std::uint32_t kGameMenuState = 3;
//: 引擎确认键跳表里"我们那一格之后"的那两页（用来做保险：见 `SetState` 中继）。
//: 静态表：9 = Stats、10 = Options。
constexpr std::uint32_t kStatsState = 9;
constexpr std::uint32_t kOptionsState = 10;

// ── 动作号 ────────────────────────────────────────────────────────────────────
//
// `0x13`/`0x14` 是 `Menu_Game::Update` 里上下键用的动作号（`IsActionPressed(0x13/0x14, -1, 0)`）。
// `0x0E` = `ACTION_MENUCONFIRM`、`0x0F` = `ACTION_MENUBACK`（两条可复核的依据：
// `Menu_Title::Update @0x41A4F0` 里 `mov w1,#0xe` ⇒ `SetState(2)`；`Menu_Game::Update` 的
// "那一行确认"分支在 `0x40D730` 也是 `mov w1,#0xe`，而 `0x40d890` 处是 `mov w1,#0xf`）。
// ⚠️ 探针第一版把确认写成了 `0x0F`（那是返回），一直没暴露是因为当时只记数、没接页面。
constexpr std::uint32_t kActionUp = 0x13;
constexpr std::uint32_t kActionDown = 0x14;
constexpr std::uint32_t kActionConfirm = 0x0E;
constexpr std::uint32_t kActionBack = 0x0F;
//: "任一控制器答'是'"：游戏自己的菜单代码用的就是这个值（`Menu_Title::Update @0x41A4F0`
//: 里是 `mov w2, #-1`）。**不能只问手柄号 0** —— 真机上出现过 33（项目历史结论）。
constexpr std::uint32_t kAnyController = 0xFFFFFFFFu;
constexpr std::uint32_t kScanControllers = 64;

//: 兜底那一行画什么。**必须用 ASCII**：游戏自带字体没有中文字形（探针实测：画中文一片空白），
//: 而周围五行烤在图里的字本来就是英文。带中文字形的那份字体留给**模组页里的模组名**用。
constexpr char kModRowLabel[] = "MODS";
//: 兜底那行字的颜色 = **纸上烤的那套字**的墨色（把 `gamemenu.pcx` 解出来取墨迹像素，最暗/最常见
//: 的是 `(55,43,45)` 深褐，不是纯黑）。
//: ★ 探针里这一处是**纯红**：那是探针的信号（屏幕上看到红色 MODS = 贴图那条链还断着），
//:   而生产版走兜底是**正常形态**（覆盖层没装/被回退），颜色必须与纸上的字一致，红色是错的。
constexpr float kModRowTextColor[4] = {55.0F / 255.0F, 43.0F / 255.0F, 45.0F / 255.0F, 1.0F};
//: 兜底字的位置：x 对齐引擎自己那几行的文字左边（行图框 x≈185，烤的字在框内 +7 左右）。
constexpr float kModRowTextX = 192.0F;
//: 万一布局还没定（语言没取到）时的文字锚点 —— 048 批真机验过的那个值。
constexpr float kModEntryTextYFallback = 124.0F;
//: 字号 = **量出来的字高** ÷ 当前字体的行高（换字体自动适应，不用手调）。
//: 兜底用的"美术里那行字高"：中文那一列量出来约 28 格。
constexpr float kModRowArtTextHeight = 28.0F;
//: 行高拿不到（守卫不过）时的兜底缩放。
constexpr float kModRowTextScaleFallback = 2.0F;

// ── 批次 124 / 126：模组页**第 1 行** = 「Console: ON/OFF」（控制台总开关）────────────
//
// 用户定案：PC 的控制台靠 `options.ini` 的 `EnableDebugConsole` 开，我们这边换成**模组菜单里的开关**。
// 它**不是模组**：不进模组清单、不参与"启用模组数"与禁成就判据、也不占那 4 个加载名额。
//
// ★★ 批次 126（用户 2026-09-25 原话："你也别画在其他位置了，你就作为模组的一个写在第一个模组位置上吧，
//    其他 mods 中的模组按顺序从 2 开始排"）：它就写在**模组列表的第 1 格**里。
//    引擎给每行加的前缀是 `%d.`（从 1 起，见 `mod_page_entries.hpp` 顶部）⇒ 这一行显示成
//    `1.Console: ON`，真正的模组顺延成 `2.`、`3.`…。
//
//    怎么做到的：这一页的**列表内容本来就是我们自己造的**（`TryPrepareModsVector` 把
//    `BuildModPageEntries` 造好的条目写进引擎那个 vector，引擎只按行画）⇒ 把这一条造在
//    **下标 0**、其余全部顺延即可。好处是光标、高亮、滚动**全部回到引擎的原生行为**：
//    我们不再自己画字，也不再需要"往引擎的选中项里写负一哨兵"那一套（批次 124 的做法，
//    它当年是为了绕开"我们那一行不在列表里"而生的）。
//
//    边界（两条，都是既有设计的自然结果，不是新限制）：
//      * **一个模组都没发现时不写这张表**（保持"等发现结果"的时序逻辑，`DecideModPageSource`
//        把"目录 0 条 + 还没到尝试上限"判成等）⇒ 那种情况下这一行也进不去；
//      * 条目总容量 32 格（`kEntryCapacity`），本行占 1 格 ⇒ 留给"发现到的模组"的是 31 格。
//: 这一行在条目表里的下标：**0 = 第一个模组位置**，真正的模组都排在它后面。
constexpr std::uint32_t kConsoleRowEntryIndex = 0;
//: 这一行现在该写什么名字（跟着开关状态走）。
//:
//: 为什么要一个函数而不是"两处各写一遍"：条目里的 `std::string` 数据指针由
//: `SyncConsoleRowName()` 每帧指向这两个常量之一（引擎的 `Render` 只把它当 `%s` 用）
//: ⇒ 拨动开关**同一帧**名字就变，不必重建整张表（重建要重读所有 `metadata.xml`，几十次文件读）。
const char* ConsoleRowName() {
    return isaac::runtime::console::ConsoleControlRowName();
}

// ── 模组页（引擎状态 16）──────────────────────────────────────────────────────
//
// **为什么是状态 16**：PC 上"选模组"就是让引擎切到状态 16；Switch 版只把这一格从
// `MenuManager::Update` 的分派表（0..15）与 `MenuManager::Render` 的页面清单里删了，
// 页面代码（`Menu_Mods` 六个方法）与资源都还在（证据见 `mod_page_nav.hpp` 的注释）。
//
// **为什么自己维护输入、不调引擎的 `Menu_Mods::Update`**：它按确认会往模组目录写/删
// `disable.it`，而卡上模组目录就在 **romfs 覆盖层**里 —— 那正是"写覆盖层 ⇒ 下次启动崩"的雷区。
// ⇒ 页面只借引擎的 `Render`，输入与开关状态由我们维护（`mod_page_nav.hpp`，有宿主门禁）。
//
// 条目表要的数据结构（静态已确认，见 `mod_page_entries.hpp`）：
//   * `g_Manager + 0x36800` 起三个字 = `std::vector<条目指针>` 的 begin / end / cap；
//   * 每个条目 `+0x18` 是 libc++ `std::string`（长串形态）、`+0x138` 启用位、`+0x13a` "旧版"位。
constexpr std::uintptr_t kMenuModsCtorOffset = 0x41008C;
constexpr std::array<std::uint8_t, 16> kMenuModsCtorExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
constexpr std::uintptr_t kMenuModsInitOffset = 0x4100C4;
constexpr std::array<std::uint8_t, 16> kMenuModsInitExpected = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF5, 0x1B, 0x00, 0xF9,
};
constexpr std::uintptr_t kMenuModsRenderOffset = 0x4107C4;
constexpr std::array<std::uint8_t, 16> kMenuModsRenderExpected = {
    0xFF, 0x03, 0x06, 0xD1, 0xEC, 0x7B, 0x00, 0xFD,
    0xEB, 0x2B, 0x10, 0x6D, 0xE9, 0x23, 0x11, 0x6D,
};
//: `Menu_Mods::Reset()`：进入模组页时调一次（把选中项归零、重读 ModManager 指针）。
//: 引擎自己的 `MenuManager::SetState` 切页时会替各页面做这件事，但**它没有状态 16 那一格**
//: ⇒ 这一下得我们替它做（等价于 PC 的 `SetState(模组)` 里那次 `Reset`）。
constexpr std::uintptr_t kMenuModsResetOffset = 0x4101B4;
constexpr std::array<std::uint8_t, 16> kMenuModsResetExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};

// ── 换语言：**照引擎自己那套协议做**（079 → 080 撤回 → **083 重新启用，真机已验收**）────────
//
// 引擎里确实有一整套换语言协议 —— `PerformLanguageSwitch(eLanguage)`（`0x3B39C0`），顺序：
//   ① `MenuManager::PreLanguageSwitch()`（对每个页面调 `页面::PreLanguageSwitch()`，紧接着 `页面::Reset()`）
//   ② `AnmCache::FreeUnreferencedImages()` + `AnmCache::FreeUnreferencedEntries()`
//   ③ `Manager::SetLanguage(eLanguage)`（重建语言挂载点）
//   ④ `MenuManager::PostLanguageSwitch()`（对每个页面调 `页面::PostLanguageSwitch()`）
//   ⑤ `Manager/Game::PostLanguageSwitch()` + `MenuManager::ResetCharacterMenu()`
// 我们照抄的是其中与"这张纸"有关的三步（① 里的 `Menu_Mods::PreLanguageSwitch` → ② → ④ 里的
// `Menu_Mods::PostLanguageSwitch`），实际调用在 `ReloadPageForLanguage()`。
// 而 `Menu_Mods` 自己也有这两个钩子：`PreLanguageSwitch`（`0x41021C`）= `add x0,x0,#0x10; b ANM2::Reset`；
// `PostLanguageSwitch`（`0x410224`）= 与 `Init` 同一套重新加载（不碰构造函数、不动页面位置）。
// 另外 `g_AnmCache` 是 `std::__1::map<uint32_t, Entry2>`、键 = `AnmCache::FNHash(路径串)`（`0xF4E8`）
// = **路径串一样就分不出语言**，这就是"换语言后排版不跟着换"的根因（贴图会跟着换，因为
// `load_graphics` 每次都按当前挂载层重新解析精灵表）—— 也正是**必须**做第②步的原因。
//
// ★★ **这段历史能替你省一轮真机，读完再动手**：
// 079 第一次做这三步时，真机上出现"EID 的信息显示被搞坏了"（用户原话"大部分信息都没有，
// 只有一个很浅的图标在闪烁"），于是 080 撤回，并在注释里写下"第②步不能调、别再试"。
// **但那个归因是误判** —— 当时"换语言丢 Mod 挂载点"那个 bug 还在（082 才修掉），EID 在那种
// 情况下**不管怎样都会坏**；而且 080 撤回之后 EID 照样坏（当时的记录自己就写了这一点）。
// ⇒ 083 把这三步拿回来重试，**083-补 真机验收："三条全部通过"、用户原话"一切正常"**
//   （① 换语言后 EID 不再坏 ② 进模组页不再自动翻第一个开关 ③ 排版当场就跟着换）。
// ⇒ 所以**不要再照旧注释说的"退回不做"**：① 门禁 `test_mod_menu_native_production.py` 是**正向**
//   判据（三步必须在、顺序必须 Pre → 回收 → Post、四个入口必须逐字节守卫过、不许重跑 `ctor`）；
//   ② 真机已经通过。
// ★ **万一将来又出现"换语言后 EID 坏"**：先读**状态面 [24]**与**读数工具里的 Lua 错误历史**，
//   **不要再直接把锅甩给这两个回收函数**（082 那次真凶是"换语言后 Mod 挂载点没恢复"）。
//   完整过程见 `docs/改动日志-20260923.md` 的 083 与 `083-补`、
//   `dist/change-archive-20260923/082-language-switch-and-mod-page-fixes/README.md`，
//   以及 `docs/问题记录-换语言后EID显示坏掉-20260923.md` 顶部那节。
//: `MenuManager::SetModsOffset(int)`：把"模组页那一格"的滚动目标写成"第 n 条"。
//: 进页面时先调一次 `SetModsOffset(0)`，让那一格的 Y **立刻**变成确定值 —— 否则要等页面自己
//: `Render` 一次才拿得到它，而"算位置"就发生在那一帧之前。
//: ★ 真机实测（探针批次 064）：不先调的话，重启后第一次进来会**错位 1~2 秒**（读到 `Init` 的旧值
//:   -290，而实际是 -216，差 74 格）。
//: `Menu_Mods::PreLanguageSwitch()`（`0x41021C`）= `add x0,x0,#0x10; b ANM2::Reset` ——
//: **放开**这份动画（还掉缓存引用、清掉路径串、放掉图层持有的贴图引用）。
//: `Menu_Mods::PostLanguageSwitch()`（`0x410224`）= 按**当前**语言重新 `Load` + `Play("Main")` + …，
//: 与 `Init` 同一套动作，只是**不碰构造函数、也不动页面位置**。
constexpr std::uintptr_t kMenuModsPreLanguageSwitchOffset = 0x41021C;
constexpr std::array<std::uint8_t, 16> kMenuModsPreLanguageSwitchExpected = {
    0x00, 0x40, 0x00, 0x91, 0xBC, 0x7F, 0x09, 0x14,
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
};
constexpr std::uintptr_t kMenuModsPostLanguageSwitchOffset = 0x410224;
constexpr std::array<std::uint8_t, 16> kMenuModsPostLanguageSwitchExpected = {
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF4, 0x4F, 0x03, 0xA9,
};
//: `AnmCache::FreeUnreferencedEntries()`（`0x14F64`）/ `FreeUnreferencedImages()`（`0x156B4`）：
//: 回收"没人引用"的动画条目 / 贴图。★ 这两个是**全局**的，只在"照引擎自己的换语言协议"时调，
//: 而且调之前必须先把本页的引用放开（`PreLanguageSwitch`），否则清不掉那份旧语言的动画数据。
constexpr std::uintptr_t kAnmCacheFreeUnreferencedEntriesOffset = 0x14F64;
constexpr std::array<std::uint8_t, 16> kAnmCacheFreeUnreferencedEntriesExpected = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
constexpr std::uintptr_t kAnmCacheFreeUnreferencedImagesOffset = 0x156B4;
constexpr std::array<std::uint8_t, 16> kAnmCacheFreeUnreferencedImagesExpected = {
    0xFD, 0x7B, 0xBB, 0xA9, 0xFA, 0x67, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};
//: `g_AnmCache` 的 GOT 槽（`0xAAC6A0`）：**读一次就是对象地址**（引擎自己的写法是
//: `adrp x0,0xaac000; ldr x0,[x0,#0x6a0]` 之后直接当 `this` 用，只有一次取值）。
constexpr std::uintptr_t kAnmCacheSlotOffset = 0xAAC6A0;
constexpr std::uintptr_t kSetModsOffsetOffset = 0x3FF6F4;
constexpr std::array<std::uint8_t, 16> kSetModsOffsetExpected = {
    0x3F, 0x14, 0x00, 0x71, 0x8A, 0x00, 0x00, 0x54,
    0x08, 0x6B, 0xB8, 0x52, 0x00, 0x01, 0x27, 0x1E,
};

// ── ANM2 两个跳板 ─────────────────────────────────────────────────────────────
//
// `ANM2::GetLayer(int)` / `ANM2::SetLayerFrame(int,int)` 的**跳板**（引擎自己也是调这两个地址）。
constexpr std::uintptr_t kAnm2GetLayerStubOffset = 0x66FCB0;
constexpr std::array<std::uint8_t, 16> kAnm2GetLayerStubExpected = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0xE2, 0x46, 0xF9,
    0x10, 0x02, 0x37, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
constexpr std::uintptr_t kAnm2SetLayerFrameStubOffset = 0x670C20;
constexpr std::array<std::uint8_t, 16> kAnm2SetLayerFrameStubExpected = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0xBE, 0x42, 0xF9,
    0x10, 0xE2, 0x15, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};

// ── 引擎字体对象：**本批确认不再动它**（2026-09-23，批次 078）─────────────────────
//
// 077 曾把一份带中文字形的扩展字体（`font/…Extended12.fnt`，TeamMeat 字面的扩展版）
// 装进**引擎自己的**字体对象（`g_Manager + 0x117120`，也就是 `Menu_Mods::Render` 画每一行时用的那份），
// 为的是让中文模组名能画出来。**真机验收推翻了这个前提**：
// `Menu_Mods::Render`（`0x4107C4`）用的是**按字节**的那个重载 `Font::DrawStringScaled(char const*…)`
// —— 它把字符串里**每个字节**当一个字形编号；中文在 UTF-8 里是 3 字节、每字节 ≥ 0x80
// ⇒ 只会画出 3 个毫不相干的字形。引擎另有一套 UTF-8 家族（`DrawStringScaledUTF8` /
// `GetStringWidthUTF8`，先转 UTF-16），而**模组页没用它** ⇒ **换字体救不了中文**。
// 代价却是真的：多加载一份 2048×2048 × 2 页的字图集（约 32MB），观感也会变
// （换成扩展版后点阵画得略细，用户当场就看出来了）。
//
// ⇒ 本批**整个撤掉**换字体那段接线：这个对象现在只被**读**
// （兜底画字时取行高，见 `DrawRowLabel`），**一个字节都不写**。
// 中文模组名的问题改为"等真有中文名模组时单独立项"（见交接文档第五节 C）。
// 状态面里 `fontObjectWrites` 那一格就是这条纪律的载体：它数"我们改写过几次引擎字体对象"，恒 0。
//
// ⚠️ 路径仍然不许用 `font/CJK/LanaPixel.fnt`：它的图集背景是不透明黑，真机上被画成黑方块
// （探针第一版实测），比"没有中文"更糟。

// ── 页面摆放（探针批次 042/063/066 的结论）────────────────────────────────────
//
// **引擎自己的页面约定**：`titlemenu`/`saveselectmenu`/`statsmenu`/… 的内容全部落在
// `x∈[0,480]`、`y∈[0,270]` ⇒ **页面原点 = 一个 480 宽页面的左上角**。
// 而模组页那张纸的设计是**以原点为中心**的：纸 = `480×900 @(-240,-72)`；`Menu_Mods::Render`
// 里那句 `+200`（`mov w8,#0x43480000` = 200.0f）正是"把居中布局挪成页面框布局的那一下"。
// ⇒ 要让纸铺满页面框、上沿压在页面顶端，原点应当是 **(240, 72)**。
//
// ★★ 横向 173 = **按 PC 引擎自己的公式换算出来的**：把 PC 的 `isaac-ng.exe`（PE32，32 位）
// 反汇编后，画布偏移的收敛目标写得很清楚：`((屏幕宽−480)/2 + 家位置x, …)`，而 `MenuManager::Init`
// 给每个页面写的位置是**家位置取负** ⇒ 页面最终原点 = 居中量 + (200,0)。
//   * PC 屏幕铺满整个 480×270 画布 ⇒ 居中量 0 ⇒ 原点 (200,0)；
//   * Switch 屏幕只有 426×240 ⇒ 居中量 ((426−480)/2, (240−270)/2) = (−27,−15)
//     ⇒ 同一套布局换算到 Switch 上，横向应当是 200 − 27 = **173**。
// 纵向仍取 72（批次 042/056 真机验收过的值）：按公式应得 −15，但那会让纸的上沿跑出屏幕外
// ⇒ 纵向这一格的残差尚未定性，**以真机验收为准，不按公式硬套**。
constexpr float kPageBoxWidth = 480.0F;
constexpr float kModsSheetOffsetY = -72.0F;   // 纸相对原点的左上角 Y
constexpr float kModsRenderExtraX = 200.0F;   // `Menu_Mods::Render` 自己加的那 200 格
constexpr float kModsPageTargetOriginX = 173.0F;
//: ★★ 2026-09-27 真机**实测**：按 `(screenHeight − 270)/2 = −15` 推出来的目标与"画布实际停的位置"
//: **差 120 格**（批次 171 读数：纸画在 `(173.0, -48.0)`，而验收过的静止位置是 `(173, 72)`，
//: 差正好 −120）。X 那一侧是对的（实测 173 ✓）⇒ 只有 Y 的居中量差这一项。
//: 在此之前（批次 063~166）是那段"停稳后校正"在吃这个差 —— 所以它才必须存在；
//: 现在把**实测值**直接算进公式，位置就能在 `Init` 时一次算准（不再依赖事后校正）。
constexpr float kModsPageCenterYAdjust = 120.0F;
//: "算画布停稳"的帧数阈值（60 Hz 下 20 帧 ≈ 1/3 秒；转移动画本身约 0.5~0.9 秒）。
constexpr std::uint32_t kSettleFrames = 20;

// ── 条目来源 ──────────────────────────────────────────────────────────────────
//
// 容量与"一次最多加载几个模组"**同一个数**：能加载却放不下那种情况没有人会想到去查，
// 也不该出现（`mod_page_runtime_sources.hpp` 里的 `kModPageMaximumMods` 就是它）。
constexpr std::uint32_t kEntryCapacity = isaac::runtime::kModPageMaximumMods;
//: 留给"启动扫描发现到的模组"的格数 = 总容量让出 **1 格**（批次 126）。
//:
//: 为什么必须显式让：`CollectRuntimeModPageSources` 的 `capacity` 参数就是"装不下"的判定口
//: —— 传总容量的话，发现到 32 个模组时正好占满，再加我们那一行（下标 0）就越界；
//: 传 31 则"发现到 32 个"照旧走既有的"装不下 ⇒ 整体放弃"（页面空表，不写半截）。
constexpr std::uint32_t kModSourceCapacity = kEntryCapacity - 1U;
//: 名字缓冲要**两份**：来源侧一份（`CollectModPageSources` 往里写显示名），条目侧一份
//: （`BuildModPageEntries` 把名字抄进去，条目里的 `std::string` 从此指向它）。
//: 放不下时两条路都是**整体放弃**（绝不写出半截结构）。
constexpr std::size_t kEntryNameBytes = 8192;
constexpr std::size_t kSourceNameBytes = 8192;
//: 一帧最多试几次"等发现结果"（≈15 秒 @60fps）。
//:
//: **为什么要等**：发现结果（`ModMenuPublishDiscovered`）是**启动的模组加载**填进去的，
//: 而那是 worker 线程（构建还专门给了它 5 秒启动延迟）。而"`g_MenuManager` 非空"只说明菜单
//: 系统构造好了，**不保证模组已经扫完**。不等的话会读到"0 个模组"，而那张表只会写一次。
constexpr std::uint32_t kPrepareAttemptLimit = 900;

// 失败码（写进状态面 [2]，读数里一眼看出卡在哪一步）。**与探针同一套语义**。
enum : std::uint32_t {
    kFailureNone = 0,
    kFailureInputUnavailable = 1,
    kFailureModuleNotFound = 2,
    kFailureSetStateGuard = 3,
    kFailureMenuManagerNull = 4,
    kFailureMenuModsGuard = 5,
    kFailureRenderGuard = 6,
    kFailureEntryBuild = 7,       // 条目没造出来
    kFailureManagerNull = 8,      // `g_Manager` 没读到（写条目的前置条件）
    kFailureTitleRelayGuard = 9,  // `Menu_Title::Render` 入口与期望不符（版本不对）
    kFailureModRowGuard = 10,     // `Menu_Game::Render` 入口与期望不符（同上）
    kFailureMenuModsResetGuard = 11,  // `Menu_Mods::Reset` 入口与期望不符
    kFailureLanguageSwitchGuard = 12,  // 换语言那三下的入口（或 `&g_AnmCache`）对不上 ⇒ 不调用
};

// `pageInitState` 的取值。
enum : std::uint32_t {
    kInitNotTried = 0,
    kInitOk = 1,
    kInitGuardMismatch = 2,
    kInitMenuManagerNull = 3,
};

// ── 上下文 ────────────────────────────────────────────────────────────────────

//: `Menu_Mods` 的**静态壳**。
//:
//: 为什么需要它：`Menu_Mods` 是 `MenuManager` 的**内嵌成员**，而它的偏移与大小都没有定论
//: （状态表里那 17 格是"位置/滚动"槽，不是页面对象）。探针用一块**静态零初始化**的内存当壳、
//: 在上面调 `ctor` + `Init` + `Render`，真机跑通了 ⇒ 生产版照用同一形状。
//: 静态已确认的布局：`+0x00` 选中项、`+0x04` 按住计时、`+0x08` Vector2、`+0x10` ANM2、
//: `+0x124` "改过没有"、`+0x170` ModManager ⇒ 0x800 足够，且都落在零初始化内存里。
alignas(16) std::uint8_t g_ModsObject[0x800]{};
float g_ModsPosition[2] = {0.0F, 0.0F};  // `KAGE::Math::Vector2` = 两个 float

//: 条目存储：条目数组、指针数组、`begin/end/cap` 三个字、名字缓冲。**静态零初始化，不写堆**。
alignas(16) std::uint8_t g_Entries[kEntryCapacity][isaac::runtime::kModPageEntryStride]{};
std::uintptr_t g_EntryPointers[kEntryCapacity]{};
alignas(8) std::uintptr_t g_EntryVector[3]{};
isaac::runtime::ModPageEntrySource g_Sources[kEntryCapacity]{};
char g_EntryNameArena[kEntryNameBytes]{};    // 条目里的字符串指向它
char g_SourceNameArena[kSourceNameBytes]{};  // 来源的 displayName 指向它
char g_MetadataScratch[isaac::runtime::kModPageMetadataCapacity]{};
char g_MetadataPath[isaac::runtime::kModPageMetadataPathCapacity]{};

//: 一次性核对过的引擎入口与运行时指针。
struct Context {
    using GetLayerFn = void* (*)(void*, int);
    using SetLayerFrameFn = void (*)(void*, int, int);
    using DrawTextFn = void (*)(void*, const char*, float, float, float, float, const void*, int,
                                bool);
    using FontLineHeightFn = float (*)(const void*);
    using GetLanguageCodeFn = const char* (*)(void*);
    using CtorFn = void (*)(void*);
    using InitFn = void (*)(void*, const float*);
    using RenderFn = void (*)(void*);
    using ResetFn = void (*)(void*);
    using SetModsOffsetFn = void (*)(void*, int);

    GetLayerFn getLayer{nullptr};
    SetLayerFrameFn setLayerFrame{nullptr};
    DrawTextFn drawText{nullptr};
    FontLineHeightFn lineHeight{nullptr};
    //: `Manager::GetLanguageCode()`：按语言码挑那一套生成的美术布局。
    GetLanguageCodeFn getLanguageCode{nullptr};
    CtorFn modsCtor{nullptr};
    InitFn modsInit{nullptr};
    RenderFn modsRender{nullptr};
    ResetFn modsReset{nullptr};
    SetModsOffsetFn setModsOffset{nullptr};
    //: 换语言那三下（照引擎 `PerformLanguageSwitch` 对每个页面的做法，见 `ReloadPageForLanguage`）。
    using PageHookFn = void (*)(void*);
    using AnmCacheFreeFn = void (*)(void*);
    PageHookFn modsPreLanguageSwitch{nullptr};
    PageHookFn modsPostLanguageSwitch{nullptr};
    AnmCacheFreeFn freeUnreferencedEntries{nullptr};
    AnmCacheFreeFn freeUnreferencedImages{nullptr};
    //: 读 `metadata.xml` 那组绑定（`GameFileReader::ReadTextFile`）。
    GameFileReader::Bindings fileBindings{};
    bool fileBindingsOk{false};
    //: `metadata.xml` 三种结果各几次（**读数用**：判断"名字为什么退成了目录名"）。
    //: `rootRelative` = 用应用根相对名解析成功（现在的口径）；`prefixed` = 只有带 `rom:/` 那种成了；
    //: `misses` = 两种都没解析到（那一行会退成目录名）。
    std::uint32_t metadataRootRelativeHits{0};
    std::uint32_t metadataPrefixedHits{0};
    std::uint32_t metadataMisses{0};
    //: 本次开机**实际加载**的**真实模组**（`mods/` 里那些，不含运行时自带的菜单模组）个数。
    //: 口径 = `ModMenuActiveCount()`（启动时 `ModMenuMarkActive` 标出来的那批）。
    //: ★ 2026-09-24 批次 107 起它只作**诊断**用（判据改看下面那个"启用状态"的）。
    std::uint32_t activeRealMods{0};
    //: 处于**启用状态**的真实模组个数（口径 = 模组页开关那一份，**不看有没有重启**）。
    //: ★ 2026-09-24 批次 107 起「该不该禁成就」的判据就是它 —— 与 PC 的
    //: `ModManager::AchievementsLocked()` 同口径（走列表里每一项的启用位）。
    std::uint32_t enabledRealMods{0};
    // ---- 批次 116 加的"发现清单自证"四格（发布进状态面 [41]..[44]，一一对应）----
    // 为什么要有它们：上面两个只是**汇总数**，而待修记录里 `[40] = 0` 与"开关服务读不出来时
    // 本该默认全都开着"是矛盾的 —— 汇总数分不出"清单是空的 / 每一条都被判成关闭 /
    // 发现这一步根本没跑到"，而这三者的处置完全不同（见状态面 `.hpp` 那一段的判读表）。
    std::uint32_t discoveredRealMods{0};
    std::uint32_t discoveredEnabledMask{0};
    std::uint32_t discoveredActiveMask{0};
    std::uint32_t discoveryDone{0};
    std::uint32_t wombAchievementUnlocked{0};
    std::uint32_t achievementsReadOnly{0};
    //: 成就位数组的抽样（`PersistentGameData+0x28` 起 4 个字节）—— 读数里自证位置没读错。
    std::uint32_t achievementSample{0};
    //: `IContentManager::GetMountedFilePath`：返回堆上挂载绝对路径（空 = 不在任何挂载点）。
    //: **优先用中继记下的原函数**：这个函数的入口已经被我们自己的贴图桥改写成跳转了，
    //: 比原版序言必然失败（2026-09-21 真机掩码 0x20 就是这么来的）。
    using GetMountedFn = char* (*)(void*, const char*);
    GetMountedFn getMounted{nullptr};
    //: `g_ContentManager` 对象指针（`base + 0xAAC748` **读一次**就是它）。
    void* contentManager{nullptr};
    //: 还那条堆路径用的 —— **必须用游戏自己的 `operator delete[]`**。
    GameFileReader::GameOperatorDeleteArrayFn freePath{nullptr};
    //: 运行时值（每帧刷新）。
    std::uintptr_t manager{0};       // `g_Manager`（字体对象嵌在它里面）
    std::uintptr_t menuManager{0};   // `g_MenuManager`
    std::uint32_t menuState{0};      // `MenuManager+0x38`（渲染回调靠它门控）
    float screenWidth{0.0F};
    float screenHeight{0.0F};
    //: 挑中的那一套布局（按游戏语言码，见 `mod_row_generated.hpp`）。
    const isaac::runtime::ModRowLayout* layout{nullptr};
    char language[4] = {0, 0, 0, 0};
    //: 语言码是不是已经读到过至少一次 —— 有了它，"`language` 变了"才有意义（第一次不算变）。
    std::uint32_t languageSeen{0};
    //: 1 = 语言变过、等模组页**不显示**时把页面动画按新语言重载一次（见 `ReloadPageForLanguage`）。
    std::uint32_t pageReloadPending{0};
    std::uint32_t languageState{0};  // 0 没试 / 1 ★ 拿到 / 2 入口守卫不过 / 3 单例空 /
                                     // 4 挑到的是 `en` 兜底（不是本语言的美术）
    std::uint32_t entryGuardState{0};  // 0 没试 / 1 ★ 全部过 / 2 有入口不符（不调用）
    std::uint32_t pageInitState{kInitNotTried};
    std::uint32_t prepareAttempts{0};
    std::uint32_t vectorWritten{0};
    std::uint32_t writtenDirectories{0};
    //: ★ 批次 169：页面位置那套小状态机（positionSet / 落位校正 / 每帧重写）**整套删掉了** ——
    //: 位置现在只在 `Init` 时算一次（见 `ComputeModsPagePosition`），之后一个字节都不写。
    //: 上一帧是否在模组页里 —— 用来识别"**刚刚离开**"这一刻（在那时落盘一次）。
    std::uint32_t pageWasActive{0};
};
Context g_Menu{};

//: 当前选中第几格（0..5，3 = 我们那一格）。进入那一屏时按引擎的行号初始化。
std::uint32_t g_Slot = 0;
std::uint32_t g_SlotInit = 0;
//: 从模组页回来时，光标要回到**我们那一格**（而不是按引擎行号换算出来的邻格）。
//:
//: 为什么需要它：我们那一格（slot 3）写回给引擎的行号是 **3**（`EngineRowForSlot(3) == 3`），
//: 而"引擎行号 → 我们的格子"的换算是"≥ 我们的落点就 +1"（插进去的那一格占了原来的第 4 格）
//: ⇒ 引擎行号 3 会被换成**第 5 格（统计数据）**，光标就跑到隔壁去了。
std::uint32_t g_RestoreOurs = 0;
//: 上一帧的按键状态（**自己算边沿**）：引擎那份"刚按下"状态在我们跑到它的时候是空的
//: （结论写在 `input_api.cpp` 里），所以沿用"按住"位图 + 自记状态。
std::uint32_t g_LastUp = 0;
std::uint32_t g_LastDown = 0;
std::uint32_t g_LastConfirm = 0;
//: 模组页那一边的边沿（与"我们那一格"那套分开记，免得两个屏幕互相污染）。
std::uint32_t g_PageLastUp = 0;
std::uint32_t g_PageLastDown = 0;
std::uint32_t g_PageLastConfirm = 0;
std::uint32_t g_PageLastBack = 0;

//: 与 `input_api.cpp` 同一个调用形状（那处是权威）：第一个参数被跳板覆盖，动作号进 x1、
//: 手柄号进 x2、第三个引擎参数（PC 的可选 `entity`）一律给空指针。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);

// ─────────────────────────────────────────────────────────────────────────────
// 基础工具
// ─────────────────────────────────────────────────────────────────────────────

//: 解析一个引擎入口 ⇒ **直接得到带签名的可调用指针**（批次 108 起本 TU 唯一的入口解析形状）。
//:
//: 三件事一次做完：范围判据、可读判据、16 字节序言的**逐字节核对**，全在引擎调用层
//: （`engine_call::ResolveFunction`）；这里只回答"我们要调的是哪个入口"。
//: 任一条不成立 ⇒ `nullptr` —— **绝不把没核对过的地址变成能调的东西**。
//:
//: `ok` 是**累积**语义（原来 `Guarded(...) && ok` 那个形状）：给了一串入口要一起核对时，
//: 只要有一条不过，后面的入口**一律不给**（免得"半套入口"被拿去用）。传 `nullptr` 表示只要这一个。
template <typename Fn>
Fn VerifiedEntry(const TargetModule& module, std::uintptr_t offset,
                 const std::array<std::uint8_t, 16>& expected, bool* ok = nullptr) {
    const Fn entry = engine_call::ResolveFunction<Fn>(
        module.base, module.size, offset, expected, &engine_memory::EngineMemoryReadable);
    if (ok == nullptr) {
        return entry;
    }
    *ok = entry != nullptr && *ok;
    return *ok ? entry : nullptr;
}

//: 读一个 GOT 槽里存的东西（= 加载器解析出来的地址）。槽本身必须落在模块映像内。
bool ReadSlot(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* value) {
    if (module.size < sizeof(std::uintptr_t) ||
        slotOffset > module.size - sizeof(std::uintptr_t)) {
        return false;
    }
    const std::uintptr_t slot = module.base + slotOffset;
    if (slot < module.base || slot + sizeof(std::uintptr_t) > module.base + module.size) {
        return false;
    }
    // 取值走访问层（候选地址仍由上面那两条范围判据先筛过一遍 —— 两条都要留着：
    // 范围判据拦的是"偏移本身就不对的调用"，可读判定拦的是"这段映射压根不在"）。
    return engine_memory::ReadAt(slot, value, &engine_memory::EngineMemoryReadable);
}

//: 单例的两级取值（槽 → 全局变量地址 → 值）。返回 false = 这条链不成立，**不许再往下用**。
bool ReadSingleton(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* out) {
    std::uintptr_t global = 0;
    if (!ReadSlot(module, slotOffset, &global) || global == 0) {
        return false;
    }
    // 全局变量本身在模块的 bss 里（例如 `g_MenuManager` 在 0xABCD48），所以这里只做
    // 非空与对齐检查，不要求它落在映像内：超出映像尾部的那段正是 bss。
    // ★ 批次 105：取值改走访问层，于是多一道"这 8 字节可读吗"。bss 是普通的**可读写**映射，
    //   这一道必然通过 —— 它挡的是"读到一段没映射的地址"（那种形态原来会直接崩）。
    if ((global & (sizeof(std::uintptr_t) - 1)) != 0) {
        return false;
    }
    std::uintptr_t value = 0;
    if (!engine_memory::ReadAt(global, &value, &engine_memory::EngineMemoryReadable)) {
        return false;
    }
    if (value == 0) {
        return false;
    }
    *out = value;
    return true;
}

bool Edge(std::uint32_t* last, bool now) {
    const bool pressed = now && *last == 0;
    *last = now ? 1U : 0U;
    return pressed;
}

//: "任一控制器答'是'" —— **不再假设手柄号是 0**（项目历史结论：真机上出现过 33），
//: 并且单独问一次 `0xFFFFFFFF`（游戏自己的菜单代码用的就是这个值，语义是"任意"）。
bool HeldByAnyone(const ActionQueryFn query, std::uint32_t action) {
    if (query(nullptr, action, kAnyController, nullptr)) {
        return true;
    }
    for (std::uint32_t controller = 0; controller < kScanControllers; ++controller) {
        if (query(nullptr, action, controller, nullptr)) {
            return true;
        }
    }
    return false;
}

//: 可见屏幕有多大（`IsaacRepentance::WIDTH` / `HEIGHT`）。
//: GOT 槽里放的是**指向 float 的指针**（`get_target_offset` 里 `ldr x8,[x8,#0x650]; ldr s0,[x8]`），
//: 所以这里读两步：槽 → 指针 → 那个 float。
//: 为什么要它：页面坐标空间是 480×270，可见屏幕比它小、居中裁切 —— 算"纸该摆在哪"要用它。
void RefreshScreenSize(const TargetModule& module) {
    const auto readFloatGlobal = [&module](std::uintptr_t slotOffset, float* out) {
        std::uintptr_t target = 0;
        if (!ReadSlot(module, slotOffset, &target) || target == 0) {
            return false;
        }
        float value = 0.0F;
        if (!engine_memory::ReadAt(target, &value, &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        *out = value;
        return true;
    };
    if (!readFloatGlobal(kWidthSlotOffset, &g_Menu.screenWidth)) {
        g_Menu.screenWidth = 0.0F;
    }
    if (!readFloatGlobal(kHeightSlotOffset, &g_Menu.screenHeight)) {
        g_Menu.screenHeight = 0.0F;
    }
}

//: 读 `MenuManager+0x38`（状态机当前状态）。
std::uint32_t ReadMenuState(std::uintptr_t menuManager) {
    if (menuManager == 0) {
        return 0;
    }
    std::uint32_t state = 0;
    if (!engine_memory::ReadField(menuManager, kMenuManagerStateOffset, &state,
                                  &engine_memory::EngineMemoryReadable, 0)) {
        // 读不到 ⇒ 报"状态 0"（= 不在任何菜单页）。原来会照读、拿垃圾值去比 —— 那正是
        // `EnterModsPage` 那条"必须就在选择界面"的前置判据最怕的东西。
        return 0;
    }
    return state & 0xFFFFU;
}

// ─────────────────────────────────────────────────────────────────────────────
// 条目来源（发现结果 + `metadata.xml` 的 `<name>`）
// ─────────────────────────────────────────────────────────────────────────────

//: 目录来源：直接读 `mod_menu_api` 收下的那份"开机扫描发现到的模组"。
//: 为什么不自已再列一次目录：那会变成两处各维护一份，用户在原生日志页上看到的名字与
//: 自己的 Lua 模组菜单里看到的对不上时，没有人能判断哪一份是对的。
std::uint32_t ProvideDirectories(void* /*context*/, const char** out, std::uint32_t capacity) {
    const std::size_t count = isaac::runtime::ModMenuDiscoveredCount();
    if (count == 0) {
        return 0;
    }
    if (count > capacity) {
        return static_cast<std::uint32_t>(count);  // 装不下：如实报数，由调用方整体放弃
    }
    for (std::size_t index = 0; index < count; ++index) {
        const char* name = isaac::runtime::ModMenuDiscoveredDirectory(index);
        if (name == nullptr || name[0] == '\0') {
            return 0;
        }
        out[index] = name;
    }
    return static_cast<std::uint32_t>(count);
}

//: 开关来源：就是那张纸右边"开着/关着"的依据（同一份数据源，见 `RuntimeMods.List()`）。
bool ProvideEnabled(void* /*context*/, const char* directory) {
    return isaac::runtime::ModMenuDiscoveredEnabled(directory);
}

//: "把这个路径解析成引擎自己能打开的绝对路径" —— **绝不盲开**的最后一步。
//:
//: ★ 反汇编依据：`GetMountedFilePath` 内部是 `get_mount_point(path)` + `FileMap::Get` +
//: `CreateCleanPath`，**全程只查表、不开文件** ⇒ 解析不到只是返回空，不会 Abort。
bool ResolveMountedPath(void* context, const char* path, char* out, std::size_t capacity) {
    auto* source = static_cast<Context*>(context);
    if (source == nullptr || source->getMounted == nullptr || source->contentManager == nullptr ||
        source->freePath == nullptr || path == nullptr || out == nullptr) {
        return false;
    }
    char* mounted = source->getMounted(source->contentManager, path);
    if (mounted == nullptr) {
        return false;  // 这条路径不在任何挂载点 ⇒ 正常（`metadata.xml` 本来就是可选的）
    }
    const std::size_t length = std::strlen(mounted);
    const bool fits = length + 1 <= capacity;
    if (fits) {
        std::memcpy(out, mounted, length + 1);
    }
    // 引擎用 `new[]` 分配的，**只能**用引擎的 `operator delete[]` 还。
    source->freePath(mounted);
    return fits;
}

//: 真正把 `metadata.xml` 读进来（`GameFileReader::ReadTextFile`，与清单/脚本读取同一个入口）。
bool ReadMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                      std::size_t* length) {
    const auto* source = static_cast<const Context*>(context);
    if (source == nullptr || !source->fileBindingsOk || buffer == nullptr) {
        return false;
    }
    // `ReadTextFile` 只在"非诊断构建"或"stage 13"里存在（`game_file_reader.hpp` 的 `#if`）。
    // 本 TU 在诊断构建里也编译 ⇒ 这一块跟着它的可见性走：不可见时如实返回"读不到"
    // ⇒ 所有名字退目录名，而不是编译不过。
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    // 这里那个 `reinterpret_cast<u8*>` 是 `char*` → libnx `u8*` 的**类型别名转换**
    // （`GameFileReader::ReadTextFile` 的参数类型如此），不碰引擎内存 ⇒ 不走访问层。
    const auto result = GameFileReader::ReadTextFile(
        source->fileBindings, path, reinterpret_cast<u8*>(buffer), capacity, length);
    return result == GameFileReader::TextReadResult::Success;
#else
    (void)path;
    (void)capacity;
    (void)length;
    return false;
#endif
}

//: 把"挂载解析 + 读文件"合成 `CollectRuntimeModPageSources` 要的那个 reader：
//: 先解析（`ResolveThenRead` 的纪律），解析不过 ⇒ **绝不**去读。
//: ★ 2026-09-22 真机事故换来的：`File::OpenRead` 对"打开失败"是直接 Abort，而它**不做挂载解析**
//: ⇒ "先问存在性、再拿同一条路径去读"这个写法会崩游戏。这里读的永远是**解析出来的那条绝对路径**。
bool CollectMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                         std::size_t* length) {
    auto* source = static_cast<Context*>(context);
    if (source == nullptr || path == nullptr) {
        return false;
    }
    char resolved[isaac::runtime::kModPageMetadataPathCapacity]{};
    // ① **应用根相对名**（现在的口径，见 `mod_page_sources.hpp` 里那段）：
    //    引擎的挂载解析只认这种形式；带 `rom:/` 前缀那种它答不出来（2026-09-22 实测）。
    if (isaac::runtime::MountedReadResult::Read ==
        isaac::runtime::ResolveThenRead(path, &ResolveMountedPath, source, &ReadMetadataText, source,
                                        resolved, sizeof(resolved), buffer, capacity, length)) {
        ++g_Menu.metadataRootRelativeHits;
        return true;
    }
    // ② 兜底：把带 `rom:/` 前缀那种也试一次（旧口径）。**两种都试是为了把不确定性变成读数** ——
    //    哪一条成了记在状态面 [28] 上，下次真机一眼看得出解析口径对不对，不必再猜。
    const std::size_t lengthWithoutPrefix = std::strlen(path);
    if (lengthWithoutPrefix + 6 < sizeof(resolved)) {
        char prefixed[isaac::runtime::kModPageMetadataPathCapacity]{};
        std::memcpy(prefixed, "rom:/", 5);
        std::memcpy(prefixed + 5, path, lengthWithoutPrefix + 1);
        if (isaac::runtime::MountedReadResult::Read ==
            isaac::runtime::ResolveThenRead(prefixed, &ResolveMountedPath, source, &ReadMetadataText,
                                            source, resolved, sizeof(resolved), buffer, capacity,
                                            length)) {
            ++g_Menu.metadataPrefixedHits;
            return true;
        }
    }
    ++g_Menu.metadataMisses;
    return false;
}

//: 条目来源的引擎入口校验（只做一次）。返回是否具备"取真实模组名"的全部前提。
//:
//: ★ 两个函数指针（`getMounted` / `freePath`）都经 `VerifiedEntry` 拿 —— 批次 108 起
//:   "核对 + 转成可调用签名"是**引擎调用层**的一个名字（`engine_call::ResolveFunction`），
//:   调用点不再自己 `reinterpret_cast`。原来的范围/逐字节判据一条没改，只是搬进了层。
void PrepareSourceContext(const TargetModule& module) {
    g_Menu.fileBindingsOk = GameFileReader::VerifyBindings(module, &g_Menu.fileBindings);
    // ① 挂载解析入口：优先用中继记下的原函数（理由见 `Context::getMounted`）。
    //    中继没装时才退回"守卫过的引擎入口" —— 那种情况下入口是原版、守卫才有意义。
    auto getMounted =
        isaac::runtime::Original<Context::GetMountedFn>(isaac::runtime::HookId::ContentGetMountedFilePath);
    if (getMounted != nullptr) {
        g_Menu.getMounted = getMounted;
    } else if (const auto direct = VerifiedEntry<Context::GetMountedFn>(
                   module, kContentManagerGetMountedFilePathOffset,
                   kContentManagerGetMountedFilePathExpectedBytes);
               direct != nullptr) {
        // 核对不过就**保持原值**（原实现也是"不赋值"，不是"赋空"）—— 这里逐条同义。
        g_Menu.getMounted = direct;
    }
    // ② `g_ContentManager` 对象指针：`base + 0xAAC748` **读一次**就是它
    //    （两个引擎调用点互证；`GameFileReader::VerifyImagePcxBindings` 也是这么读的）。
    //    ★ 批次 105：原来是 `volatile` 裸解引用 —— 换成访问层的取值（层内是 `memcpy`，
    //      同样"真读一次内存"、不会被折成常量），并多一道"这 8 字节可读吗"。
    {
        std::uintptr_t slot = 0;
        if (engine_memory::ReadAt(module.base + kContentManagerGotSlotOffset, &slot,
                                  &engine_memory::EngineMemoryReadable) &&
            slot != 0 && (slot & 7u) == 0) {
            g_Menu.contentManager = engine_memory::AsObject(slot);
        }
    }
    // ③ 还内存用的"游戏的 `operator delete[]`"（`GetMountedFilePath` 的返回值是 `new[]` 出来的）。
    if (const auto freePath = VerifiedEntry<GameFileReader::GameOperatorDeleteArrayFn>(
            module, kGameOperatorDeleteArrayOffset, kGameOperatorDeleteArrayExpectedBytes);
        freePath != nullptr) {
        g_Menu.freePath = freePath;
    }
    // 任一条拿不到 ⇒ 解析回调自己会返回 false（`ResolveMountedPath` 的前置检查），
    // 结果是"所有名字退目录名"—— 那是**正常降级**，不是错误。
}

//: 试着把条目表准备好并把 `begin/end/cap` 写进 `g_Manager + 0x36800`。
//:
//: 返回 true = 表已经就绪（可以往下走 `ctor` + `Init`）；false = 还在等发现结果、或没有模组。
//: **必须在 `Init` 之前写**：`Init` 会把 begin 抄进 `对象+0x170`。
//: 布局本身由 `mod_page_entries.hpp` 负责（那里逐字节被宿主门禁钉住）—— 本函数只负责"接线"。
//:
//: ★ 与探针的唯一差别（规格第二节：**不搬假数据**）：探针在"真实数据取不到"时会退回三个写死的
//:   测试名当信号；生产里**一个模组都没发现就是空表** —— 绝不往玩家屏幕上写假名字。
//:   （那三个字面量**故意不写在这里**：门禁按整段子串判定"生产代码里不许出现固定测试名"，
//:    注释里出现也会红。只改措辞、不放宽断言 —— 真写进去照样红。）
bool TryPrepareModsVector() {
    if (g_Menu.vectorWritten != 0) {
        return true;
    }
    if (g_Menu.manager == 0) {
        g_ModMenuState.failure = kFailureManagerNull;
        return false;
    }
    if (g_Menu.prepareAttempts < kPrepareAttemptLimit) {
        ++g_Menu.prepareAttempts;
    }
    isaac::runtime::ModPageRuntimeStats stats{};
    // ★ 批次 126：容量传 `kModSourceCapacity`（总容量 −1）—— 空出来的那一格给下标 0 的控制台开关行。
    const std::uint32_t found = isaac::runtime::CollectRuntimeModPageSources(
        &g_Sources[0], kModSourceCapacity, &ProvideDirectories, nullptr, &ProvideEnabled, nullptr,
        &CollectMetadataText, &g_Menu, g_SourceNameArena, sizeof(g_SourceNameArena),
        g_MetadataPath, g_MetadataScratch, &stats);
    std::size_t nameBytes = 0;
    std::uint32_t built = 0;
    // 表的总行数 = 发现的模组数 + 1（我们自己那一行，见 `kConsoleRowEntryIndex`）。
    // `found == 0` 时**不写表**：那正是"发现结果还没到"的正常时序，交给下面那个 switch 判"等"。
    const std::uint32_t total = found + 1U;
    if (found != 0) {
        // 把发现结果整体后移一格，空出下标 0 给自己那一行。
        // （`g_Sources` 有 `kEntryCapacity` 格，而 `found ≤ kModSourceCapacity` ⇒ 不会越界。）
        for (std::uint32_t index = found; index > 0; --index) {
            g_Sources[index] = g_Sources[index - 1];
        }
        // 这一条**不是模组**：`enabled = true` 让引擎按"开着的行"那种颜色画它，
        // `outdated = false`（它后面不会出现 `[Old]`）。
        g_Sources[kConsoleRowEntryIndex] = {ConsoleRowName(), true, false};
        built = isaac::runtime::BuildModPageEntries(&g_Entries[0][0], &g_EntryPointers[0],
                                                    g_EntryVector, total, &g_Sources[0],
                                                    g_EntryNameArena, sizeof(g_EntryNameArena),
                                                    &nameBytes);
    }
    const bool ready = built == total && found != 0;
    // 该等还是该退，由那个纯判定说了算（`DecideModPageSource`，宿主门禁逐条钉着）。
    switch (isaac::runtime::DecideModPageSource(ready, stats.directories, g_Menu.prepareAttempts,
                                                kPrepareAttemptLimit)) {
        case isaac::runtime::ModPageSourceDecision::Wait:
            // 发现结果还没出来（启动的模组扫描在 worker 线程上，构建还给了它 5 秒延迟）
            // ⇒ 这一帧什么都别做。**绝不能**在这里写死那张表：它只会写一次。
            return false;
        case isaac::runtime::ModPageSourceDecision::Ready:
            break;
        case isaac::runtime::ModPageSourceDecision::Fallback:
            // 真没有模组（或条目没造全）⇒ 写一张**空表**：页面照样进得去、只是 0 行。
            // 为什么不学探针退固定测试名：那会往玩家屏幕上写假名字（规格明令不搬）。
            if (built != total) {
                g_ModMenuState.failure = kFailureEntryBuild;
            }
            g_EntryVector[0] = 0;
            g_EntryVector[1] = 0;
            g_EntryVector[2] = 0;
            break;
    }
    // ★ 写入前**读旧值**（留证：引擎那张表天生是空的 —— `ModManager::Reset` 无调用者、
    //   `ListMods` 只有它一个调用者）。这里不因为"旧值非空"就放弃写入：那会让页面显示引擎的
    //   （空名）条目而不是真实模组，与验收判据冲突；而这 24 字节是**死代码**的字段，
    //   覆盖它不会丢任何活数据（规格第七节的风险对策就是这条）。
    {
        std::uintptr_t oldBegin = 0;
        std::uintptr_t oldEnd = 0;
        const bool oldReadBegin =
            engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset, &oldBegin,
                                     &engine_memory::EngineMemoryReadable, 0);
        const bool oldReadEnd =
            engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset + 8, &oldEnd,
                                     &engine_memory::EngineMemoryReadable, 0);
        // 旧值是"一对像话的指针"说明引擎真的在用它 ⇒ 记进失败码，便于现场分诊
        // （探针的 `modListPointersOk` 同一口径；不阻断写入）。
        // 读不到就**不许**说它像指针（那会把"读不到"误报成"引擎在用"）。
        const bool pointerLike = oldReadBegin && oldReadEnd && oldBegin >= 0x1000 &&
                                 oldEnd >= oldBegin && (oldBegin & 7u) == 0 &&
                                 (oldEnd & 7u) == 0 && oldEnd > oldBegin;
        if (pointerLike) {
            g_ModMenuState.failure = kFailureEntryBuild;
        }
    }
    // ★ 批次 105：这一处**必须**先过"可写"判定 —— 它写的正是引擎自己的模组表（`g_Manager + 0x36800`），
    //   "一处无守卫的写把内存写坏"那类事故就长在这个形状上。写不进去 = 表还是引擎原来那份空表
    //   ⇒ 如实记失败码并报"没就绪"，**不许**声称已就绪（那会让页面显示引擎的空条目）。
    //   （原来的裸 `memcpy` 在"不可写"时是把进程直接写崩。）
    if (!engine_memory::WriteField(g_Menu.manager, kManagerModsVectorOffset, g_EntryVector,
                                   &engine_memory::EngineMemoryWritable, 0)) {
        g_ModMenuState.failure = kFailureEntryBuild;
        return false;
    }
    g_Menu.vectorWritten = 1;
    g_Menu.writtenDirectories = stats.directories;
    // 如实报**表里实际有几行**（含下标 0 的自己那一行）—— 读数工具按"页面上该有几行"解释这一格。
    g_ModMenuState.entryCount = (built == total) ? total : 0;
    return true;
}

//: 让条目表**下标 0** 那一条的名字跟着开关状态走（`Console: ON` ↔ `Console: OFF`）。
//:
//: 为什么是"每帧同步"而不是"造表时写一次、拨开关时再改一次"：这张表只在进页面时造一次
//: （`vectorWritten` 只置一次），而它会因为换语言等原因**重建** —— 重建之后条目 0 的字符串
//: 又指回名字缓冲里那份造表时的副本。每帧把指针写正，就不会出现"拨过开关之后名字又变回去"。
//: 代价是 16 字节的两次 `memcpy`，只在模组页开着的那几帧跑，可以忽略。
void SyncConsoleRowName() {
    if (g_Menu.vectorWritten == 0) {
        return;  // 表还没造过（含"一个模组都没发现 ⇒ 空表"那种）⇒ 别去碰 `g_Entries`
    }
    isaac::runtime::SetModPageEntryName(&g_Entries[kConsoleRowEntryIndex][0], ConsoleRowName());
}

// ─────────────────────────────────────────────────────────────────────────────
// 那一行的算术（纯逻辑在 `mod_menu_entry_row.hpp`，这里只接线）
// ─────────────────────────────────────────────────────────────────────────────

//: 取 ANM2 的某个图层对象；拿不到返回 nullptr（调用方必须判）。
void* LayerOf(std::uintptr_t anm2, std::uint32_t layer) {
    if (g_Menu.getLayer == nullptr || anm2 == 0) {
        return nullptr;
    }
    return g_Menu.getLayer(engine_memory::AsObject(anm2), static_cast<int>(layer));
}

//: 引擎自己那份菜单动画里有没有我们补回去的那一层（`Item6`）。
//:
//: 判据 = **图层数**（`ANM2+0xB0`）。为什么不用 `GetLayer(12)` 是不是空：`ANM2::GetLayer(int)`
//: 越界时**不返回空指针** —— 它只打一条日志，然后照样按 `[ANM2+0xA8] + index*0xB0` 算出界地址。
//: 拿那个地址当图层用就是读越界内存。
bool HasNativeLayer(std::uintptr_t anm2) {
    if (anm2 == 0) {
        return false;
    }
    std::uint32_t count = 0;
    const bool read =
        engine_memory::ReadField(anm2, kAnm2LayerCountOffset, &count,
                                 &engine_memory::EngineMemoryReadable, 0);
    // 读不到图层数 ⇒ 当作"没有我们那一层"（⇒ 走兜底绘制）。比"照读一个越界值再拿它判断"安全。
    const bool present = read && count >= kMenuGameLayerCountWithModRow;
    g_ModMenuState.rowOwner = present ? 1U : 2U;
    return present;
}

//: 给每一行的图层偏移加/减一个位移（X 与 Y 都加）。`sign` = +1 施加、-1 还原。
//: 为什么要还原：引擎自己每帧也在往这个字段里加（那是它的排版手段），我们不还原就会一路漂下去。
//: 每一行挪的量**各不相同**（见生成的 `rowShiftY` / `rowShiftX`）：插点以上三行上移、STATS 下移、
//: OPTIONS 几乎不动。横向也照搬 PC（只搬 Y 的话「模组」会比上面那行挑战还靠左）。
void ShiftRows(std::uintptr_t anm2, float sign) {
    if (g_Menu.layout == nullptr) {
        return;  // 语言还没定 ⇒ 一帧都不挪（比"照英文那套挪"安全）
    }
    for (std::uint32_t row = 0; row < isaac::runtime::kMenuGameEngineEntryCount; ++row) {
        void* object = LayerOf(anm2, isaac::runtime::kMenuGameFirstRowLayer + row);
        if (object == nullptr) {
            continue;
        }
        const auto base = engine_memory::AddressOf(object);
        const float delta_x =
            isaac::runtime::MenuGameRowShiftXFor(*g_Menu.layout, row) * sign;
        const float delta_y = isaac::runtime::MenuGameRowShiftFor(*g_Menu.layout, row) * sign;
        // X 在 `+0x48`、Y 在 `+0x4C`（见 `mod_menu_entry_row.hpp` 里那条真机换来的结论）。
        // 读-改-写都走访问层：读要过"可读"、写要过"可写"（原来是裸 memcpy，两个都不查）。
        auto shift = [base](std::uintptr_t field_offset, float delta) {
            if (delta == 0.0F) {
                return;
            }
            const std::uintptr_t field = base + field_offset;
            float value = 0.0F;
            if (!engine_memory::ReadAt(field, &value, &engine_memory::EngineMemoryReadable)) {
                return;  // 读不到 ⇒ 一个字节都不写（比"照加一个数再写回去"安全）
            }
            value += delta;
            (void)engine_memory::WriteAt(field, value, &engine_memory::EngineMemoryWritable);
        };
        shift(isaac::runtime::kAnm2LayerOffsetXField, delta_x);
        shift(isaac::runtime::kAnm2LayerOffsetYField, delta_y);
    }
}

//: 光标：帧号 = 生成器给的帧（**不是格子号**），位置 = 我们自己给的一个 Y 偏移。
//: 那几帧的 y 是按**原版**那几格画的（帧 y ≈ 格子框顶 + 33），格子动了就不能照用 ——
//: 探针"选项那行光标停不到"正是栽在这：照用第 6 帧，它的 y=236 已经在纸外面。
//: `sign` = +1 施加（顺带设帧）、-1 还原。
void PlaceCursor(std::uintptr_t anm2, float sign) {
    void* object = LayerOf(anm2, isaac::runtime::kMenuGameCursorLayer);
    if (object == nullptr || g_Menu.layout == nullptr) {
        return;
    }
    const float delta = isaac::runtime::CursorDeltaYForSlot(*g_Menu.layout, g_Slot) * sign;
    const std::uintptr_t field =
        engine_memory::AddressOf(object) + isaac::runtime::kAnm2LayerOffsetYField;
    float value = 0.0F;
    if (engine_memory::ReadAt(field, &value, &engine_memory::EngineMemoryReadable)) {
        value += delta;
        (void)engine_memory::WriteAt(field, value, &engine_memory::EngineMemoryWritable);
    }
    if (sign > 0.0F && g_Menu.setLayerFrame != nullptr) {
        g_Menu.setLayerFrame(engine_memory::AsObject(anm2),
                             static_cast<int>(isaac::runtime::kMenuGameCursorLayer),
                             static_cast<int>(
                                 isaac::runtime::CursorFrameForSlot(*g_Menu.layout, g_Slot)));
    }
}

//: 算出**这一页的 ANM2 原点**（= 引擎自己交给 `ANM2::Render` 的那个位置）。
//:
//: 为什么必须**实时**算：进这一屏时纸是"滑"进来的 —— 那个滑动就是 `MenuManager+0x3c`
//: 这个偏移在朝目标值收敛。纸与那些行图都是 ANM2 图层，它们的最终位置 = **ANM2 原点 +
//: 图层局部坐标**；而画字接口用的是绝对坐标 ⇒ 把局部坐标直接交给它，字就**不跟着纸动**。
//: 引擎自己就是这么算的（`Menu_Game::Render` 反汇编 `0x40E760`~`0x40E784`）：
//:     x8 = g_MenuManager; x8 = *x8; ldp w9, w8, [x8, #0x3c]   ; 偏移
//:     x1 = this + 8                                            ; 页面自己的位置
//:     Vector2::operator+                                      ; ⇒ 原点
bool PageOrigin(std::uintptr_t page, float* out) {
    if (out == nullptr || page == 0 || g_Menu.menuManager == 0) {
        return false;
    }
    float offset[2] = {0.0F, 0.0F};
    float position[2] = {0.0F, 0.0F};
    // ★ 这里必须写 `&offset` / `&position`：`ReadField` 的出参是引用形参（`T* const&`），
    //   传裸数组**编译不过** —— 那段历史与判据见 `engine_field_access.hpp` 里 `ReadField` 那一段。
    if (!engine_memory::ReadField(g_Menu.menuManager, kMenuManagerCanvasOffset, &offset,
                                  &engine_memory::EngineMemoryReadable, 0) ||
        !engine_memory::ReadField(page, kPagePositionOffset, &position,
                                  &engine_memory::EngineMemoryReadable, 0)) {
        // 两段读不到 ⇒ **不假装原点算出来了**（画出去会落在屏幕角上）。
        return false;
    }
    out[0] = offset[0] + position[0];
    out[1] = offset[1] + position[1];
    return true;
}

//: 引擎那份**中等字体对象**（`g_Manager` 里那个偏移指向的对象）。**只读**（078 撤掉了
//: "往它里面装扩展字体换中文"那条路，门禁按"这个偏移在文件里只许出现两次"钉住它：
//: 常量定义 + 这一个取用点）。两处画字（兜底那一行、模组页上我们自己那一行）都从这里取 ——
//: 想再画一处就调这个函数，**不要**在别处再拼一次地址（那会让上面那条判据失效）。
void* EngineFontObject() {
    if (g_Menu.manager == 0) {
        return nullptr;
    }
    return engine_memory::AsObject(g_Menu.manager + kManagerFontOffset);
}

//: 画我们那一行（**兜底**，只有"引擎那份动画里没有我们那一层"时才走）。
//:
//: ★ 与探针的唯一差别：探针这里有三条路（磁盘贴图 → 内存贴图 → 画字），生产版**只留画字**。
//:   为什么：075 之后那一行由引擎自己画，那两条贴图路线已是死路（真机崩过：`Data Abort @ 0x0`，
//:   栈为 `ANM2::Render → AnimationLayer::RenderFrame → GetSourceQuad`，原因是拿了一张**空**的
//:   精灵表去画）。搬过去只会扩大风险面。
//: ★ 但"**空的东西绝不拿去画**"这条判据要保住：拿不到字体/布局/原点时返回 false 并**什么都不画**。
//:   返回值就是那条判据的载体 —— 调用方据此决定要不要记"我们画出了东西"。
bool DrawRowLabel(std::uintptr_t page) {
    if (g_Menu.drawText == nullptr || g_Menu.manager == 0 || g_Menu.layout == nullptr) {
        return false;
    }
    void* font = EngineFontObject();
    float origin[2] = {0.0F, 0.0F};
    if (!PageOrigin(page, origin)) {
        return false;  // 原点拿不到 ⇒ 画出去会落在屏幕角上，宁可不画
    }
    const float x = origin[0] + kModRowTextX;
    // 锚点 = 生成器算出来的那一格顶（引擎行 = 框顶；我们那一格 = 贴图顶），字从贴图内的
    // `inkTop` 起 —— 与周围五行落在同一水平线上。
    float slotTop = kModEntryTextYFallback;
    if (g_Menu.layout != nullptr) {
        slotTop = isaac::runtime::MenuGameSlotTop(*g_Menu.layout, isaac::runtime::kModEntrySlot) +
                  static_cast<float>(g_Menu.layout->sprite.inkTop);
    }
    const float y = origin[1] + slotTop;
    // 缩放 = **量出来的字高** ÷ 当前字体的行高 —— 换字体自动适应，不用重调。
    // ⚠️ 用的是 `glyphHeight`（真字高）而不是美术里那行字的**包围盒**高：那五行是斜着写的，
    //   包围盒高 = 字高×cos + 字宽×sin ⇒ 照包围盒缩放，画出来的字比周围大一圈。
    float artHeight = kModRowArtTextHeight;
    if (g_Menu.layout->glyphHeight > 1.0F) {
        artHeight = g_Menu.layout->glyphHeight;
    }
    float scale = kModRowTextScaleFallback;
    if (g_Menu.lineHeight != nullptr) {
        const float lineHeight = g_Menu.lineHeight(font);
        if (lineHeight > 1.0F && lineHeight < 200.0F) {
            scale = artHeight / lineHeight;
        }
    }
    g_Menu.drawText(font, kModRowLabel, x, y, scale, scale, kModRowTextColor, 0, false);
    return true;
}

// ── 批次 124 那套"自己另找位置画一行"在这里被删掉（批次 126，**别再照它做**）──────────────
//
// 124 的做法：这一行**不进条目表**，由我们用 `g_Menu.drawText` 在固定槽位上画，光标也自己画
// （选中时前面多一个 `> `）—— 因为那时"选到它"在引擎那边表现为"没有哪一行高亮"。
// 真机上为这一个位置试了四轮（-200 画到页面外 / +200 与 +125 被模组名盖住 /
// -25 压在「模组」标题下方那条横线上 / -150 + 小字号落在左侧空白带才算能看），
// 每挪一次都要用户重启主机验一轮。
// ⇒ 用户 2026-09-25 定案改成"作为模组的一个写在第一个模组位置上"（见本文件上方那组常量）：
//   它现在是**条目表里的下标 0**，引擎自己会把它画成 `1.Console: ON`，光标、高亮、滚动
//   全部是引擎原生行为 ⇒ 这个函数（连同四个位置/字号常量与负一哨兵）没有必要存在。

//: 定语言：调 `Manager::GetLanguageCode()`（两字符码），再按它挑一套生成的布局。
//:
//: ★ **每帧都问一次**（2026-09-23 批次 078 改）：原来这里"一次就定死"，理由是
//: "语言在游戏里改不了、改了要重启"。用户实测推翻了这个前提 ——
//: **在选项页里换语言是当场生效的**：其它界面的文字与美术都跟着换，只有我们这一页
//: 还挂着旧语言那张纸（那张纸是分语言的，见 `ReloadPageForLanguage`）。
//: `Manager::GetLanguageCode()` 只是一次读，代价可以忽略；语言码没变就一个字节都不写。
void ResolveLanguage() {
    if (g_Menu.manager == 0 || g_Menu.getLanguageCode == nullptr) {
        // 拿不到就**不定**（每帧都会再问一次）：宁可让布局晚一帧就位，也不要定错一套美术。
        if (g_Menu.languageSeen == 0) {
            g_Menu.languageState = 3;
        }
        return;
    }
    const char* code =
        g_Menu.getLanguageCode(engine_memory::AsObject(g_Menu.manager));
    if (code == nullptr || code[0] == '\0') {
        if (g_Menu.languageSeen == 0) {
            g_Menu.languageState = 3;
        }
        return;
    }
    // 绝大多数帧走这一条：语言码没变（一次比较，"变了才动手"）。
    if (g_Menu.languageSeen != 0 && code[0] == g_Menu.language[0] &&
        code[1] == g_Menu.language[1]) {
        return;
    }
    const bool changed = g_Menu.languageSeen != 0;
    g_Menu.language[0] = code[0];
    g_Menu.language[1] = code[1];
    std::uint32_t packed = 0;
    std::memcpy(&packed, g_Menu.language, sizeof(packed));  // 'z''h' ⇒ 0x0000687A
    g_ModMenuState.languageCode = packed;
    g_Menu.layout = isaac::runtime::ModRowLayoutForLanguage(g_Menu.language);
    g_Menu.languageSeen = 1;
    // 挑到 `en` 而语言码不是 `en` ⇒ 这个语言没有自己的美术（引擎那边也一样走基础资源）。
    const bool isEnglish = g_Menu.language[0] == 'e' && g_Menu.language[1] == 'n';
    const bool pickedEnglish = g_Menu.layout->language[0] == 'e' &&
                               g_Menu.layout->language[1] == 'n';
    g_Menu.languageState = (pickedEnglish && !isEnglish) ? 4U : 1U;
    if (changed) {
        // 语言变了：那一列的挪位量、以及模组页那张纸**都**要换成新语言的。
        // 布局上面已经换了；页面动画的换法见 `ReloadPageForLanguage`（它不能在这里做 ——
        // 这里只是"发现变了"，重载要挑页面不显示的时刻）。
        ++g_ModMenuState.languageSwitches;
        g_Menu.pageReloadPending = 1;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 模组页（引擎状态 16）
// ─────────────────────────────────────────────────────────────────────────────

//: 语言变了 ⇒ 把模组页的动画按新语言重载一次（那张纸、以及右上那行提示的**贴图**都烤在图里）。
//:
//: ★ 只重跑 `Init`、**绝不重跑 `ctor`**：`ctor` 会在活对象上重新构造内嵌的 ANM2
//:   （`add x0,x19,#0x10; bl ANM2::ANM2()`）⇒ 旧动画的缓存引用**没人还**，白漏一份。
//:   引擎自己的 `PostLanguageSwitch` 也不碰构造函数 —— 这一点我们和它一致。
//:
//: ★★ **排版怎么换（083 起已在做，真机验收通过）**：这一招（重载页面）只能换**贴图**
//:   （`load_graphics` 会按当前挂载层重新解析精灵表），**换不动动画排版** —— `g_AnmCache` 按
//:   **路径哈希**缓存（`FNHash`，`0xF4E8`），路径串一样就分不出语言，所以同一路径的动画数据
//:   永远是**开机那次解析**的那份。⇒ 要照引擎自己的办法：**先放开引用
//:   （`Menu_Mods::PreLanguageSwitch`）→ `AnmCache::FreeUnreferenced*` 回收掉不再被引用的
//:   → 再按当前语言重新 `Load`（`Menu_Mods::PostLanguageSwitch`）** —— 这三步就在本文件里做着。
//:   ★ 079 当年做过这三步、又被 080 撤回（理由是"把 EID 的信息显示搞坏了"）—— **那个归因是误判**：
//:     真凶是 082 才修掉的"换语言后 Mod 挂载点没恢复"，EID 在那种情况下本来就会坏。
//:     **083 把三步拿回来重试，083-补 真机三条全过**（EID 不再坏、排版当场就换）。
//:   ⇒ **不要再按旧注释"退回不做"**（门禁是正向判据：三步必须在、顺序必须对）。
//:   完整过程见 `docs/改动日志-20260923.md` 的 083 / `083-补`，以及文件上半部分那段注释。
//:   ⇒ 影响面：**同一次开机内换过语言**时，这张纸上的贴图会跟着换、那个键盘图标的位置还是
//:   开机语言那份（**重启一次即正确**）。
//:
//: 时机：**每帧更新里**（引擎 `Manager::Update` 之前、不在任何渲染批次中间），
//: 而且只在模组页**当前没显示**时动手 —— 页面正画着的时候换它的动画没有意义。
//: 语言只能在选项页里改，所以正常情况下这一刻页面本来就是关着的；万一不是（将来有别的入口），
//: 就等它关了再换：`pageReloadPending` 一直挂着，不会丢。
void ReloadPageForLanguage(const TargetModule& module) {
    if (g_Menu.pageReloadPending == 0) {
        return;
    }
    if (isaac::runtime::ModPageIsActive(g_Menu.menuState)) {
        return;  // 页面正显示 ⇒ 等它关了再换（不丢：标志还挂着）
    }
    g_Menu.pageReloadPending = 0;
    if (g_Menu.pageInitState != kInitOk) {
        return;  // 页面还没建过（或建失败）⇒ 下次进页面本来就会按新语言 `Init`，不必重复
    }
    if (g_Menu.modsPreLanguageSwitch == nullptr || g_Menu.modsPostLanguageSwitch == nullptr ||
        g_Menu.freeUnreferencedEntries == nullptr || g_Menu.freeUnreferencedImages == nullptr) {
        g_ModMenuState.failure = kFailureLanguageSwitchGuard;
        return;  // 有入口没通过逐字节核对 ⇒ **一次都不调用**（绝不盲目跳地址）
    }
    std::uintptr_t anmCache = 0;
    if (!ReadSlot(module, kAnmCacheSlotOffset, &anmCache) || anmCache == 0) {
        g_ModMenuState.failure = kFailureLanguageSwitchGuard;
        return;
    }
    // ① 放开（`ANM2::Reset` 在里面）—— 这一步之后页面暂时是"空"的，所以上面先要求它没在显示。
    g_Menu.modsPreLanguageSwitch(g_ModsObject);
    // ② 回收没人引用的贴图与动画数据（顺序与引擎一致：先图后条目）。
    g_Menu.freeUnreferencedImages(engine_memory::AsObject(anmCache));
    g_Menu.freeUnreferencedEntries(engine_memory::AsObject(anmCache));
    // ③ 按当前语言重新加载（引擎自己的 `PostLanguageSwitch`：`Load` + `Play("Main")` + …）。
    g_Menu.modsPostLanguageSwitch(g_ModsObject);
    ++g_ModMenuState.pageReloads;
    // 位置那套状态机跟着重来一遍：`Reset`/`Load` 会清掉页面自己的位置与动画状态，
    // 不重置的话这一帧会按"上一次算出来的位置"画（那一套是给旧动画算的）。
}

//: 走引擎自己的状态机切状态。**必须走中继记下的原函数**：装了 `SetState` 中继之后入口
//: 16 字节已被改写，逐字节守卫必然对不上（探针批次 060 的 bug 就是这么来的：现象只是"按了没反应"）。
//: 没装中继（`Original` 为空）才走"守卫 + 直接调"的老路。
void ApplyState(const TargetModule& module, std::uint32_t state) {
    using SetStateFn = void (*)(void*, std::int32_t);
    const auto original =
        isaac::runtime::Original<SetStateFn>(isaac::runtime::HookId::MenuManagerSetState);
    if (original != nullptr) {
        original(engine_memory::AsObject(g_Menu.menuManager), static_cast<std::int32_t>(state));
        g_ModMenuState.failure = kFailureNone;
        return;
    }
    // 批次 108：核对与"转成可调用签名"一起由引擎调用层完成 —— 核对不过就是 `nullptr`。
    const auto setState = VerifiedEntry<SetStateFn>(module, kMenuManagerSetStateOffset,
                                                    kMenuManagerSetStateExpectedBytes);
    if (setState == nullptr) {
        g_ModMenuState.failure = kFailureSetStateGuard;
        return;
    }
    setState(engine_memory::AsObject(g_Menu.menuManager), static_cast<std::int32_t>(state));
    g_ModMenuState.failure = kFailureNone;
}

//: 一次性 `ctor` + `Init`（`Menu_Mods` 的静态壳）。
//: 位置先给 `(0,0)`：真正的摆放由**每帧**按 `MenuManager+0x3c` 反算后写进对象 `+0x8` 完成。
//: 页面位置 —— **在 `Init` 时算一次就定死**（批次 169）。
//:
//: 引擎自己的模型（反汇编，可复核）：`Menu_Mods::Init(self, const Vector2& pos)` @`0x4100C4`
//: 把**入参**写进 `this+0x8`（`add x0,x19,#0x8` → `Vector2::operator=`），而 `Menu_Mods::Render`
//: @`0x4107C4` 只**读**它（`(this+0x8) + 画布`，再 `+ (100,0)`）——**引擎从不改它**；
//: 滚动则是 `Render` 收尾调 `SetModsOffset(选中项)` 改"状态 16 那一格的 Y"、由画布插值承担。
//: ⇒ 我们照做：位置在进页面时算一次、交给 `Init`，之后**一个字节都不再写**。
//: 算的依据仍是引擎自己的约定：画布停稳时落在 `那一格 + 居中量`。
void ComputeModsPagePosition(std::uintptr_t menuManager, float* out) {
    if (out == nullptr) {
        return;
    }
    out[0] = 0.0F;
    out[1] = 0.0F;
    if (menuManager == 0) {
        return;
    }
    float slot[2] = {0.0F, 0.0F};
    if (!engine_memory::ReadField(menuManager,
                                  isaac::runtime::kMenuManagerStateSlotBase +
                                      isaac::runtime::kModsPageState * 8,
                                  &slot, &engine_memory::EngineMemoryReadable, 0)) {
        return;
    }
    const float centerX = (g_Menu.screenWidth - kPageBoxWidth) * 0.5F;
    const float centerY = (g_Menu.screenHeight - 270.0F) * 0.5F - kModsPageCenterYAdjust;
    out[0] = kModsPageTargetOriginX - kModsRenderExtraX - (slot[0] + centerX);
    out[1] = -kModsSheetOffsetY - (slot[1] + centerY);
}

void InitManualPage() {
    if (g_Menu.menuManager == 0) {
        g_Menu.pageInitState = kInitMenuManagerNull;
        g_ModMenuState.failure = kFailureMenuManagerNull;
        return;
    }
    if (g_Menu.modsCtor == nullptr || g_Menu.modsInit == nullptr || g_Menu.modsRender == nullptr) {
        g_Menu.pageInitState = kInitGuardMismatch;
        g_ModMenuState.failure = kFailureMenuModsGuard;
        return;
    }
    // ★ 批次 169：**先把"状态 16 那一格的滚动值"定成确定值**（引擎 `Init` 的旧值不可信：
    //   批次 064 实测"重启后第一次进来读到 -290，而实际是 -216，差 74 格"），
    //   再按"画布停稳时会落在哪"算出**这一个常数**，交给 `Init` —— 之后不再写位置。
    if (g_Menu.setModsOffset != nullptr) {
        g_Menu.setModsOffset(engine_memory::AsObject(g_Menu.menuManager), 0);
    }
    ComputeModsPagePosition(g_Menu.menuManager, g_ModsPosition);
    g_Menu.modsCtor(g_ModsObject);
    g_Menu.modsInit(g_ModsObject, g_ModsPosition);
    g_Menu.pageInitState = kInitOk;
    g_ModMenuState.failure = kFailureNone;
}

// ---- 批次 148（2026-09-26）：把模组的 content 喂给引擎 ----------------------------------
//
// ★ 2026-09-26 深夜**换了做法**：不再调引擎自己的 `ListMods`/`LoadConfigs`，改成**直接调**
//   那两个 content 加载器。原因与依据见 `runtime_constants.hpp` 的批次 148b 常量段：
//   真机崩溃报告证明 `ListMods → ContentManager::get_directory_entries` 在本版本里**必然 abort**
//   （它把永远为空的 `g_ModdingDataPath` 交给 `nn::fs::OpenDirectory`），与"什么时候调"无关
//   （批次 143 那次也是它，当时归因成"第一帧太早"是误判）。
//   换来两个好处：① 真正可行；② 我们**完全不碰** `Manager+0x36800` 那张模组表 ⇒
//   模组页保持 147 的样子（`Console: ON` + 我们的模组行），上一版"页面变空"的回归不会再有。

//: 数 `Music + 0x3D8` 那张曲目表有几条；`0xFFFFFFFF` = 读不到（**不是**"表是空的"）。
std::uint32_t CountMusicEntries(std::uintptr_t manager) noexcept {
    if (manager == 0 || manager > UINTPTR_MAX - kManagerMusicOffset) {
        return 0xFFFFFFFFu;
    }
    const std::uintptr_t music = manager + kManagerMusicOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!engine_memory::ReadAt(music + kMusicEntryVectorBeginOffset, &begin,
                               &engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadAt(music + kMusicEntryVectorEndOffset, &end,
                               &engine_memory::EngineMemoryReadable) ||
        begin == 0 || end < begin || (end - begin) % kMusicEntrySize != 0) {
        return 0xFFFFFFFFu;
    }
    const std::size_t count = (end - begin) / kMusicEntrySize;
    return count <= kMusicEntryMaximumCount
               ? static_cast<std::uint32_t>(count)
               : 0xFFFFFFFFu;
}

//: 数 `ItemConfig` 的 null 服装容器有几条（`IC + 0x30/+0x38`）；`0xFFFFFFFF` = 读不到。
//: 这就是"模组那 23 条 `costumes2.xml` 进引擎了没有"的直接读数（真机基线 132）。
std::uint32_t CountNullCostumeEntries(std::uintptr_t manager) noexcept {
    if (manager == 0 || manager > UINTPTR_MAX - kManagerItemConfigOffset) {
        return 0xFFFFFFFFu;
    }
    const std::uintptr_t config = manager + kManagerItemConfigOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!engine_memory::ReadAt(config + kItemConfigNullItemBeginOffset, &begin,
                               &engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadAt(config + kItemConfigNullItemEndOffset, &end,
                               &engine_memory::EngineMemoryReadable) ||
        begin == 0 || end < begin || (end - begin) % sizeof(std::uintptr_t) != 0) {
        return 0xFFFFFFFFu;
    }
    const std::size_t count = (end - begin) / sizeof(std::uintptr_t);
    return count <= 65536 ? static_cast<std::uint32_t>(count) : 0xFFFFFFFFu;
}

//: 解析一个引擎入口（地址 = 模块基址 + 偏移，**已在别处算好**）⇒ 带签名的可调用指针；
//: 16 字节序言逐字节核对不过 ⇒ `nullptr`（**绝不跳一个没核对过的地址**）。
//: 走引擎调用层的"第二种形状"（`VerifyEntryBytes` + `AsFunction`），本函数不写 `reinterpret_cast`。
//:
//: ★★ 批次 378：**加了第二道守卫**（可选）。为什么必须加：本批要调的那 14 个内容加载器
//: （`EntityConfig::Load` / `ItemConfig::Load` / `LoadCostumes` …）**入口 16 字节完全相同**
//: （`kModContentLoaderExpectedBytes`）⇒ 只比序言的话，"偏移写串了"会被静默放过 ——
//: 而换个加载器就是**喂错容器**：不报错、不崩，只是"那个文件的内容永远不进引擎"。
//: 判别式 = "该函数入口 + N 处在某条指令上的 4 字节"，语义与 `kKageInputButtonDiscriminatorOffset`
//: 那一套**逐字相同**（`hook_manager.cpp` 的 `VerifyInputButtonEntry` 就是这么做的）。
//: `discriminator == nullptr` ⇒ 只比序言（表里 `PostLoadMods` 那条的 16 字节本身已唯一）。
std::uintptr_t ResolveVerifiedEntryAddress(const TargetModule& module, std::uintptr_t offset,
                                           const std::uint8_t* expected, std::size_t expectedSize,
                                           std::uintptr_t discriminatorOffset,
                                           const std::uint8_t* discriminator) noexcept {
    if (module.base == 0 || offset > UINTPTR_MAX - module.base) {
        return 0;
    }
    const std::uintptr_t address = module.base + offset;
    if (!engine_call::VerifyEntryBytes(address, expected, expectedSize,
                                       &engine_memory::EngineMemoryReadable)) {
        return 0;
    }
    if (discriminator != nullptr) {
        // 判别式落在入口之后 ⇒ 也要防回绕（与上面那条同一个理由：先算清楚、再碰内存）。
        if (discriminatorOffset > UINTPTR_MAX - address) {
            return 0;
        }
        if (!engine_call::VerifyEntryBytes(address + discriminatorOffset, discriminator,
                                           kModContentFeedDiscriminatorBytes,
                                           &engine_memory::EngineMemoryReadable)) {
            return 0;
        }
    }
    return address;
}

template <typename Fn>
Fn ResolveEngineEntry(const TargetModule& module, std::uintptr_t offset, const std::uint8_t* expected,
                      std::size_t expectedSize, std::uintptr_t discriminatorOffset = 0,
                      const std::uint8_t* discriminator = nullptr) noexcept {
    const std::uintptr_t address = ResolveVerifiedEntryAddress(
        module, offset, expected, expectedSize, discriminatorOffset, discriminator);
    return address == 0 ? nullptr : engine_call::AsFunction<Fn>(address);
}

//: 把 `GetMountedFilePath` 返回的 `rom:/…` 变成"相对应用根"的形式（去掉那 5 个字符）。
//:
//: 为什么需要（批次 149b）：引擎自己那条路（`ModManager::LoadConfigs`）喂给加载器的路径是
//: `ModEntry::GetContentPath` 拼出来的**相对应用根**形式；而 `GetMountedFilePath` 返回的是带
//: `rom:/` 的完整路径。148d 真机实测"两个加载器各被调 1 次、两个容器一条没涨"⇒ 口径可疑。
//: 不认识的串原样返回（绝不猜）。
const char* RelativeToApplicationRoot(const char* mounted) {
    constexpr char kPrefix[] = "rom:/";
    if (mounted != nullptr && mounted[0] == 'r' && mounted[1] == 'o' && mounted[2] == 'm' &&
        mounted[3] == ':' && mounted[4] == '/') {
        return mounted + (sizeof(kPrefix) - 1);
    }
    return mounted;
}

//: 把一条路径拷进定长缓冲区留证（超长只保留能装下的部分，**绝不越界**；总是 NUL 结尾）。
void CopyPathForEvidence(char* out, std::size_t capacity, const char* path) {
    if (out == nullptr || capacity == 0) {
        return;
    }
    std::size_t written = 0;
    if (path != nullptr) {
        while (written + 1 < capacity && path[written] != '\0') {
            out[written] = path[written];
            ++written;
        }
    }
    out[written] = '\0';
}

//: 把曲目表**最后一条**的编号（`+0x00`）与名字那 32 字节原始串（`+0x08` 起）搬进留证全局。
//: **只用于自证条目布局**（条目步长 `0x70`、字段偏移都在 `runtime_constants.hpp`）。
//:
//: ★ 逐 8 字节走**内存访问层**（`engine_memory::ReadAt` + 可读判定）—— 第一版是"返回引擎
//: 内存里的裸指针、让调用方逐字节读"，那**违反**本仓"不许新增裸碰引擎"门禁
//: （`test_no_new_raw_engine_access` 当场判红，1 ⇒ 2）。读 4 个字正好落在条目内
//: （`+0x08..+0x27`），不会越出这一条。
void ReadMusicEntryEvidence(std::uintptr_t manager) noexcept {
    if (manager == 0 || manager > UINTPTR_MAX - kManagerMusicOffset) {
        return;
    }
    const std::uintptr_t music = manager + kManagerMusicOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!engine_memory::ReadAt(music + kMusicEntryVectorBeginOffset, &begin,
                               &engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadAt(music + kMusicEntryVectorEndOffset, &end,
                               &engine_memory::EngineMemoryReadable) ||
        begin == 0 || end < begin || (end - begin) % kMusicEntrySize != 0) {
        return;
    }
    const std::size_t count = (end - begin) / kMusicEntrySize;
    if (count == 0 || count > kMusicEntryMaximumCount) {
        return;
    }
    const std::uintptr_t entry = begin + (count - 1) * kMusicEntrySize;
    std::uint32_t id = 0;
    if (engine_memory::ReadAt(entry + kMusicEntryIdOffset, &id,
                              &engine_memory::EngineMemoryReadable)) {
        g_ModEngineMusicLastEntryId = id;
    }
    for (std::size_t index = 0; index < 4; ++index) {
        std::uint64_t word = 0;
        if (!engine_memory::ReadAt(entry + kMusicEntryNameStringOffset +
                                       index * sizeof(std::uint64_t),
                                   &word, &engine_memory::EngineMemoryReadable)) {
            break;
        }
        g_ModEngineMusicLastEntryRaw[index] = word;
    }
}

// ---- 批次 152（2026-09-27 上午）：`LoadCostumes` 的第二个参数**不能传 `nullptr`** ----------
//
// 由来：149b 真机读数里 `LoadCostumes` 被调了 2 次、`null` 服装容器却 **132 → 132**（一条没涨）。
// 本批把 `ItemConfig::LoadCostumes @ 0x3B9448` 全文读完（962 行反汇编），结论与逐条地址证据
// 全部写在 `runtime_constants.hpp` 的批次 152 那一段。这里只留"做什么"：
//
//   * 第二个参数（`ModEntry*`）在这个函数里**只被用作"是不是空指针"**（三处 `ldr x2; cbz`），
//     外加由它算出 `ctx = ModEntry + 0x108`；
//   * `type="none"` 那条分支**一次都不碰 `ctx`**：非空 ⇒ 往 null 服装容器**追加**一条
//     （编号 = 容器旧条数、路径 = `anm2root + anm2path`）；空指针 ⇒ 落到"按 XML 的 `id`
//     去找**已有**那条"的路（本体 `resources/costumes2.xml` 走的就是这条，所以它容器不涨）；
//   * `ctx` 里其实是两个 libc++ `std::map<int,int>` 的空树头部（`+0x108` / `+0x120`），
//     `trinket` / `passive·active·familiar` 那几条分支会读它们 ⇒ 替身里的这两个 map
//     **必须是合法的空树**（零填充不行：引擎会解引用 `__begin_node_`）。
//
// ⇒ 我们传一块**只把那两个空 map 摆好**的替身即可（`type="none"` 只用"非空"这一个性质）。
//   为什么不去取引擎那个真 `ModEntry`：那张表（`g_Manager + 0x36800`）在本版里时有时无
//   （§024 读数见过 7 条、也见过 0 条），而"非空"这件事我们**自己就能保证**；替身与引擎自己
//   那条路在这几条分支上的行为一致（引擎那个 `ModEntry` 的两张 map 一开始也是空树）。
//: 一个 libc++ `std::map` 的头部三个 8 字节槽（`__tree`：`__begin_node_` / `__end_node_.__left_`
//: / `size_`）。语义逐格对应 `LoadCostumes` 里的用法：
//:   * 读根：`0x3BA010 ldr x0,[x9,#0x8]`（`__end_node_.__left_`）→ 传给
//:     `__tree_balance_after_insert`；
//:   * 插入后计数：`0x3BA01C ldr x8,[x19,#0x10]` + `add #1` + `str`（`size_`）；
//:   * 更新最左结点：`0x3B9F74 ldr x8,[x9]` 再 `0x3B9F78 ldr x8,[x8]`（解引用 `__begin_node_`
//:     —— **所以它不能是 0**）。
struct SubstituteModEntryTree {
    void* beginNode;       //: +0x00 = 空树时指向 `endNodeLeft` 自身
    void* endNodeLeft;     //: +0x08 = 空树时 0（它就是"根"那一格）
    std::uintptr_t size;   //: +0x10
};
static_assert(sizeof(SubstituteModEntryTree) == 0x18, "libc++ map 头部必须是 3 个 8 字节槽");

//: 替身 `ModEntry`：`+0x108` 起是两个空 map（皮肤那条分支用第一个、饰品那条用第二个）。
//: 前 `0x108` 字节引擎一个字都不读（只做"非空"判断），但仍然**留着**：
//: 引擎算 `ctx` 的方式就是 `x2 + 0x108`，替身必须够长、且 `ctx` 恰好落在结构体成员上。
struct SubstituteModEntry {
    unsigned char unused[kModEntryCostumeContextOffset];  //: 引擎不读（只判非空）
    SubstituteModEntryTree costumeMap;   //: +0x108：`passive` / `active` / `familiar` 走它
    SubstituteModEntryTree trinketMap;   //: +0x120：`trinket` 走它
};
static_assert(offsetof(SubstituteModEntry, costumeMap) == kModEntryCostumeContextOffset,
              "ctx 必须正好落在 +0x108（引擎入口就是 add x8,x2,#0x108）");
static_assert(offsetof(SubstituteModEntry, trinketMap) ==
                  kModEntryCostumeContextOffset + sizeof(SubstituteModEntryTree),
              "第二个 map 紧跟在第一个后面（引擎按 ctx+0x18 = ModEntry+0x120 取它）");
static_assert(sizeof(SubstituteModEntry) <= kModEntrySubstituteBytes,
              "替身不许超出我们声明的长度");

//: 替身本体。**静态存储（bss）+ 全 POD 成员 ⇒ 常量初始化**，不会有 `__cxa_guard_*`
//: （本模块 `-nostartfiles`：函数里带动态初始化的 `static` 会在守卫上自旋 ⇒ 黑屏有声不崩，
//: 见门禁 `test_no_static_guard_init.py`）。只初始化一次（`LoadEngineModContent` 本身只跑一次）。
SubstituteModEntry g_SubstituteModEntry;

//: 把一个 map 头部摆成"合法空树" —— 就是 libc++ `__tree` 默认构造出来的样子
//: （`__begin_node_ = &__end_node_`、`__end_node_.__left_ = 0`、`size_ = 0`）。
//: ★ `__begin_node_` 指向 `endNodeLeft` **而不是 0** 是必须的：`0x3B9F74-0x3B9F78` 连读两级指针，
//: 全 0 时第二次就是解引用空指针（真机表现会是 `Data Abort`）。
void MakeEmptyCostumeTree(SubstituteModEntryTree& tree) noexcept {
    tree.beginNode = &tree.endNodeLeft;
    tree.endNodeLeft = nullptr;
    tree.size = 0;
}

// ─────────────────────────────────────────────────────────────────────────────
// 批次 378（2026-10-05）：引擎那 **16 项**逐模组喂入（表在 `runtime_constants.hpp`）
// ─────────────────────────────────────────────────────────────────────────────
//
// 为什么要有这一块：引擎自己那条 `ModManager::LoadConfigs @ 0x41E388` 在 Switch 上**从不执行**
// （批次 147/148 定案），所以"每个模组的 `content/*.xml` 交给各加载器"只能我们做。
// 本批之前只喂 2 项（皮肤 / 音乐，批次 148~156 真机定案）；本批补到与引擎完全一致的 16 项
// （14 个文件 + `ModEntry::LoadCustomResources` + `EntityConfig::PostLoadMods`）。
// 调用次序、参数形状、每条的判别式逐条抄自 `LoadConfigs` 的反汇编，依据写在
// `runtime_constants.hpp` 的 `kModContentFeedSpecs` 那一段。

//: `g_ModEngineScanStage` 判"涨过没有"用的那个函数（定义在本文件下半部分）——
//: 本批的 `RunPostLoadModsOnceIfDue` 要用它，所以在这一块前面**前向声明**（匿名命名空间内同一实体）。
bool EngineModContentLoaded() noexcept;

//: `PostLoadMods` 的**一次性**闩锁（本仓不许用 bool 版原子量 ⇒ `std::uint32_t`）。
//: 为什么必须是"进程内只调一次"：见 `RunPostLoadModsOnceIfDue` 的注释。
std::atomic<std::uint32_t> g_PostLoadModsDone{0};

//: 16 项入口的解析结果（**模块基址一次定死 ⇒ 只解析一次、之后复用**）。
//: 与 `g_SubstituteModEntry` 同一个理由：文件作用域 + 常量初始化 ⇒ 不会有 `__cxa_guard_*`。
std::uintptr_t g_ModContentFeedAddresses[kModContentFeedSpecs.size()] = {};
//: `ModEntry::ctor` 的地址（0 = 没解析到 ⇒ 所有带 `ModEntry*` 的项都跳过）。
std::uintptr_t g_RealModEntryCtorAddress = 0;
//: `std::string::assign(const char*)` 那条 **PLT 桩**的地址（0 = 没解析到 ⇒ 内容目录不填）。
//: ★ 它核对的是"桩里编码的 GOT 槽"而不是函数序言（那个符号不在本模块里），见 `runtime_constants.hpp`。
std::uintptr_t g_ModEntryStringAssignAddress = 0;
//: ★ 批次 409：`ANM2::Load(std::string const&, bool)` 的地址（0 = 没解析到 ⇒ 收尾那一步跳过，
//: 并在 `modEngineLoaderFailures` 的 bit18 留痕）。它同样**不在**那 16 行表里，单独解析一次。
std::uintptr_t g_Anm2LoadAddress = 0;
//: 只解析一次的闩锁（单线程：这条链只在游戏线程的 `Manager::Update` 帧里跑）。
std::uint32_t g_ModContentFeedResolved{0};

//: 真 `ModEntry` 的静态竞技场（bss；零初始化 = 常量初始化 ⇒ 无静态守卫）。
//: 步长 `kRealModEntryStride`（16 的倍数）⇒ **每个下标都 16 字节对齐**（引擎自己是用 `new` 拿的）。
//: 为什么要 32 个：`kMaximumSelectedMods = 32`，取小了的后果是"第 N 个之后的模组内容喂不进去"。
alignas(16) unsigned char g_RealModEntryArena[kMaximumRealModEntries * kRealModEntryStride];
//: 哪些下标已经构造过（每一位一个下标；**按下标惰性构造一次、之后复用**）。
//: 为什么必须只构造一次：构造器会建 13 个 `ANM2`（`+0x140` 起，步长 `0x158`）——重复构造
//: 等于在同一块内存上重来一遍，没有意义、还可能漏掉前一次的资源。
std::uint32_t g_RealModEntryBuiltMask{0};

//: ★★ 批次 378：哪些下标已经喂过"**没有可观测信号**"的那一批
//: （`ModEntry::LoadCustomResources` + 12 个 content 文件）。
//:
//: 为什么需要这个闩锁（本批实施后由主线程复核发现的缺陷）：`LoadEngineModContent` 允许
//: **最多 8 次尝试**，而"涨过就不再试"那道闸看的**只是** `costumes2.xml`/`music.xml` 两个容器
//: （`EngineModContentLoaded()`）。也就是说：
//:   * 只要这两个容器没涨，**每一轮都会把 12 个 content 文件重新喂一遍**；
//:   * 而引擎那几个加载器里有的**是追加语义**（`LoadChallenges(…, true)`、`EntityConfig::Load`
//:     往实体表里加、`LoadCustomResources` 会再 `ANM2::Load` 一遍）⇒ 多喂几轮就是**重复条目**
//:     （挑战列表出现重复行、实体表重复项、ANM2 缓存引用数虚高）。
//:   * PC 的 `ModManager::LoadConfigs` 对这一批**只跑一次**（它在启动时按模组跑一遍）。
//: ⇒ 处置：这一批**每个模组只喂一次**（第一次尝试就喂），服装/音乐两行**不动** —— 它们有客观信号
//:   （容器涨没涨），"没涨就再试一次"是批次 153 定下的、真机摔出来过的机制，不能拿掉。
//:
//: 为什么"第一次就喂"是安全的：那 12 项与服装/音乐走的是**同一种路径口径**（相对应用根直接喂），
//: 批次 155 已经证明"最早那一刻直接喂就能进容器"；真正在最早那一刻失败的是
//: `ResolveMountedPath`（它依赖 `ContentManager` 就绪），而我们这一批**不依赖它**。
//: 下标超过 31（配置上限 32 之外）时不置位 ⇒ 那种边界情形退回"每轮都喂"。
std::uint32_t g_ModContentUnobservableFedMask{0};

//: 解析 16 项入口 + `ModEntry::ctor`（**只做一次**），并把结果写进状态面 `[68]/[69]`。
//:
//: ★ 失败**不 return**：本批的处置是"记位、跳过这一项、继续其余"—— 理由：少一项时其余 15 项
//: 照样能把内容喂进去，而"整批放弃"会让一个入口解析失败**连累**全部内容都进不去（那是更坏的
//: 结果，且现场看不出是哪一项）。读数上靠 `[69]` 的位掩码一眼区分"全成功"与"少哪一项"。
void EnsureModContentFeedResolved(const TargetModule& module) noexcept {
    if (g_ModContentFeedResolved != 0) {
        return;
    }
    std::uint32_t resolvedMask = 0;
    std::uint32_t failureMask = 0;
    for (std::size_t row = 0; row < kModContentFeedSpecs.size(); ++row) {
        const ModContentFeedSpec& spec = kModContentFeedSpecs[row];
        const std::uint8_t* const discriminator =
            spec.discriminatorOffset != 0 ? spec.discriminator.data() : nullptr;
        const std::uintptr_t address =
            ResolveVerifiedEntryAddress(module, spec.functionOffset, spec.expected,
                                        spec.expectedSize, spec.discriminatorOffset, discriminator);
        g_ModContentFeedAddresses[row] = address;
        if (address != 0) {
            resolvedMask |= (1U << row);
        } else {
            failureMask |= (1U << row);
        }
    }
    g_RealModEntryCtorAddress =
        ResolveVerifiedEntryAddress(module, kModEntryCtorFileOffset, kModEntryCtorExpectedBytes.data(),
                                    kModEntryCtorExpectedBytes.size(), 0, nullptr);
    if (g_RealModEntryCtorAddress == 0) {
        // bit16 = `ModEntry::ctor`（**不在 16 行表里**，单独一位）：那位一亮，
        // 所有需要 `ModEntry*` 的项都会被跳过（空指针会让 `type="none"` 的条目一条都不加）。
        failureMask |= kModFeedConstructorFailureBit;
    }
    g_ModEntryStringAssignAddress = ResolveVerifiedEntryAddress(
        module, kModEntryStringAssignFileOffset, kModEntryStringAssignExpectedBytes.data(),
        kModEntryStringAssignExpectedBytes.size(), 0, nullptr);
    if (g_ModEntryStringAssignAddress == 0) {
        // bit17 = `std::string::assign` 那条桩（同样不在 16 行表里）。那位一亮 ⇒
        // `ModEntry+0x48`/`+0x60` 填不上 ⇒ `LoadCustomResources` 找不到任何文件（见 `.hpp`）。
        failureMask |= kModFeedStringAssignFailureBit;
    }
    // ★ 批次 409：收尾那一步要用的 `ANM2::Load`（= `kSpriteLoadOffset`，不在 16 行表里，单独解析）。
    // 它拿不到**不影响**其余 16 项 —— 只表现为"`ModManager+0x368` 那个默认 ANM2 没被载"
    // （后果见 `runtime_constants.hpp` 的批次 409 那一段：暂停屏画模组道具时会崩）。
    // ★ 这里**不**核对序言：那个入口已被批次 363 的中继改写过头部（理由逐字写在
    // `runtime_constants.hpp` 的批次 409 那一段）⇒ 核对会必然失败、把这一步静默跳过。
    if (module.base != 0 && kSpriteLoadOffset <= UINTPTR_MAX - module.base) {
        g_Anm2LoadAddress = module.base + kSpriteLoadOffset;
    }
    if (g_Anm2LoadAddress == 0) {
        failureMask |= kModFeedAnm2LoadFailureBit;
    }
    g_ModMenuState.modEngineLoadersResolved = resolvedMask;
    g_ModMenuState.modEngineLoaderFailures = failureMask;
    g_ModContentFeedResolved = 1;
}

//: 取**第 index 个模组的真 `ModEntry`**（第一次要它时用引擎构造器造，之后复用）。
//: 返回 `nullptr` = 造不出来（构造器没解析到 / 下标超出竞技场）⇒ 调用方跳过需要它的项。
//: ★ 这里**不**碰引擎的模组表（`Manager+0x36800`）：这些条目只当参数用，不进引擎的列表。
//:
//: `contentPath` = `isaac_mods/mods/<目录>/content/`（**带结尾 `/`**）—— 造完之后要把它写进
//: 条目的两个成员（`+0x48` / `+0x60`）：`ModEntry::GetContentPath` 读的是 `+0x48`，而本版
//: 引擎自己的 `ListMods` 写的是 `+0x60`（证据见 `runtime_constants.hpp` 那两段）⇒ **两个都填**。
//: 写串用引擎自己的 `std::string::assign`（libc++ 的 SSO/长串布局与分配器都由它负责，
//: 之后引擎释放时用的是同一个 `_ZdlPv`）—— 我们自己写那 24 字节就是把 libc++ 的内部约定抄一份。
void* RealModEntryForIndex(std::uint32_t index, const char* contentPath) noexcept {
    if (g_RealModEntryCtorAddress == 0 || index >= kMaximumRealModEntries) {
        return nullptr;
    }
    unsigned char* const bytes = g_RealModEntryArena + static_cast<std::size_t>(index) * kRealModEntryStride;
    const std::uint32_t bit = (1U << index);
    if ((g_RealModEntryBuiltMask & bit) == 0) {
        using ModEntryCtorFn = void (*)(void*);
        // `x0` = 条目自身（引擎入口 `0x420D18` 就是 `this` 在 x0）；`AsFunction` 只收已核对过的地址。
        void* const entry = engine_memory::AsObject(engine_memory::AddressOf(bytes));
        engine_call::AsFunction<ModEntryCtorFn>(g_RealModEntryCtorAddress)(entry);
        if (contentPath != nullptr && g_ModEntryStringAssignAddress != 0) {
            using StringAssignFn = void (*)(void*, const char*);
            const StringAssignFn assign =
                engine_call::AsFunction<StringAssignFn>(g_ModEntryStringAssignAddress);
            const std::uintptr_t entryAddress = engine_memory::AddressOf(bytes);
            // 两张都要填（谁读对都行）：`+0x48` 是 `GetContentPath` 读的，`+0x60` 是引擎自己写的那个。
            assign(engine_memory::AsObject(entryAddress + kModEntryContentPathOffset), contentPath);
            assign(engine_memory::AsObject(entryAddress + kModEntryContentDirectoryOffset), contentPath);
        }
        g_RealModEntryBuiltMask |= bit;
        g_ModMenuState.modEngineRealEntryBuilds += 1;
    }
    return engine_memory::AsObject(engine_memory::AddressOf(bytes));
}

struct ModRoomSources {
    void* entries[kMaximumRealModEntries]{};
    void** begin{};
    void** end{};
    void** capacity{};
    bool ready{};
};
ModRoomSources g_ModRoomSources{};
bool PrepareModRoomSources() noexcept {
    if(g_ModRoomSources.ready)return true;
    const auto selected=isaac::runtime::ModMenuDiscoveredForReading();
    if(!isaac::runtime::ModMenuDiscoveryDone() ||
       (selected.activeMask & ~g_RealModEntryBuiltMask)!=0)return false;
    std::size_t count=0;
    for(std::size_t index=0;index<selected.count && index<kMaximumRealModEntries;++index) {
        if((selected.activeMask&(std::uint32_t{1}<<index))==0)continue;
        auto* bytes=g_RealModEntryArena+index*kRealModEntryStride;
        const auto address=engine_memory::AddressOf(bytes);
        // 这是运行时拥有的真实ModEntry，不改引擎菜单的另一份列表。
        if(!engine_memory::WriteField(address,kModEntryEnabledFlagOffset,std::uint8_t{1},
                                     engine_memory::EngineMemoryWritable)) {
            ++isaac::runtime::modmenu::g_ModRoomLoadState[6];return false;
        }
        g_ModRoomSources.entries[count++]=engine_memory::AsObject(address);
    }
    g_ModRoomSources.begin=g_ModRoomSources.entries;
    g_ModRoomSources.end=g_ModRoomSources.entries+count;
    g_ModRoomSources.capacity=g_ModRoomSources.end;
    g_ModRoomSources.ready=true;
    isaac::runtime::modmenu::g_ModRoomLoadState[1]=static_cast<std::uint32_t>(count);
    isaac::runtime::modmenu::g_ModRoomLoadState[7]=selected.activeMask;
    return true;
}

//: 把表里第 `row` 行那一个**文件**喂给它的接收者（路径已经拼到 `path` 的 `baseLength` 之后）。
//:
//: * 接收者按 `spec.receiver` 算（`Manager` 的几个子对象偏移见 `runtime_constants.hpp`）；
//: * 第三个参数按 `spec.argument` 的形状传（`ModEntry*` / `bool true` / 没有）；
//: * ★ `realEntry == nullptr` 时**只跳过需要 `ModEntry*` 的那几项**（空指针会让 `type="none"`
//:   的条目一条都不加、还会把"属于哪个模组"归错）—— 其余项（`bool` 那条）照喂；
//: * 路径装不下就**跳过这一条**（下面有算术证明：按现有长度上限它不可能发生，这一句是保险）。
void FeedModContentFile(std::size_t row, std::uintptr_t manager, void* realEntry, char* path,
                        std::size_t baseLength, std::size_t pathCapacity) noexcept {
    const ModContentFeedSpec& spec = kModContentFeedSpecs[row];
    if (spec.fileName == nullptr || manager == 0) {
        return;
    }
    const std::uintptr_t address = g_ModContentFeedAddresses[row];
    if (address == 0) {
        return;  // 这一项没解析到 ⇒ 跳过（位掩码里记着，见 `EnsureModContentFeedResolved`）
    }
    if (spec.argument == ModContentFeedArgument::ModEntry && realEntry == nullptr) {
        return;  // 没有真条目 ⇒ 不能喂（见函数头那条）
    }
    // 接收者（`x0`）。
    std::uintptr_t receiverAddress = 0;
    switch (spec.receiver) {
        case ModContentFeedReceiver::ItemConfig:
            receiverAddress = manager + kManagerItemConfigOffset;
            break;
        case ModContentFeedReceiver::EntityConfig:
            receiverAddress = manager + kManagerEntityConfigOffset;
            break;
        case ModContentFeedReceiver::ManagerItself:
            receiverAddress = manager;  // ★ 不加偏移（`0x41EA58 ldr x0,[x22]`）
            break;
        case ModContentFeedReceiver::SoundEffects:
            receiverAddress = manager + kManagerSoundEffectsOffset;
            break;
        case ModContentFeedReceiver::Music:
            receiverAddress = manager + kManagerMusicOffset;
            break;
        case ModContentFeedReceiver::NightmareScene:
            receiverAddress = manager + kManagerNightmareSceneOffset;
            break;
        case ModContentFeedReceiver::ModEntryItself:
            return;  // 只对"整批项"有意义（`LoadCustomResources`），文件项不该走这里
    }
    if (receiverAddress == 0) {
        return;
    }
    // 拼 `<模组根>/content/<文件名>`。
    // ★ 长度算术（为什么这一句"装不下"不可能命中）：模组根前缀在循环入口已经过
    //   `prefixLength > sizeof(path) - 32` 那道闸 ⇒ `baseLength <= 224`；本表最长的文件名是
    //   `items_metadata.xml`（含 NUL 19 字节）、`/content/` 是 9 字节 ⇒ `224 + 9 + 19 = 252 <= 256`。
    //   仍然留着这条判定：将来文件名或前缀变长时它会**跳过**而不是截断成半个路径
    //   （截断的后果是"悄悄喂了一个不存在的路径"，比不喂更难查）。
    const std::size_t prefixLength = sizeof(kModContentDirectoryPrefix) - 1;  // 不含结尾 NUL
    const std::size_t nameSize = std::strlen(spec.fileName) + 1;
    if (baseLength + prefixLength + nameSize > pathCapacity) {
        return;
    }
    std::memcpy(path + baseLength, kModContentDirectoryPrefix, prefixLength);
    std::memcpy(path + baseLength + prefixLength, spec.fileName, nameSize);
    void* const receiver = engine_memory::AsObject(receiverAddress);
    switch (spec.argument) {
        case ModContentFeedArgument::ModEntry: {
            using FeedWithModEntryFn = void (*)(void*, const char*, void*);
            engine_call::AsFunction<FeedWithModEntryFn>(address)(receiver, path, realEntry);
            break;
        }
        case ModContentFeedArgument::BoolTrue: {
            // ★ `w2 = 1`：引擎自己对这些加载器传的就是 1（`LoadConfigs` 里 `mov w2, #0x1`）。
            using FeedWithFlagFn = void (*)(void*, const char*, bool);
            engine_call::AsFunction<FeedWithFlagFn>(address)(receiver, path, true);
            break;
        }
        case ModContentFeedArgument::None: {
            using FeedPlainFn = void (*)(void*, const char*);
            engine_call::AsFunction<FeedPlainFn>(address)(receiver, path);
            break;
        }
    }
    g_ModMenuState.modEngineContentCalls += 1;
}

//: 每个模组的**第一个**动作：`ModEntry::LoadCustomResources()`（引擎在 `entities2.xml` **之前**
//: 调它：`0x41E414`，就在 `ldrb w8,[x0,#0x139]` + `cbz` 那道启用位闸门之后）。
//: ★ 这里**不先问"它有没有文件"**：引擎直接调、函数内部自己逐个 `Exists` 判，不存在不 abort
//: —— 照引擎做（`runtime_constants.hpp` 里已写明这一条）。
void FeedModCustomResources(void* realEntry) noexcept {
    const std::uintptr_t address = g_ModContentFeedAddresses[kModFeedRowCustomResources];
    if (address == 0 || realEntry == nullptr) {
        return;
    }
    using LoadCustomResourcesFn = void (*)(void*);
    engine_call::AsFunction<LoadCustomResourcesFn>(address)(realEntry);
    g_ModMenuState.modEngineCustomResourceCalls += 1;
}

//: `EntityConfig::PostLoadMods()` —— 引擎在**所有模组都喂完之后**调一次（循环外 `0x41ED24`）。
//:
//: ★★ 为什么用一次性闩锁、且带"最后一次尝试"兜底：
//:   * 它**不是**幂等收尾（引擎只调一次）⇒ 每轮都调等于拿一份没收尾的配置去收尾，
//:     与"同一条内容喂两遍"是同一类代价，所以 `compare_exchange` 保证**进程内只调一次**；
//:   * 判据一"这一轮真喂进去了"（`EngineModContentLoaded()` —— 与既有的"涨过就不再喂"同一个信号）
//:     是**成功那一刻**收尾；判据二"这是最后一次尝试"兜底，否则"早期那次时机不对"会让
//:     `PostLoadMods` 永远轮不到、而后面几轮喂进去的内容没有被收尾。
//: ★★ 批次 409（2026-10-08）：`ModManager::LoadConfigs` **尾部**的收尾那一步 ——
//: 把 `gfx/ui/mod_defaults.anm2` 载进 `ModManager + 0x368` 那个 `ANM2`。
//:
//: 为什么必须有它（真机崩过一次，报告 `dist/crash-20261008-1345/`）：那是"**模组道具在暂停屏上的
//: 默认图标**"。`PauseScreen::Render` 遇到道具 id ≥ `0x2DD`（733）就调
//: `ModManager::RenderCustomCollectionItem`，走"默认"分支时对 `ModManager+0x368` 调
//: `ANM2::GetLayer(0)`；`ANM2::GetLayer` 不做越界返回空 ⇒ 层数组为空时算出地址 `0x0`，
//: 再 `+0x80` 就是一次写 `0x80` ⇒ `Data Abort`。依据与逐条反汇编见
//: `runtime_constants.hpp` 的批次 409 那一段。
//:
//: 串怎么造：与 `RealModEntryForIndex` **同一个口径** —— 不自己写 libc++ 那 24 字节布局，
//: 用一块零初始化的 24 字节（= 合法的空串：libc++ 的短模式判据是"首字节最低位 == 0"）
//: 交给引擎自己的 `std::string::assign(const char*)`。为什么放在 `PostLoadMods` **之后**：
//: 引擎就是那个次序（`0x41ED34` → `0x41ED7C`）—— 它对"所有模组都喂完之后"的收尾有依赖。
void LoadModManagerDefaultAnm2Once(std::uintptr_t manager) noexcept {
    if (g_Anm2LoadAddress == 0 || g_ModEntryStringAssignAddress == 0 || manager == 0) {
        return;
    }
    //: 24 = `sizeof(std::string)`（libc++，与 `ModEntry+0x48`/`+0x60` 那两格的间距 `0x18` 同源）。
    constexpr std::size_t kStringBytes = 24;
    //: 静态缓冲（bss，零初始化 ⇒ 常量初始化、无静态守卫）：这条链在游戏线程上只走一次。
    alignas(8) static unsigned char pathString[kStringBytes] = {};
    unsigned char* const pathBytes = pathString;
    using StringAssignFn = void (*)(void*, const char*);
    engine_call::AsFunction<StringAssignFn>(g_ModEntryStringAssignAddress)(
        engine_memory::AsObject(engine_memory::AddressOf(pathBytes)), kModManagerDefaultAnm2Path);
    const std::uintptr_t anm2 = manager + kManagerToModManagerOffset + kModManagerDefaultAnm2Offset;
    using Anm2LoadFn = void (*)(void*, const void*, std::uint32_t);
    engine_call::AsFunction<Anm2LoadFn>(g_Anm2LoadAddress)(
        engine_memory::AsObject(anm2),
        engine_memory::AsObject(engine_memory::AddressOf(pathBytes)), 1);
    // ★ 两处都要写：`g_ModEngineModDefaultsAnm2Loads` 是读数工具按**裸名**直读的那个全局，
    //   `g_ModMenuState.modEngineDefaultAnm2Loads`（[74]）是状态面里那一格。
    //   ★★ 这里踩过一次：第一版只加了前者，于是读数工具打出来的 [74] **恒为 0**
    //   （而真实的计数器已经是 1）—— 那正是"诊断口撒谎"，比没有诊断更坏。
    g_ModEngineModDefaultsAnm2Loads += 1;
    g_ModMenuState.modEngineDefaultAnm2Loads += 1;
}

void RunPostLoadModsOnceIfDue(std::uintptr_t manager, bool lastAttempt) noexcept {
    if (!lastAttempt && !EngineModContentLoaded()) {
        return;
    }
    const std::uintptr_t address = g_ModContentFeedAddresses[kModFeedRowPostLoadMods];
    if (address == 0 || manager == 0) {
        return;
    }
    std::uint32_t expected = 0;
    if (!g_PostLoadModsDone.compare_exchange_strong(expected, 1U, std::memory_order_acq_rel)) {
        return;
    }
    using PostLoadModsFn = void (*)(void*);
    engine_call::AsFunction<PostLoadModsFn>(address)(
        engine_memory::AsObject(manager + kManagerEntityConfigOffset));
    g_ModMenuState.modEnginePostLoadModsCalls += 1;
    // ★ 批次 409：紧接着就是引擎那条尾（`0x41ED34` → `0x41ED7C`），顺序照抄引擎。
    LoadModManagerDefaultAnm2Once(manager);
}

// ─────────────────────────────────────────────────────────────────────────────
// 批次 401（2026-10-07）：把一个模组的 `content/players.xml` 并进"角色名 → id"追加层
// ─────────────────────────────────────────────────────────────────────────────
//
// ## 为什么在这里、按这个顺序
//
// 模组角色的 id 规则（批次 399 已取证定案，本批直接采信）：
//   **id = 41 + 该角色在本模组 `players.xml` 里的 `<player>` 出现顺序（0 基）；跨模组按
//   引擎喂入顺序继续累加。**
// 下面 `LoadEngineModContent` 的循环**就是**喂入顺序（`ModMenuDiscoveredCount/Directory/Enabled`
// 逐模组，与引擎喂 `content/*.xml` 同一条路）。⇒ 解析也放在**同一个循环、同一个下标顺序**上，
// **绝不自己按目录名/文件名重排** —— 顺序错了 id 就错，而且是**静默错**（按错角色判类型、不报错）。
//
// ## 读文件：走与 `metadata.xml` 同一条**已知安全**的路
//
// `ResolveThenRead` + `ResolveMountedPath`：**先解析挂载**（文件不在任何挂载点 ⇒ 返回空、
// **不炸**），再读解析出来的绝对路径。
// ★ 为什么不直接用引擎的 `File::OpenRead` 入口去开相对路径：它对"打开失败"是**直接 Abort**
//   （真机 01789974615）⇒ 一个**没有** players.xml 的模组会把整个运行时打崩。
//   `GetMountedFilePath` 正是引擎 `FileManager::Exists` 用来做存在性判断的那一步
//   （`runtime_constants.hpp` 贴图桥 v3 段），过了它才读，才是安全的。
//
// ## 诊断（不报错、不崩，但读得出来）
//
// 读失败记 `readFailures`、解析失败记 `malformedMods`、空名条目记 `skippedEntries`
// （都在 `ModPlayerNameStatistics()`）。★ 残余风险**写在明处**：若引擎在某一刻成功喂进了
// players.xml、而我们这一刻解析挂载失败，则那个模组的名字进不了表、而引擎确实占了 id ——
// 表现为**后面模组的 id 整体偏移**；`readFailures > 0` 就是这件事的信号（正常应恒 0）。
void FeedModPlayerTypeNames(const char* directory, char* path, std::size_t baseLength,
                            std::size_t pathCapacity) noexcept {
    if (directory == nullptr || directory[0] == '\0' || path == nullptr) {
        return;
    }
    constexpr std::size_t kPrefixLength = sizeof(kModContentDirectoryPrefix) - 1;   // "/content/"
    constexpr std::size_t kNameSize = sizeof(isaac::runtime::kModPlayersFileName);  // 含结尾 NUL
    if (baseLength + kPrefixLength + kNameSize > pathCapacity) {
        return;  // 装不下就跳过（绝不截断成半个路径）
    }
    std::memcpy(path + baseLength, kModContentDirectoryPrefix, kPrefixLength);
    std::memcpy(path + baseLength + kPrefixLength, isaac::runtime::kModPlayersFileName,
                kNameSize);
    // ★ 缓冲是 `static`（文件作用域等效）：players.xml 很小（Trinity 那份 ~1 KiB），8 KiB 足够；
    //   真更大时 `ReadTextFile` 返回 `LengthOutOfRange` ⇒ 记一次读失败（不截断、不越界）。
    static char text[8192];
    char resolved[512] = {};
    std::size_t textLength = 0;
    const auto result = isaac::runtime::ResolveThenRead(
        path, &ResolveMountedPath, &g_Menu, &ReadMetadataText, &g_Menu, resolved,
        sizeof(resolved), text, sizeof(text), &textLength);
    if (result != isaac::runtime::MountedReadResult::Read) {
        isaac::runtime::NoteModPlayerNameReadFailure();
        return;
    }
    (void)isaac::runtime::IngestModPlayersXml(directory, text, textLength);
}

// ─────────────────────────────────────────────────────────────────────────────
// 批次 404（2026-10-07）：把一个模组的 `content/items.xml` / `content/pocketitems.xml`
// 并进"收藏品 / 饰品 / 卡牌 名字 → id"追加层
// ─────────────────────────────────────────────────────────────────────────────
//
// ## 为什么在这里、按这个顺序
//
// 三条的 id 规则（批次 404 逐条取证，见 `program/mod_content_names.hpp` 表头）：
//   **id = 本体该类条数 + 该条目在本模组该 xml 里的同类出现顺序（0 基），跨模组按喂入顺序累加。**
//   本体条数：收藏品 733（`items.xml` 的 `<passive>/<active>/<familiar>`）、
//   饰品 190（`items.xml` 的 `<trinket>`）、卡牌 98（`pocketitems.xml` 的 `<card>/<rune>`）。
// 下面 `LoadEngineModContent` 的循环**就是**引擎的喂入顺序（与 401 的 players.xml 同一条路，
// 行 1 = items.xml、行 2 = pocketitems.xml）。⇒ 解析放在**同一个循环、同一个下标顺序**上，
// **绝不自己按目录名/文件名重排** —— 顺序错了 id 就错，而且是**静默错**（拿到错道具、不报错）。
//
// ## 读文件：与 players.xml 走同一条**已知安全**的路
//
// `ResolveThenRead` + `ResolveMountedPath`（**不用** `File::OpenRead` —— 那个打开失败即 Abort）。
// 读失败记 `readFailures`、解析失败记 `malformedFiles`（都在 `ModContentNameStatistics()`）。
// ★ 残余风险**写在明处**（与 401 同一条）：若引擎成功喂进了某个模组的 items.xml、而我们这一刻
//   读/解析失败，则那个模组的名字进不了表、而引擎确实占了 id —— 表现为**后面模组的 id 整体偏移**；
//   `readFailures > 0` / `malformedFiles > 0` 就是这件事的信号（正常应恒 0）。
void FeedOneContentNameFile(isaac::runtime::ModContentFileKind file, const char* fileName,
                            const char* directory, char* path, std::size_t baseLength,
                            std::size_t pathCapacity) noexcept {
    if (directory == nullptr || directory[0] == '\0' || path == nullptr || fileName == nullptr) {
        return;
    }
    constexpr std::size_t kPrefixLength = sizeof(kModContentDirectoryPrefix) - 1;  // "/content/"
    const std::size_t nameSize = std::strlen(fileName) + 1;                        // 含结尾 NUL
    if (baseLength + kPrefixLength + nameSize > pathCapacity) {
        return;  // 装不下就跳过（绝不截断成半个路径）
    }
    std::memcpy(path + baseLength, kModContentDirectoryPrefix, kPrefixLength);
    std::memcpy(path + baseLength + kPrefixLength, fileName, nameSize);
    // ★ 缓冲是 `static`（文件作用域等效）且**两个文件共用**（调用是串行的）：一个模组的
    //   items.xml 正常只有几 KB（语料最大 ~5.5 KiB）；64 KiB 足够。真更大时 `ReadTextFile`
    //   返回 `LengthOutOfRange` ⇒ 记一次读失败（不截断、不越界）——那种情况就是上面写的
    //   "残余风险"（id 会整体偏移），由 `readFailures` 读数暴露。
    static char text[65536];
    char resolved[512] = {};
    std::size_t textLength = 0;
    const auto result = isaac::runtime::ResolveThenRead(
        path, &ResolveMountedPath, &g_Menu, &ReadMetadataText, &g_Menu, resolved,
        sizeof(resolved), text, sizeof(text), &textLength);
    if (result != isaac::runtime::MountedReadResult::Read) {
        isaac::runtime::NoteModContentNameReadFailure();
        return;
    }
    (void)isaac::runtime::IngestModContentXml(file, directory, text, textLength);
}

//: 把本模组的 `items.xml`（收藏品 + 饰品）与 `pocketitems.xml`（卡牌）按**引擎的调用次序**
//: （第 1 项 → 第 2 项）喂进追加层。同一个模组下标 ⇒ 与引擎的 id 分配逐格对齐。
void FeedModContentNames(const char* directory, char* path, std::size_t baseLength,
                         std::size_t pathCapacity) noexcept {
    FeedOneContentNameFile(isaac::runtime::ModContentFileKind::Items,
                           isaac::runtime::kModContentItemsFileName, directory, path, baseLength,
                           pathCapacity);
    FeedOneContentNameFile(isaac::runtime::ModContentFileKind::PocketItems,
                           isaac::runtime::kModContentPocketItemsFileName, directory, path,
                           baseLength, pathCapacity);
}

//: **只做一次**：对**每一个启用着的**模组，把它 `content/` 下的皮肤与音乐直接喂给引擎。
//:
//: * 模组目录来自**我们自己的发现结果**（`ModMenuDiscoveredDirectory`，与模组页显示的是同一份）；
//: * "启用的"用 `ModMenuDiscoveredEnabled` 判定 —— 与批次 147 那条闸门认的**存档侧开关**同源，
//:   所以"用户在模组页关掉的模组不会被加载"这条语义不变；
//: * 路径写法 = `isaac_mods/mods/<目录>/content/<文件名>`（**不带 `rom:/`**）：引擎的文件层
//:   认的是"相对应用根"的输入，这条批次 085 已真机验证过；
//: * 两个加载器**自己**对"文件不存在/打不开"有普通分支（`FileManager::OpenRead` 返回空即返回），
//:   所以**不需要**我们先用 `Exists` 探一次（那还需要另接一个引擎入口）；
//: * 全程**不碰** `Manager+0x36800`、不写 `g_ModdingDataPath` ⇒ 模组页不受影响。
//: 喂模组 content 的**尝试次数上限**（批次 153 起"只做一次"→ 两次 → 本批 8 次）。
//:
//: 为什么允许这么多次、为什么会有多个触发点：真机已经暴露"时机"是这件事的成败关键，而我们能
//: 拿到的最早时机（模组脚本之前，`ManagerUpdateHook::Callback` 里）**不一定**已经能解析挂载路径
//: —— 2026-09-27 的崩溃（`dist/crash-153-20260927-1121.log`）就是"那次没喂成、而用户按提示
//: 直接进了局、没开模组页"⇒ 模组的 `content/music.xml` 始终没进引擎 ⇒ 它拿到 `-1` 去
//: `Music::Play` ⇒ 崩。所以**不能依赖任何单一时机**：每帧那条路会按下面这个间隔重试到成功为止。
//: ★ 上限存在的理由：每次尝试都真的读文件 + 调引擎，不许无上限地试。
constexpr std::uint32_t kMaximumContentLoadAttempts = 16;
//: 相邻两次重试至少隔这么多帧（`ModMenuNativeUpdate` 的每帧计数；≈0.5 秒 @60fps）。
//: 目的是给"引擎还没就绪"留出时间，同时避免每帧都去读文件。
//: （16 次 × 0.5 秒 ≈ 8 秒的覆盖，再加上"模组脚本之前"那一次 —— 真机上出问题的那个窗口
//: 是开机后头几秒，这个覆盖足够；上限只是防止一直空转。）
constexpr std::uint32_t kContentLoadRetryIntervalFrames = 30;

//: 上一次真的去尝试加载是在第几帧（`g_ModMenuState.drivenFrames` 口径）。
std::uint32_t g_LastContentLoadFrame{0};

//: 已经喂进去了吗（判据 = 两个容器**任一**涨过）。**任一**就停：多喂一次会把同一条内容加两遍
//: （23 条服装、2 首曲子都会重复），那个代价比"另一边没喂成"大得多。
bool EngineModContentLoaded() noexcept {
    return g_CostumeCountAfter > g_CostumeCountBefore ||
           g_MusicEntryCountAfter > g_MusicEntryCountBefore;
}

bool LoadEngineModContent(const TargetModule& module, std::uint32_t trigger) {
    // 闸：**最多 8 次**，且"涨过就不再试"。多个触发点共用这一个闸（见上面两个常量的注释）。
    // ★ 本仓源码不许用 bool 版原子量（门禁按文本判定），所以还是 `uint32_t`。
    static std::atomic<std::uint32_t> attempts{0};
    const std::uint32_t slot = attempts.fetch_add(1U, std::memory_order_acq_rel);
    if (slot >= kMaximumContentLoadAttempts) {
        return g_ModEngineScanStage == 2;
    }
    if (slot != 0 && EngineModContentLoaded()) {
        return true;  // 上一次已经喂进去了 ⇒ 不重复喂
    }
    g_ModMenuState.modEngineTrigger = trigger;
    g_LastContentLoadFrame = g_ModMenuState.drivenFrames;
    g_ModEngineScanAttempts += 1;
    std::uintptr_t manager = g_Menu.manager;
    if (manager == 0) {
        // ★ 批次 153：走"模组脚本之前"那条路时，每帧更新可能还没跑过 ⇒ `g_Menu.manager` 是 0。
        // 这里按**引擎自己的 `g_Manager` 槽**现取一次（与 `ModMenuNativeUpdate` 里那句同一个
        // 来源）。
        (void)ReadSingleton(module, kManagerSlotOffset, &manager);
    }
    if (manager == 0 || manager > UINTPTR_MAX - kManagerItemConfigOffset ||
        manager > UINTPTR_MAX - kManagerMusicOffset ||
        // ★★ 批次 378：本批新用到的三个子对象偏移也要防回绕（同一条纪律：先算清楚再碰内存）。
        manager > UINTPTR_MAX - kManagerEntityConfigOffset ||
        manager > UINTPTR_MAX - kManagerSoundEffectsOffset ||
        manager > UINTPTR_MAX - kManagerNightmareSceneOffset) {
        g_ModEngineScanStage = 3;
        return false;
    }

    // 两个加载器：`LoadCostumes` 是成员函数（x0 = ItemConfig*），第二个参数是 `ModEntry*`。
    // ★★ 批次 152：这个参数**不能传 `nullptr`**（149b 的 `132 → 132` 就是它）——
    //    引擎入口处那个 `csel` 只是"不崩"，空指针会让 `type="none"` 的条目**一条都不加**
    //    （它落到"按 XML 的 `id` 去找**已有**那条"的路，那是本体资源那条路）。
    //    见本文件上面 `SubstituteModEntry` 那一段与 `runtime_constants.hpp` 的批次 152。
    // `Music::LoadConfig` 第二个参数按引擎对模组传的值传 `true`。
    MakeEmptyCostumeTree(g_SubstituteModEntry.costumeMap);
    MakeEmptyCostumeTree(g_SubstituteModEntry.trinketMap);
    void* const modEntry = &g_SubstituteModEntry;
    using LoadCostumesFn = void (*)(void* config, const char* file, void* modEntry);
    using LoadMusicFn = void (*)(void* music, const char* file, bool append);
    const LoadCostumesFn loadCostumes = ResolveEngineEntry<LoadCostumesFn>(
        module, kItemConfigLoadCostumesFileOffset, kItemConfigLoadCostumesExpectedBytes.data(),
        kItemConfigLoadCostumesExpectedBytes.size());
    if (loadCostumes == nullptr) {
        g_ModEngineResolveFailures |= 1u;
        g_ModEngineScanStage = 3;
        return false;
    }
    const LoadMusicFn loadMusic = ResolveEngineEntry<LoadMusicFn>(
        module, kMusicLoadConfigFileOffset, kMusicLoadConfigExpectedBytes.data(),
        kMusicLoadConfigExpectedBytes.size());
    if (loadMusic == nullptr) {
        g_ModEngineResolveFailures |= 2u;
        g_ModEngineScanStage = 3;
        return false;
    }
    g_ModEngineScanStage = 1;

    // 加载前的基线（验收判据就是这两对数字的前后差）。
    g_MusicEntryCountBefore = CountMusicEntries(manager);
    g_CostumeCountBefore = CountNullCostumeEntries(manager);

    void* const config = engine_memory::AsObject(manager + kManagerItemConfigOffset);
    void* const music = engine_memory::AsObject(manager + kManagerMusicOffset);
    // ★★ 批次 155（2026-09-27）：**先直接喂"相对应用根"的路径，把 `GetMountedFilePath` 降级成兜底。**
    //
    // 为什么改（真机读数把这条钉死了）：`GetMountedFilePath` 返回的是
    // `rom:/isaac_mods/mods/<目录>/content/<文件>`，去掉 `rom:/` 之后与**我们自己拼的那条
    // 一模一样**（读数里两行逐字对上）⇒ 它其实是**恒等变换**，只多了一个"这条路径在挂载表里吗"
    // 的校验，而**那个校验依赖 `ContentManager` 就绪**。
    // 而 154 的真机读数显示：在"模组脚本之前"那一刻，`ResolveMountedPath` **全部解析不到**
    // （`[61]` 显示"跑完了"但两个容器一条没涨 —— 见下面 stage 4 的说明），于是我们**整条都跳过了**；
    // 内容直到后面某次每帧重试（`[60] = 3`）才真正进去，**那时模组的服装编号早就查成 `-1` 了**。
    // ⇒ 所以：**不依赖解析**。引擎自己那条模组路（`ModManager::LoadConfigs`）就是拿
    // `ModEntry::GetContentPath` 拼出的"相对应用根"串**直接**交给 `FileManager::OpenRead` 的
    // （`0x41E388` 那段反汇编），我们照它做。
    // 解析仍然保留作**兜底**：先用解析结果（去掉 `rom:/`）再试一次，判据始终是"容器涨没涨"。
    // `FileManager::OpenRead` 打开失败是**普通分支**（返回空即返回，不 abort）⇒ 直接喂没有风险。
    PrepareSourceContext(module);
    // ★★ 批次 378：把引擎那 16 项的入口一次性解析好（16 字节序言 + 每行自己的 4 字节判别式）。
    //    放在循环**之前**：解析结果与模组无关（只依赖模块基址），而且失败要能写进读数
    //    （`[68]/[69]`）—— 即使一个模组都没有，读数里也该看得出"入口解析全没全"。
    //    失败**不整批放弃**：记位、跳过那一项、其余照喂（理由见 `EnsureModContentFeedResolved`）。
    EnsureModContentFeedResolved(module);
    char path[256] = {};
    char resolved[512] = {};
    const std::size_t modCount = isaac::runtime::ModMenuDiscoveredCount();
    // 与脚本、挂载使用同一份开机过滤结果（含disable.it和仅资源模组）。
    // 菜单开关是下次启动的意图，不能把本次未加载的内容重新喂入引擎。
    const auto contentMods = isaac::runtime::ModMenuDiscoveredForReading();
    for (std::size_t index = 0; index < modCount; ++index) {
        const char* directory = isaac::runtime::ModMenuDiscoveredDirectory(index);
        if (directory == nullptr || directory[0] == '\0' ||
            (contentMods.activeMask & (std::uint32_t{1} << index)) == 0) {
            continue;
        }
        const std::size_t directoryLength = std::strlen(directory);
        const std::size_t prefixLength = std::strlen(kModdingDataPathValue) + directoryLength;
        if (prefixLength > sizeof(path) - 32) {
            continue;  // 装不下就跳过这一条（绝不截断成半个路径）
        }
        std::memcpy(path, kModdingDataPathValue, std::strlen(kModdingDataPathValue));
        std::memcpy(path + std::strlen(kModdingDataPathValue), directory, directoryLength + 1);
        const std::size_t baseLength = std::strlen(path);
        // ★★ 批次 378：先把 `<模组根>/content/` 拼出来（**带结尾 `/`**），它有两个用途：
        //    ① 写进真条目的 `+0x48`/`+0x60`（`GetContentPath` 靠它找模组自己的资源，见下）；
        //    ② 后面 12 项各自的 `content/<文件名>` 就是在它后面接着拼（这里不截断它，
        //       `FeedModContentFile` 每次都是"从 baseLength 重新写"）。
        if (baseLength + sizeof(kModContentDirectoryPrefix) > sizeof(path)) {
            continue;  // 与上面那道长度闸同一条纪律（按本表最长的名字算不可能命中，见函数注释）
        }
        std::memcpy(path + baseLength, kModContentDirectoryPrefix, sizeof(kModContentDirectoryPrefix));
        // ★★ 批次 378：这一批"没有可观测信号"的东西（真条目 + `LoadCustomResources` +
        //    下面那 12 个 content 文件）**每个模组只喂一次**（理由见 `g_ModContentUnobservableFedMask`）。
        const bool unobservableFed =
            index < 32 && (g_ModContentUnobservableFedMask & (static_cast<std::uint32_t>(1) << index)) != 0;
        void* realEntry = nullptr;
        if (!unobservableFed) {
            // ★★ 批次 378：这个模组的**真 `ModEntry`**（引擎自己的构造器造；按下标惰性、只造一次）。
            //
            // 为什么必须有它：引擎那 16 项里有 8 项要把 `ModEntry*` 当第三个参数（`+0x108`/`+0x120`
            // 那两张 map = 这个模组的服装上下文），而**绝对不能传空指针**（批次 149b 的 `132 → 132`
            // 就是它：空指针会让 `type="none"` 的条目一条都不加）。本批之前用的那个 `0x140` 字节替身
            // 之所以不能用在这里：`LoadCustomResources` 会往 `+0x140` 起的 13 个 `ANM2` 写（到 `+0x1008`）
            // ⇒ 那是**越界写**。造不出来（没解析到 / 超出竞技场）时返回 `nullptr`，
            // 需要它的项会被跳过、其余项照喂（见 `FeedModContentFile`）。
            realEntry = RealModEntryForIndex(static_cast<std::uint32_t>(index), path);
            // ★★ 批次 378：引擎每个模组的**第一个**动作就是它（`0x41E414`，在 `entities2.xml` 之前）。
            FeedModCustomResources(realEntry);
        }
        // ★★ 批次 378：14 项按**引擎的调用次序**喂（表序 = 引擎表序）。
        //    第 4 / 第 13 项（`costumes2.xml` / `music.xml`）走下面那条批次 148~156 真机定案的
        //    专用路：它要"两种路径口径 + 容器涨没涨"的取证，而且门禁钉着那两处调用形状
        //    （`loadCostumes` 恰好两次、第三个参数必须是那个非空替身）。**它们同样只喂一遍**，
        //    只是喂的动作在专用路里；`g_ModMenuState.modEngineContentCalls` 两边都算。
        for (std::size_t row = 0; row < kModFeedContentRows; ++row) {
            if (row == kModFeedRowCostumes) {
                // ① 皮肤；② 音乐（两条路径只差文件名，拼一次前缀用两次）。
                //    ★★ 批次 155：**先直接喂 `path`**（= 相对应用根，引擎自己那条路的形式）；
                //       涨了就不再试别的（避免把同一条内容加两遍）。
                //       没涨才去解析一次作兜底 —— 判据始终是**容器涨没涨**（客观信号）。
                //       形状记录：`g_ModEngineCostumeForm` 1 = 直接喂成功 / 2 = 解析后的串才成功。
                if (baseLength + sizeof(kModContentCostumesFile) <= sizeof(path)) {
                    std::memcpy(path + baseLength, kModContentCostumesFile,
                                sizeof(kModContentCostumesFile));
                    CopyPathForEvidence(g_ModEngineResolvedCostumes, sizeof(g_ModEngineResolvedCostumes),
                                        path);
                    const std::uint32_t before = CountNullCostumeEntries(manager);
                    loadCostumes(config, path, modEntry);
                    g_ModEngineCostumeCalls += 1;
                    g_ModMenuState.modEngineContentCalls += 1;  // 批次 378：与 14 项同一个计数器
                    g_ModEngineCostumeLoads += 1;
                    if (CountNullCostumeEntries(manager) > before) {
                        g_ModEngineCostumeForm = 1;
                    } else if (ResolveMountedPath(&g_Menu, path, resolved, sizeof(resolved))) {
                        loadCostumes(config, RelativeToApplicationRoot(resolved), modEntry);
                        g_ModEngineCostumeCalls += 1;
                        g_ModMenuState.modEngineContentCalls += 1;  // 批次 378：同上（第二种口径）
                        if (CountNullCostumeEntries(manager) > before) {
                            g_ModEngineCostumeForm = 2;
                        }
                    } else {
                        g_ModEnginePathResolveMisses += 1;
                    }
                }
            } else if (row == kModFeedRowMusic) {
                if (baseLength + sizeof(kModContentMusicFile) <= sizeof(path)) {
                    std::memcpy(path + baseLength, kModContentMusicFile,
                                sizeof(kModContentMusicFile));
                    CopyPathForEvidence(g_ModEngineResolvedMusic, sizeof(g_ModEngineResolvedMusic),
                                        path);
                    const std::uint32_t before = CountMusicEntries(manager);
                    loadMusic(music, path, true);   // ★ 批次 155：先直接喂（与服装侧同一条理由）
                    g_ModEngineMusicCalls += 1;
                    g_ModMenuState.modEngineContentCalls += 1;  // 批次 378：同服装侧
                    g_ModEngineMusicLoads += 1;
                    if (CountMusicEntries(manager) > before) {
                        g_ModEngineMusicForm = 1;
                    } else if (ResolveMountedPath(&g_Menu, path, resolved, sizeof(resolved))) {
                        loadMusic(music, RelativeToApplicationRoot(resolved), true);
                        g_ModEngineMusicCalls += 1;
                        g_ModMenuState.modEngineContentCalls += 1;  // 批次 378：同上
                        if (CountMusicEntries(manager) > before) {
                            g_ModEngineMusicForm = 2;
                        }
                    } else {
                        g_ModEnginePathResolveMisses += 1;
                    }
                }
            } else if (!unobservableFed) {
                // 其余 12 项：拼 `<模组根>/content/<文件名>` 直接喂（与引擎同形）。
                // ★★ 批次 378：**只喂一次**（`unobservableFed` 为真 ⇒ 这一轮是重试，
                //    跳过 —— 否则"追加语义"的那几个加载器会加出重复条目，见那个掩码的注释）。
                FeedModContentFile(row, manager, realEntry, path, baseLength, sizeof(path));
            }
        }
        // ★★ 批次 401：把本模组 `content/players.xml` 声明的角色名并进"角色名 → id"追加层。
        //    ★ 位置与顺序**就是**喂入顺序（同一个循环、同一个下标）——见 `FeedModPlayerTypeNames`。
        //    ★ 只在 `!unobservableFed` 时做：与 `players.xml` 交给引擎的**同一次**喂入对齐
        //      （那道一次性掩码保证"每个模组的这批内容只喂一次"）；追加层自己还有 modKey 幂等兜底。
        //    ★ `realEntry == nullptr` ⇒ `players.xml`（需要 `ModEntry*`）根本没交给引擎
        //      （见 `FeedModContentFile`）⇒ 名字也不该追加（否则与引擎的 id 分配错开）。
        if (!unobservableFed && realEntry != nullptr) {
            std::array<char,sizeof(path)> shaderRoot{};
            std::memcpy(shaderRoot.data(),path,baseLength);shaderRoot[baseLength]='\0';
            // 解析服务未就绪是加载失败，不能误当成该模组没声明shader。
            const auto shaderResolver =
                g_Menu.getMounted && g_Menu.contentManager && g_Menu.freePath
                    ? &ResolveMountedPath : nullptr;
            if(!isaac::runtime::LoadModShaderFile(g_Menu.fileBindings,shaderRoot.data(),
                                                 shaderResolver,&g_Menu)){
                std::array<char,320> message{};
                const auto status=isaac::runtime::ShaderPipelineStatsSnapshot();
                const int count=std::snprintf(message.data(),message.size(),"shader load failed (%u): %s/content/shaders.xml",static_cast<unsigned>(status.error),shaderRoot.data());
                if(count>0)LuaRuntime::RecordLuaErrorText(message.data(),std::min(static_cast<std::size_t>(count),message.size()-1));
            }
            FeedModPlayerTypeNames(directory, path, baseLength, sizeof(path));
            // ★★ 批次 404：同一位置、同一模组下标，把 items.xml（收藏品+饰品）与
            //    pocketitems.xml（卡牌）并进各自的追加层（见 `FeedModContentNames`）。
            //    条件与 `players.xml` 逐字相同：`!unobservableFed`（与引擎的这一次喂入对齐）
            //    且 `realEntry != nullptr`（这两个文件都需要 `ModEntry*`，拿不到就不喂）。
            FeedModContentNames(directory, path, baseLength, sizeof(path));
        }
        // ★★ 批次 378：置位表示"这一批已经喂过"，后面几轮重试不再喂（服装/音乐两行不受影响）。
        if (!unobservableFed && index < 32) {
            g_ModContentUnobservableFedMask |= (static_cast<std::uint32_t>(1) << index);
        }
        g_ModEngineModEntries += 1;
    }
    // ★★ 批次 409（2026-10-08）：**"涨没涨"必须先量出来，再收尾。**
    //
    // 为什么（真机读数钉死的 bug）：`RunPostLoadModsOnceIfDue` 那道闸读的就是
    // `EngineModContentLoaded()`，而它比的是 `g_MusicEntryCountAfter/g_CostumeCountAfter`
    // 与各自的 `Before` —— 这两对全局原来是在**这一行之后**才赋值的 ⇒ 闸看到的是**上一轮**
    // 的读数。于是"这一轮才真正把内容喂进去"的那一次，闸拿到的仍是上一轮的
    // "`After == Before`"（上一轮确实一条没涨）⇒ `PostLoadMods` **永远不执行**。
    // 真机实测（2026-10-08，带模组角色进局、设备侧 `mem` 读状态面）：
    //   `[70] 14 项加载器调用 = 154`、`[72] LoadCustomResources = 11`、`[73] 真 ModEntry = 11`、
    //   `stage = 2`（两个容器确实涨了：music 119→205、costume 132→160）—— 唯独
    //   `[71] PostLoadMods = 0`、`[74] mod_defaults ANM2 载入 = 0`。
    // ⇒ 把这两行**提到收尾之前**（判据本身一个字没改，只改"量的时机"）。
    g_MusicEntryCountAfter = CountMusicEntries(manager);
    g_CostumeCountAfter = CountNullCostumeEntries(manager);

    // ★★ 批次 378：`EntityConfig::PostLoadMods()` —— 引擎在**所有模组都喂完之后**调一次
    //    （循环外 `0x41ED24`：`x0 = Manager + 0x36758`）。判据（"这一轮真喂进去了"/"最后一次尝试"）
    //    与"进程内只调一次"的理由写在 `RunPostLoadModsOnceIfDue` 上面。
    //    ★★ 批次 409：紧跟其后的 `LoadModManagerDefaultAnm2Once`（引擎 `0x41ED7C` 那一步）在
    //    **同一个一次性闩锁里** ⇒ 收尾不执行时它也不执行（真机就是这么漏掉的）。
    RunPostLoadModsOnceIfDue(manager, slot + 1 >= kMaximumContentLoadAttempts);
    // 真实配置写入和避让完成后显式刷新；同根/同size重新装载也重建名字索引。
    static_cast<void>(isaac::runtime::RefreshRuntimeContentNames());

    // ★★ 批次 155：把"**跑完了**"与"**真喂进去了**"分成两个阶段字 —— 154 那次就是被这一格误导的。
    //
    // 154 的写法是"走到函数末尾就记 2"，于是 `[61] 早期那次 = 2` 看起来像"喂进去了"，
    // 而实际上那次**一条都没加载**（`ResolveMountedPath` 在那个时刻全部解析不到 ⇒ 整条跳过）。
    // 我据此以为"早期时机已经通了"，而真机事实是：内容直到后面某次每帧重试才进去，
    // 那时模组的服装编号早就查成 `-1` 了 ⇒ **舞照旧不出来**。
    // ⇒ 现在：**涨了才是 2**；跑完但两个容器都没涨 = **4**（文件没打开 / 路径不对 / 挂载没就绪）。
    g_ModEngineScanStage = EngineModContentLoaded() ? 2 : 4;
    // 批次 149c：把曲目表最后一条的编号与名字原始字节留证（条目布局的自证）。
    ReadMusicEntryEvidence(manager);
    return true;
}

//: 进模组页：补上 Switch 版删掉的那一下（`Menu_Mods::Reset`），再走引擎自己的 `SetState(16)`。
void EnterModsPage(const TargetModule& module, const ActionQueryFn query) {
    // 0) 前提：得在"选择界面"那一屏（否则说明这一下不是从我们那一格来的）。
    if ((ReadMenuState(g_Menu.menuManager)) != kGameMenuState) {
        return;
    }
    // 0.5) ★★ 批次 148：把模组的 `content/`（皮肤 + 音乐）喂给引擎 —— 这一步**只读文件、只调
    //      两个加载器**，`Manager+0x36800` 那张模组表**一格都不动**（所以页面行为与 147 逐字相同）。
    //      时机仍选"进模组页这一刻"：批次 144c 真机证明**读文件**在这个时刻是安全的
    //      （它读的是 `KAGE::Filesys::FileManager`，与模组脚本加载走同一套，早已可用）。
    //      ⚠️ 不要因为"想让它更早生效"就把它挪到每帧第一帧：143/144 在那里各崩过一次。
    // 批次 153：这个调用现在是**兜底**了 —— 正常时机是"模组脚本执行之前"
    // （`LoadEngineModContentBeforeModScripts`，由 `hook_manager.cpp` 在
    // `InitializeDefaultManifestMod` 前一行调）。这里只在"那一次没喂成"时才真的动手（函数里的
    // 两次闸会判掉重复），所以留着它不重复加载、也不会退回旧行为。
    (void)LoadEngineModContent(module, 2);
    // 1) 页面得是"已经 Init 过"的。没起来就**当场补做一次**，而不是直接放弃
    //    （那正是"按了确认却跳到统计页面"的一个可能原因：我们退出了，引擎就按它自己的索引去处理）。
    if (g_Menu.pageInitState != kInitOk) {
        if (TryPrepareModsVector()) {
            InitManualPage();
        }
        if (g_Menu.pageInitState != kInitOk) {
            return;
        }
    }
    // 2) "归零"这一下**不再依赖引擎的 `Reset`**：那几个字段我们自己就能写。
    //    引擎的 `Reset` 只在守卫过得去时额外调一次（它还会重读一遍 ModManager 指针、播 "Main" 动画）。
    const std::uint32_t zero = 0;
    // ★ `g_ModsObject` 是**我们自己的**静态壳（文件上半部分：`Menu_Mods` 的内嵌成员没有定论，
    //   探针用一块静态内存当壳、真机跑通了），不是引擎对象 —— 但它的那几个字段是**交给引擎当
    //   `this` 用**的，所以照样走访问层：本 TU 里"算地址 + 读/写"只有一条路，读代码的人不必
    //   分辨"这一处的目标是谁"。代价是每次多一次可写判定（我们自己的 bss，判定恒通过）。
    const std::uintptr_t modsObject = engine_memory::AddressOf(g_ModsObject);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsSelectedElementOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsHoldTimerOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsEditedOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    if (g_Menu.modsReset != nullptr) {
        g_Menu.modsReset(g_ModsObject);
    } else {
        // 守卫不过只是"少做一次锦上添花"，**不是**不进去的理由。
        g_ModMenuState.failure = kFailureMenuModsResetGuard;
    }
    // 4) 先让"那一格的滚动值"变成确定值，再去算纸的位置（见 `kSetModsOffsetOffset` 的注释：
    //    不先调一次的话，第一次进来读到的还是 `Init` 的旧值，用户看到"错位 1~2 秒"）。
    if (g_Menu.setModsOffset != nullptr) {
        g_Menu.setModsOffset(engine_memory::AsObject(g_Menu.menuManager), 0);
    }
    ++g_ModMenuState.pageEnterCalls;
    // 批次 144：用户打开模组页 ⇒ 存档/文件子系统必然已就绪 **且**是游戏线程 ⇒ 这时才安全地
    // 只读一眼 `options.ini`（第一版放在"每帧第一帧"直接崩了，见 `ProbeEngineOptionsFile` 注释）。
    ProbeEngineOptionsFile();
    // 5) 交给引擎的状态机（= PC 的做法）。这一步**必须**发生：走到这里之后引擎本帧的分派表
    //    （`cmp w8,#0xf`）就不会再去叫 `Menu_Game::Update`，也就不会再拿我们那一格的行号去开统计页。
    ApplyState(module, isaac::runtime::kModsPageState);
    // 6) 回来时光标要落在我们那一格上（理由见 `g_RestoreOurs`）。
    g_RestoreOurs = 1;
    // 7) 位置那套状态机（第二帧定位置、停稳后自证一次）每次进页面都要重来。
    // 8) 把引擎的"模组总开关"置上。真机读数（探针批次 058）发现它是 **0**，而 `Menu_Mods::Render`
    //    在它为 0 时**只用一个颜色画所有行**（不读条目自己的 `+0x138`）⇒ 不置它，
    //    "按确认切换开关"在屏幕上根本看不出来。**只改内存**，不碰任何文件。
    if (g_Menu.manager != 0) {
        const auto wanted = static_cast<std::uint8_t>(isaac::runtime::kModsEnabledGateOn);
        // 写引擎自己的一个字节 ⇒ 走访问层（先确认可写）。写不进去只是"颜色不变"，
        // 页面照样进得去 ⇒ 不报失败码、也不改判据。
        (void)engine_memory::WriteField(g_Menu.manager, kManagerModsEnabledOffset, wanted,
                                        &engine_memory::EngineMemoryWritable, 0);
    }
    // 8) ★★ 必须把输入边沿按"**当前**还按着的情况"锁上，否则页面第一帧就会误判一次新按下：
    //    进页面用的就是那个确认键（A），它现在**还按着**，而上一帧状态是 0 ⇒ 第一帧的 `Edge()`
    //    会返回"刚按下" ⇒ **刚进去就顺手把第一个模组的开关翻掉了**。按住计时同理。
    bool directionHeld = false;
    if (query != nullptr) {
        const bool confirmHeld = HeldByAnyone(query, kActionConfirm);
        const bool backHeld = HeldByAnyone(query, kActionBack);
        const bool upHeld = HeldByAnyone(query, kActionUp);
        const bool downHeld = HeldByAnyone(query, kActionDown);
        g_PageLastConfirm = isaac::runtime::ModPageLatchedEdge(confirmHeld);
        g_PageLastBack = isaac::runtime::ModPageLatchedEdge(backHeld);
        g_PageLastUp = isaac::runtime::ModPageLatchedEdge(upHeld);
        g_PageLastDown = isaac::runtime::ModPageLatchedEdge(downHeld);
        directionHeld = upHeld || downHeld;
    }
    const std::uint32_t seed = isaac::runtime::ModPageHoldSeed(directionHeld);
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsHoldTimerOffset, seed,
                                    &engine_memory::EngineMemoryWritable, 0);
}

//: 状态 16 期间由我们驱动页面：导航（含按住重复）、切换开关、返回。
//: 数据面：`g_Manager + 0x36800` 那张表（`begin/end/cap`，每项一个指针，条目里 `+0x138` 是启用位）。
void ModsPageUpdate(const TargetModule& module, const ActionQueryFn query) {
    const bool active = isaac::runtime::ModPageIsActive(g_Menu.menuState);
    // ★ **离开模组页**（刚刚还在、现在不在了）且这次改过开关 ⇒ 落盘一次
    //（用户 2026-09-22 裁定："退出时写一次"）。写的是**游戏存档分区**，不是卡上的覆盖层。
    if (g_Menu.pageWasActive != 0 && !active) {
        g_Menu.pageWasActive = 0;
        std::uint32_t edited = 0;
        // 读不到就当作"没改过"（= 不落盘）：宁可少写一次盘，也不要凭一个猜出来的值去写存档。
        const bool editedRead =
            engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                     isaac::runtime::kModsEditedOffset, &edited,
                                     &engine_memory::EngineMemoryReadable, 0);
        if (isaac::runtime::ModPageShouldPersist(editedRead && edited != 0)) {
            g_ModMenuState.toggleSaveState = isaac::runtime::ModMenuSaveToggles() ? 1U : 2U;
        }
        ++g_ModMenuState.pageBackCalls;
        // ★★ 2026-09-23 修：**边沿状态只在"真的离开这一页"那一刻清零**，不在这里之外的
        //    任何 `!active` 帧清（下面那个早退分支以前就是这么干的，是个真 bug）。
        //
        // 真机现象（用户 2026-09-23 报）：**每次进模组页，第一个模组的开关都会自己翻一次。**
        // 机制（同一帧的先后顺序）：
        //   ① `ModRowUpdate` 里我们那一格的确认 ⇒ `EnterModsPage()`，它把四个边沿
        //      **按"当前还按着的情况"锁上**（`ModPageLatchedEdge`，进页面用的就是 A 键、
        //      此刻还按着）⇒ 目的正是"下一帧不许把它当成新按下"；
        //   ② **同一帧**接着跑 `ModsPageUpdate`：`g_Menu.menuState` 是这一帧**开头**读的，
        //      那时还没切到 16 ⇒ `active == false` ⇒ 走了下面那个早退分支、**把刚锁上的清零**；
        //   ③ 下一帧状态已是 16、`active == true`，而 A 还按着、上一帧记的是 0
        //      ⇒ `Edge()` 返回"刚按下" ⇒ 顺手把第一条的开关翻掉。
        // ⇒ 清零只属于"离开这一页"这个动作，不能顺手放在"当前不在这一页"上。
        g_PageLastUp = 0;
        g_PageLastDown = 0;
        g_PageLastConfirm = 0;
        g_PageLastBack = 0;
    }
    if (!active) {
        // 当前不在这一页（含"刚切进来、状态还是上一帧那份"那一帧）：**什么都不动**。
        // 尤其**不许清边沿状态** —— 理由见上面那段（清了就会在进页面后第一帧误判一次确认）。
        return;
    }
    g_Menu.pageWasActive = 1;
    ++g_ModMenuState.pageDrivenFrames;

    // ── 批次 145（2026-09-26）：每帧把引擎的"启用模组"总闸置回 1 ──────────────────────────
    // 为什么不是"进页面时置一次"就够：引擎**自带**的 `Menu_Mods::Update` 里有一段"按键翻转这一位"
    // （镜像 `0x410650`：`Input::IsActionTriggered(...,0x17,...)` → `eor` → `strb [Manager+0x36519]`；
    // 项目文档里也记过"按 0x17 键翻转这一位就是 PC 的启用模组开关"）。真机上它把总闸从 **1 翻成 0**
    // ⇒ 引擎随后扫模组目录时把**每条模组**都标成"未启用"（§024 读数 `+0x139` 全 0）⇒ 模组的
    // `content/*.xml`（皮肤、音乐）永远不加载。**我们才是这一页的驱动者**（引擎那一份是历史遗留），
    // 所以每帧纠正一次：翻转之后下一帧就置回来；`g_ModsGateRestores` 记下纠正过几次（读数可查）。
    if (g_Menu.manager != 0) {
        std::uint8_t gate = 0;
        if (engine_memory::ReadField(g_Menu.manager, kManagerModsEnabledOffset, &gate,
                                     &engine_memory::EngineMemoryReadable, 0) &&
            gate == 0) {
            (void)engine_memory::WriteField(g_Menu.manager, kManagerModsEnabledOffset,
                                            static_cast<std::uint8_t>(isaac::runtime::kModsEnabledGateOn),
                                            &engine_memory::EngineMemoryWritable, 0);
            ++g_ModsGateRestores;
        }
    }

    // ── 数据面：条目表 ──────────────────────────────────────────────────────────────
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    std::uint32_t entryCount = 0;
    if (g_Menu.manager != 0) {
        (void)engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset, &begin,
                                       &engine_memory::EngineMemoryReadable, 0);
        (void)engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset + 8, &end,
                                       &engine_memory::EngineMemoryReadable, 0);
        // 条数只接受"像话"的那一种（`begin` 是个真指针、`end-begin` 是 8 的倍数且不太大）。
        if (begin >= 0x1000 && end >= begin && ((end - begin) % 8) == 0 &&
            (end - begin) <= 8ULL * 4096ULL) {
            entryCount = static_cast<std::uint32_t>((end - begin) / 8);
        }
    }
    g_ModMenuState.entryCount = entryCount;

    // ── 页面对象里的两个字段（选中项、按住计时）──────────────────────────────────────
    std::uint32_t selected = 0;
    std::uint32_t hold = 0;
    (void)engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                   isaac::runtime::kModsSelectedElementOffset, &selected,
                                   &engine_memory::EngineMemoryReadable, 0);
    (void)engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                   isaac::runtime::kModsHoldTimerOffset, &hold,
                                   &engine_memory::EngineMemoryReadable, 0);

    // ── 输入 ────────────────────────────────────────────────────────────────────────
    bool up = false;
    bool down = false;
    bool confirm = false;
    bool back = false;
    if (query != nullptr) {
        up = HeldByAnyone(query, kActionUp);
        down = HeldByAnyone(query, kActionDown);
        confirm = HeldByAnyone(query, kActionConfirm);
        back = HeldByAnyone(query, kActionBack);
    }
    const bool upEdge = Edge(&g_PageLastUp, up);
    const bool downEdge = Edge(&g_PageLastDown, down);
    // 节奏与引擎同形（`mod_page_nav.hpp`）：**判断用的是上一帧的计时值**，所以刚按下的那一帧
    // 立刻走一格（那时 `hold` 还是 0），之后要过 50 帧、再每 10 帧一格。
    // 顺序很重要：引擎是 `Update` 先看、`UpdateKeyPress` 后加，我们照这个顺序。
    // ★ 批次 126：**导航范围就是表里的行数** —— 下标 0 那一行（控制台开关）现在**真的在表里**，
    //   所以批次 124 那个"模组条数 + 1"的补丁不再需要。
    const std::uint32_t navCount = entryCount;
    if (upEdge || (up && isaac::runtime::ModPageHoldShouldMove(hold))) {
        selected = isaac::runtime::ModPageAdvance(selected, navCount, false);
    }
    if (downEdge || (down && isaac::runtime::ModPageHoldShouldMove(hold))) {
        selected = isaac::runtime::ModPageAdvance(selected, navCount, true);
    }
    hold = isaac::runtime::ModPageHoldNext(hold, up || down);
    // ★ 写回引擎的选中项 = 行号**原样**（批次 126）。
    //   它一定落在表的行号范围内（下标 0 = 控制台开关行）⇒ 引擎据此**高亮那一行**、
    //   并按它算自己的滚动量（行数超过可见格数时那种原版行为）。
    //   ★ 与批次 124 的差别：那时我们那一行不在表里，只能写**负一哨兵**
    //     （既不高亮任何一行、也不让引擎重算滚动量）；现在写真实行号，光标/高亮/滚动
    //     全部回到引擎的原生行为，我们也不再有"自己画光标"这回事。
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsSelectedElementOffset, selected,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsHoldTimerOffset, hold,
                                    &engine_memory::EngineMemoryWritable, 0);

    // 确认 = 切换这一条的开关。**只改内存**（条目 `+0x138` 那一位），退出页面时才落盘。
    // ★ 批次 126：我们那一行现在在**下标 0**（真的在表里）⇒ 按下标分派：
    //   0 = 控制台开关，其余 = 模组（对应的发现清单下标要减掉我们那一行）。
    if (Edge(&g_PageLastConfirm, confirm)) {
        // `entryCount == 0` = 表是空的（含"一个模组都没发现"那种）⇒ 页面上根本没有我们那一行，
        // 也就不该凭一个看不见的行去拨开关。
        if (entryCount != 0 && selected == kConsoleRowEntryIndex) {
            // 拨**控制台总开关**（对应 PC 的 `EnableDebugConsole`）。**当场生效**（内存值立刻改，
            // 页面上的 ON/OFF 同一帧就变、名字由 `SyncConsoleRowName` 换）；落盘由控制台的每帧点
            // 在下一帧做掉（`RequestConsoleSwitchWrite` 只挂一个"待写"，不在这里做 I/O）。
            isaac::runtime::console::RequestConsoleSwitchWrite(
                !isaac::runtime::console::ConsoleSwitchEnabled());
        } else if (selected < entryCount) {
            const std::uint32_t modIndex = selected - 1U;  // 减掉下标 0 那一行才是模组序号
            std::uintptr_t entry = 0;
            // `begin + 选中项*8` 是"表里第几个指针"的**算好的地址** ⇒ 用 `ReadAt`
            // （它不查对齐，与原实现的裸 memcpy 判据一致）。
            (void)engine_memory::ReadAt(begin + selected * sizeof(std::uintptr_t), &entry,
                                        &engine_memory::EngineMemoryReadable);
            if (entry >= 0x1000) {
                std::uint8_t enabled = 0;
                (void)engine_memory::ReadField(entry,
                                               isaac::runtime::kModPageEntryEnabledOffset, &enabled,
                                               &engine_memory::EngineMemoryReadable, 0);
                const std::uint8_t next = static_cast<std::uint8_t>(
                    isaac::runtime::ModPageToggleEnabled(enabled));
                (void)engine_memory::WriteField(entry, isaac::runtime::kModPageEntryEnabledOffset,
                                                next, &engine_memory::EngineMemoryWritable, 0);
                const std::uint32_t edited = 1;
                (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                                isaac::runtime::kModsEditedOffset, edited,
                                                &engine_memory::EngineMemoryWritable, 0);
                // 把这一下**同时**写进运行时既有的开关服务（只改内存、不落盘）。
                // 页面上那一栏读的就是它（`ModMenuDiscoveredEnabled`），所以两边永远是同一份口径。
                const char* directory = isaac::runtime::ModMenuDiscoveredDirectory(modIndex);
                (void)isaac::runtime::ModMenuSetEnabled(directory, next != 0);
            }
        }
    }
    // 返回 = 引擎自己的做法：`SetState(3)`（`Menu_Mods::Update` 就是这么做的）。
    // 这一步一执行，`MenuManager::Update` 本帧的分派就把 `Menu_Game::Update` 接回来了 ——
    // 也就是说"回到选择界面"完全走引擎的路径，我们不多写一行。
    if (Edge(&g_PageLastBack, back)) {
        ApplyState(module, kGameMenuState);
        return;
    }
    // 把下标 0 那一行的名字对齐到当前开关状态（**放在输入之后**：本帧刚拨过的开关，
    // 本帧就要看到新名字）。
    SyncConsoleRowName();
    g_ModMenuState.selectedEntry = selected;
    g_ModMenuState.failure = kFailureNone;
}

//: 问引擎"继续游戏现在可不可选"（批次 159）。`*out` 只在返回 true 时有效。
//:
//: 口径：`Manager + 0x2B688` 的**两个字节任一个非 0** ⇒ 可选（引擎的导航判据就是这个 ——
//: 它只在两个都是 0 时才跳过那一项）。读法是一次 16 位读（小端：低字节 = `+0x2B688`、
//: 高字节 = `+0x2B689`），走访问层那道可读判定。
bool ReadContinueAvailable(std::uintptr_t manager, bool* out) {
    if (out == nullptr || manager == 0) {
        return false;
    }
    std::uint16_t bytes = 0;
    if (!engine_memory::ReadField(manager, kManagerContinueAvailableOffset, &bytes,
                                  &engine_memory::EngineMemoryReadable, 0)) {
        return false;
    }
    *out = (bytes & 0xFFU) != 0U || (bytes >> 8) != 0U;
    return true;
}

//: 每帧推进"我们那一格的导航"，并把引擎的**行号**写回 `页面+0x4`。
//:
//: 我们写、引擎也写 —— 但每帧都由我们覆盖一次，所以引擎自己的那次移动不会累积成两格。
void ModRowUpdate(const TargetModule& module, const ActionQueryFn query) {
    const std::uintptr_t page = g_Menu.menuManager + kMenuGamePageOffsetInMenuManager;
    // ★★ 批次 159（2026-09-27）：**先问引擎"继续游戏现在可不可选"**，再动光标。
    //   为什么不问就会出事：引擎自己会在"没有可继续的局"时跳过那一项（它把行图设成灰帧），
    //   而这一列是**我们**驱动光标的 ⇒ 不照抄这条规则，光标就能停在灰掉的"继续游戏"上；
    //   我们每帧又把行号 1 写回 `页面+0x4`，而引擎的确认分支（`0x40D73C`）读到的正是它
    //   ⇒ 直接走"载入存档"那条路、无存档 ⇒ **进局即死**（用户真机报的就是这个）。
    //   读不到就按"可选"处理（宁可保持旧行为，也不把用户锁在"继续游戏"外面），并记成
    //   `[62] = 2` 让读数里一眼看得出来。
    bool continueAvailable = true;
    const bool continueKnown = ReadContinueAvailable(g_Menu.manager, &continueAvailable);
    if (!continueKnown) {
        continueAvailable = true;
    }
    g_ModMenuState.continueAvailable = continueKnown ? (continueAvailable ? 1U : 0U) : 2U;
    // 第一次进入那一屏：按引擎的**现有**行号初始化我们的格子（引擎行 e ≥ 3 对应我们的 e+1，
    // 因为我们插进去的那一格占了引擎原来的第 4 格）。
    // ★ 例外：**从模组页回来**时不换算，直接回到我们那一格（理由见 `g_RestoreOurs`）。
    if (g_SlotInit == 0) {
        if (g_RestoreOurs != 0) {
            g_RestoreOurs = 0;
            g_Slot = isaac::runtime::kModEntrySlot;
        } else {
            std::uint32_t engineIndex = 0;
            (void)engine_memory::ReadField(page, kPageSelectedIndexOffset, &engineIndex,
                                           &engine_memory::EngineMemoryReadable, 0);
            g_Slot = engineIndex < isaac::runtime::kModEntrySlot ? engineIndex : engineIndex + 1;
            if (g_Slot >= isaac::runtime::kMenuGameEntryCount) {
                g_Slot = isaac::runtime::kMenuGameEntryCount - 1;
            }
        }
        // 保险：引擎本来不会停在不可选的那一项上（它自己会拨回 0），但我们不靠它。
        if (!isaac::runtime::SlotSelectableByEngine(g_Slot, continueAvailable)) {
            g_Slot = 0;
        }
        g_SlotInit = 1;
    }
    if (query != nullptr) {
        const bool up = HeldByAnyone(query, kActionUp);
        const bool down = HeldByAnyone(query, kActionDown);
        const bool confirm = HeldByAnyone(query, kActionConfirm);
        if (Edge(&g_LastUp, up)) {
            // `AdvanceSlot` = 不跳过（历史口径，只用来判"这一次有没有真的跳过"）。
            const std::uint32_t plain = isaac::runtime::AdvanceSlot(g_Slot, false);
            g_Slot = isaac::runtime::AdvanceSlotSkipping(g_Slot, false, continueAvailable);
            if (g_Slot != plain) {
                ++g_ModMenuState.continueSkipped;
            }
        }
        if (Edge(&g_LastDown, down)) {
            const std::uint32_t plain = isaac::runtime::AdvanceSlot(g_Slot, true);
            g_Slot = isaac::runtime::AdvanceSlotSkipping(g_Slot, true, continueAvailable);
            if (g_Slot != plain) {
                ++g_ModMenuState.continueSkipped;
            }
        }
        if (Edge(&g_LastConfirm, confirm)) {
            if (g_Slot == isaac::runtime::kModEntrySlot) {
                ++g_ModMenuState.confirmOnOurs;
                // ★ **在我们那一格按确认 = 进模组页**（引擎状态 16）。为什么必须在这里
                //   （我们的更新回调里）就把状态切掉、而不是"等引擎自己处理"：本回调跑在引擎
                //   `Manager::Update` **之前**，而引擎那一帧还会读一次同一个动作
                //   （`Menu_Game::Update` 的确认分支）。我们那一格写回给引擎的行号是 3
                //   （= 统计那一行）⇒ 引擎会 `SetState(9)`。**先切成 16**，引擎本帧的分派表
                //   （`cmp w8,#0xf`）就不会再去叫 `Menu_Game::Update` 了 ——
                //   这一下同时完成了"进页面"和"吃掉那次确认"。
                EnterModsPage(module, query);
            }
            // 其余格子**什么都不做**：让引擎自己处理它那五格。
        }
    }
    // ★★ 写回给引擎的是**行号**（`EngineRowForSlot`），不是"把格子号夹一下" —— 2026-09-23 修正。
    //
    // 用户实测："统计和选项按了**都是设置**"。原因就在这一句：引擎的确认跳表按**它的行号**查
    // （行 3 = 统计 ⇒ `SetState(9)`；行 4 = 选项 ⇒ `SetState(10)`），而我们那一列是插过一格的
    // ⇒ 视觉上的"统计数据"（我们的第 4 格）在引擎那里必须是**行 3**。
    // 用 `EngineIndexClampedForSlot`（把格子号夹到 0..4）会把第 4 格写成 4 ⇒ 引擎认为选中的是
    // "选项" ⇒ 于是"统计按了是设置"。
    // 现在的映射（与 `EngineRowForSlot` 一致）：0/1/2 ⇒ 0/1/2、**3 与 4 ⇒ 3**、5 ⇒ 4。
    // 我们那一格（3）借用的就是行 3（统计）⇒ "按了模组却会走到统计"仍要靠**我们自己的接管**拦，
    // 以及 `SetState` 中继那道保险兜底。
    // 再夹一次上界：`EngineRowForSlot` 对非法格子返回的是"引擎行数"（越界值）⇒ 必须夹回 0..4。
    const std::uint32_t row = isaac::runtime::EngineRowForSlot(g_Slot);
    const std::uint32_t clampedRow =
        row < isaac::runtime::kMenuGameEngineEntryCount ? row
                                                        : isaac::runtime::kMenuGameEngineEntryCount - 1;
    // ★★ 批次 159：夹完之后还有**最后一道保险** —— 引擎说"继续游戏"不可选时，写回去的行号
    //   **绝不为 1**（引擎的确认分支读的就是这一格；写 1 = 走"载入存档"那条路 ⇒ 无存档时
    //   进局即死，用户真机报的就是这个）。这一句走宿主机可测的纯算术，不在这里现算。
    const std::uint32_t clamped =
        isaac::runtime::GuardContinueRowForWrite(clampedRow, continueAvailable);
    // 写回引擎：**必须**先过"可写"判定 —— 这一处每帧都写引擎的页面对象，
    // 正是"无守卫的写把内存写坏"那类事故的形状。
    (void)engine_memory::WriteField(page, kPageSelectedIndexOffset, clamped,
                                    &engine_memory::EngineMemoryWritable, 0);
    g_ModMenuState.slot = g_Slot;
    g_ModMenuState.engineIndex = clamped;
}

//: 一次性核对我们要**直接调用**的那些引擎入口（安装时做，模块初始化线程）。
//:
//: ★ 批次 108 起，这里每一条都是"解析 + 核对 + 转成可调用签名"一步（`VerifiedEntry`），
//:   三件事全在**引擎调用层**；调用点里不再出现 `reinterpret_cast<Context::XxxFn>`。
//:   `ok` 的**累积语义一个字没改**：任一条核对不过，后面的入口一律拿不到（`nullptr`）。
void VerifyEntries(const TargetModule& module) {
    bool ok = true;
    g_Menu.modsCtor = VerifiedEntry<Context::CtorFn>(module, kMenuModsCtorOffset,
                                                     kMenuModsCtorExpected, &ok);
    g_Menu.modsInit = VerifiedEntry<Context::InitFn>(module, kMenuModsInitOffset,
                                                     kMenuModsInitExpected, &ok);
    g_Menu.modsRender = VerifiedEntry<Context::RenderFn>(module, kMenuModsRenderOffset,
                                                         kMenuModsRenderExpected, &ok);
    g_Menu.modsReset = VerifiedEntry<Context::ResetFn>(module, kMenuModsResetOffset,
                                                       kMenuModsResetExpected, &ok);
    g_Menu.setModsOffset = VerifiedEntry<Context::SetModsOffsetFn>(module, kSetModsOffsetOffset,
                                                                   kSetModsOffsetExpected, &ok);
    // 换语言那三下（引擎 `PerformLanguageSwitch` 对每个页面做的同一套动作）。
    g_Menu.modsPreLanguageSwitch =
        VerifiedEntry<Context::PageHookFn>(module, kMenuModsPreLanguageSwitchOffset,
                                           kMenuModsPreLanguageSwitchExpected, &ok);
    g_Menu.modsPostLanguageSwitch =
        VerifiedEntry<Context::PageHookFn>(module, kMenuModsPostLanguageSwitchOffset,
                                           kMenuModsPostLanguageSwitchExpected, &ok);
    g_Menu.freeUnreferencedImages =
        VerifiedEntry<Context::AnmCacheFreeFn>(module, kAnmCacheFreeUnreferencedImagesOffset,
                                               kAnmCacheFreeUnreferencedImagesExpected, &ok);
    g_Menu.freeUnreferencedEntries =
        VerifiedEntry<Context::AnmCacheFreeFn>(module, kAnmCacheFreeUnreferencedEntriesOffset,
                                               kAnmCacheFreeUnreferencedEntriesExpected, &ok);
    g_Menu.getLayer = VerifiedEntry<Context::GetLayerFn>(module, kAnm2GetLayerStubOffset,
                                                         kAnm2GetLayerStubExpected, &ok);
    g_Menu.setLayerFrame = VerifiedEntry<Context::SetLayerFrameFn>(
        module, kAnm2SetLayerFrameStubOffset, kAnm2SetLayerFrameStubExpected, &ok);
    g_Menu.drawText = VerifiedEntry<Context::DrawTextFn>(
        module, kFontDrawStringScaledUTF8Offset, kFontDrawStringScaledUTF8ExpectedBytes, &ok);
    g_Menu.lineHeight = VerifiedEntry<Context::FontLineHeightFn>(
        module, kFontGetLineHeightOffset, kFontGetLineHeightExpectedBytes, &ok);
    // ★ 这里**故意没有** `Font::Load` / `IsLoaded` 两段：本批撤掉了换字体那段接线
    //   （真机结论：那一页按字节画字，换字体救不了中文；见文件上半部分那段注释）。
    g_Menu.getLanguageCode = VerifiedEntry<Context::GetLanguageCodeFn>(
        module, kManagerGetLanguageCodeOffset, kManagerGetLanguageCodeExpectedBytes, &ok);
    g_Menu.entryGuardState = ok ? 1U : 2U;
    if (!ok) {
        // 逐字节不符 ⇒ **一个字节都不写、一次都不调用**（绝不盲目跳地址）。
        g_ModMenuState.failure = kFailureMenuModsGuard;
    }
}

}  // namespace

// ─────────────────────────────────────────────────────────────────────────────
// 三个入口中继的回调
//
// 形状：入口桩是**尾调用**（`br x16`），所以回调以目标函数的身份运行、`ret` 直接回到游戏的
// 调用方 ⇒ ABI 必须与目标一致（`(this)` / `(this, int)`），返回 void。
// ─────────────────────────────────────────────────────────────────────────────

//: `Menu_Game::Render`：那一列里多一格「模组」。
//:
//: 顺序（**先挪行、再让引擎画、再还原**）：
//:   1) 按生成表挪每一行（插点以上上移、STATS 下移、OPTIONS 几乎不动；X 也照搬 PC）；
//:   2) 光标：按格子设帧 + 加我们自己的 Y 偏移；
//:   3) 跑原函数（它画的是"已经挪好的"5 行，**以及我们补回去的那一层**）；
//:   4) 把光标与行偏移都还原（不还原会随帧累积）；
//:   5) 只有在"引擎那份动画里没有我们那一层"时，才由我们兜底画。
extern "C" void EntryRelayMenuGameRenderCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original =
        isaac::runtime::Original<RenderFn>(isaac::runtime::HookId::MenuGameRender);
    if (original == nullptr) {
        return;
    }
    // 门控：只有"就在选择界面那一格"时才干活；其余时刻**纯透传**（与没挂钩逐帧等价）。
    const bool active = g_Menu.menuState == kGameMenuState && self != nullptr;
    if (!active) {
        original(self);
        return;
    }
    const auto anm2 = engine_memory::AddressOf(self) + kPageAnm2Offset;
    // ★ 那一行现在是**引擎自己那份菜单动画里的一层**（补层工具把 PC 的 `Item6` 补了回去）。
    //   有这一层 ⇒ 引擎在这次 `original(self)` 里就把它画了，我们**不许再画一遍**
    //   （画了就是两层叠在一起）。没有这一层（覆盖层没装/被回退）⇒ 由我们兜底。
    const bool nativeLayer = HasNativeLayer(anm2);
    ShiftRows(anm2, 1.0F);
    PlaceCursor(anm2, 1.0F);  // 设帧 + 给光标一个我们自己的 Y 偏移
    original(self);
    PlaceCursor(anm2, -1.0F);
    ShiftRows(anm2, -1.0F);
    if (nativeLayer) {
        return;  // ★ 有那一层就绝不再画
    }
    ++g_ModMenuState.rowFallbackFrames;
    if (DrawRowLabel(engine_memory::AddressOf(self))) {
        ++g_ModMenuState.rowDrawFrames;
    }
    // ★ 这里**不清失败码**（探针批次 061 的教训）：每帧写 0 会让"守卫没过"这种真失败
    //   在读数里显示成"没有失败"，白花一轮真机才定位。
}

//: `Menu_Title::Render`：模组页（状态 16）的**唯一**画手。
//:
//: 为什么借这一趟：`MenuManager::Render` 在调各页 `Render` **之前**先做了一整套准备
//: （`PushRenderTarget` → `SetRenderTargetTexture` → `Clear` → `SetBlendMode` → `LoadShader`
//: → 背景 `FillQuad`），**然后**才调 `Menu_Title::Render`。而引擎的渲染清单里**没有**模组页
//: ⇒ 我们只能在别人的渲染上下文里画，这一趟是唯一能用的。
//:
//: 顺序（先跑原函数，再画我们的页）：这样我们的页画在标题菜单**之上**，而且 `MenuManager::Render`
//: 后续那十几个页面的 `Render` 大多会因自己的可见位是 0 而整页跳过（各页自带门控）。
extern "C" void EntryRelayMenuTitleRenderCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original =
        isaac::runtime::Original<RenderFn>(isaac::runtime::HookId::MenuTitleRender);
    if (original != nullptr) {
        original(self);  // 1) 标题菜单照常画（与没挂钩时逐帧等价）
    }
    // 2) 紧接着，在**同一渲染上下文**里画我们的原生页。
    if (g_Menu.pageInitState != kInitOk || g_Menu.modsRender == nullptr) {
        return;
    }
    // ⚠️ 必须自己门控状态：`MenuManager::Render` 每帧无条件调所有页面，`Menu_Title::Render`
    // 自身没有状态判断 ⇒ 不门控的话"切到存档界面也照画"。
    // 只有状态 16 才画（引擎的渲染清单里没有模组页 ⇒ 这一帧就是那个页面的唯一画手）。
    if (!isaac::runtime::ModPageIsActive(g_Menu.menuState)) {
        return;
    }
    // ★ 批次 169：**不再有"第一帧不画"** —— 位置在 `Init` 时就定死了（引擎那套模型：
    //   位置是 `Init` 的入参、之后谁都不改），所以第一帧就可以按正确位置画。
    g_Menu.modsRender(g_ModsObject);
    // ★★ 批次 170：**照引擎原样补一次滚动调用**。
    //   引擎 `Menu_Mods::Render` 收尾那次 `SetModsOffset(选中项)` 是**有条件**跳过的
    //   （`0x410BCC` 的 `b.ne 0x410C24` 直接跳到函数收尾，`0x410BEC` 那次调用根本没执行）——
    //   在我们这套"手工建页面 + 借标题页渲染"的形状下它从来没被调到 ⇒ 那一格永远停在 `Init`
    //   时写的确定值 ⇒ 画布不动 ⇒ **完全没有滚动**（用户 2026-09-27 实测）。
    //   ⇒ 用**引擎自己的函数、引擎自己的实参**（选中项）补这一次，**不自己算滚动量、
    //   不写页面位置、不加任何校正**（那三样正是 163~167 越改越糟的来源）。
    // ★★ 为什么不是"直接调引擎的 `SetModsOffset`"：它读的行数是**我们这张表**（比 PC 多一行），
    //   套进它自己的公式会退化成"永远不滚"（详见 `mod_page_nav.hpp` 那段）。所以我们**按 PC 口径
    //   求同一条公式**，把结果写进引擎那一格 —— 值与 PC 对同一份模组清单逐值一致。
    //   仍然**不碰页面位置、不做任何校正**（169 已把那两样删掉）。
    if (g_Menu.menuManager != 0) {
        const std::uint32_t consoleRow = kConsoleRowEntryIndex;
        std::uint32_t rows = 0;
        if (g_ModMenuState.selectedEntry != consoleRow && g_ModMenuState.entryCount > consoleRow) {
            rows = isaac::runtime::ModPageScrollRows(g_ModMenuState.selectedEntry - consoleRow,
                                                     g_ModMenuState.entryCount - consoleRow);
        }
        const float slotY = isaac::runtime::ModPageScrollSlotY(static_cast<std::int32_t>(rows));
        (void)engine_memory::WriteField(g_Menu.menuManager,
                                        isaac::runtime::kMenuManagerModsScrollY, slotY,
                                        &engine_memory::EngineMemoryWritable, 0);
        const std::uint8_t moving = 1;
        (void)engine_memory::WriteField(g_Menu.menuManager,
                                        isaac::runtime::kMenuManagerMovingFlagOffset, moving,
                                        &engine_memory::EngineMemoryWritable, 0);
    }
    // ★ 批次 126：这里**不再**额外画任何东西 —— 控制台开关那一行现在是条目表里的下标 0，
    //   引擎的 `Menu_Mods::Render` 会连它一起画（含它自己的选中高亮）。
}

//: `MenuManager::SetState`：**我们那一格的确认只归我们管**（保险）。
//:
//: 为什么加它（用户 2026-09-22 实测反馈）：在「模组」那一格按确认**跳到了统计页面** ——
//: 我们那一格借用引擎行号 3（= 统计那一行），而我们的接管一旦中途退出，引擎本帧就会拿行号 3
//: 去 `SetState(9)`（统计）。**页面上"跳错页"比"什么都不发生"更难解释**，所以再加一道保险。
extern "C" void EntryRelayMenuManagerSetStateCallback(void* self, std::int32_t state) {
    using SetStateFn = void (*)(void*, std::int32_t);
    const auto original =
        isaac::runtime::Original<SetStateFn>(isaac::runtime::HookId::MenuManagerSetState);
    if (original == nullptr) {
        return;
    }
    // 挡下来要同时满足三条：
    //   ① 当前就在"选择界面"（状态 3）；
    //   ② **我们的光标正停在自己那一格**（格子号 3）—— "统计数据/选项"那两行在我们这边是
    //      第 4/5 格，所以用户真去选它们时这一条不成立，**不会误伤**；
    //   ③ 引擎要去的正是"我们那一格之后"的那两页（统计 9 / 选项 10）——它按行号 3/4 的推断。
    if (g_Slot == isaac::runtime::kModEntrySlot && g_Menu.menuState == kGameMenuState &&
        (static_cast<std::uint32_t>(state) == kStatsState ||
         static_cast<std::uint32_t>(state) == kOptionsState)) {
        ++g_ModMenuState.setStateSwallowed;
        return;  // 不调原函数 ⇒ 状态不变
    }
    original(self, state);
}

namespace isaac::runtime::modmenu {

void ModMenuNativeInstall(const TargetModule& module) noexcept {
    g_ModMenuState.armed = 1;
    // 三个入口中继是**挂点登记表**装的（`HookInstallService` 按 `kHookCatalog` 逐个装）⇒
    // 这里只把"装没装上"记进状态面 [1]。判据用挂点记下的回退入口是否非空：
    // 装上了就一定有回退入口（入口被改写成跳转，原函数只能从槽里取）。
    std::uint32_t bits = 0;
    if (isaac::runtime::Original<void (*)(void*)>(HookId::MenuGameRender) != nullptr) {
        bits |= 1U << 0;
    }
    if (isaac::runtime::Original<void (*)(void*)>(HookId::MenuTitleRender) != nullptr) {
        bits |= 1U << 1;
    }
    if (isaac::runtime::Original<void (*)(void*, std::int32_t)>(HookId::MenuManagerSetState) !=
        nullptr) {
        bits |= 1U << 2;
    }
    g_ModMenuState.relayInstalled = bits;
    // ★★ 批次 117：局内单向闩锁**要不要启用**，判据是 `GameExit` 挂点装上了没有。
    //   为什么必须有这条降级（而不是无条件启用）：`GameStart` 是 `Game::Start` **返回之后**
    //   才回调我们的，而引擎那次写只读位在 `Game::Start` **体内** ⇒ 只靠它清零时，
    //   上一局留下的闩锁会渗进新局（真机现象 = "关着模组的新局照样不给成就"，
    //   正是用户最早报的形状）。`GameExit` 在退出流程一开始就触发，**严格早于下一局的
    //   任何写位**，能把那条路堵死。它缺失时宁可退回批次 107 的实时判据（比 PC 松），
    //   也不要出现"误锁"。这一格记在状态面 [50]，现场一眼看得出闩锁有没有被停用。
    NoteRunLatchArmed(
        isaac::runtime::Original<void (*)(void*, std::uint32_t)>(HookId::GameExit) != nullptr);
    // 一次性核对我们要直接调用的引擎入口（此处仍在模块初始化线程上、游戏主循环尚未开始）。
    VerifyEntries(module);
    // 条目来源那几条（读文件绑定 / 挂载解析 / 还内存的 delete[]）也在这里备好。
    PrepareSourceContext(module);
}

// ── 局内单向闩锁（2026-09-25 批次 117）─────────────────────────────────────────
//
// 设计与"为什么需要它"见 `.hpp` 的「局内单向闩锁」那一段。这里只写**谁改它**：
//   * 只有 `ObserveRunLatch` 能把它抬到 1（单向，条件成立过就一直 1）；
//   * 只有 `NoteNewRun` 能把它放回 0（局边界：离开一局 / 新开一局 / 读档）；
//   * **没有第三处**改它 —— "关掉模组之后仍然是 1"能成立，靠的全部机制就是这一条。
namespace {
bool g_RunLatchLatched = false;
bool g_RunLatchArmed = false;
//: 现在是不是**在一局里**（`GameStart` 之后、`GameExit` 之前）。由 `NoteNewRun` 按来源维护。
//: ★★ 为什么闩锁必须吃这一格（批次 118，117 的第一次真机读数暴露的缺陷）：
//:   开机后在**主菜单**上"开着模组 + 妈腿没解锁"同样成立，于是 117 的闩锁在菜单上就被置位了
//:   ⇒ "进局前把模组关掉"的那一局会被误锁，而用户开工单里的裁定①明确要求"不锁"。
//:   在菜单上"开着模组"什么都不代表 —— 它只是开关状态，不是"这一局用过模组"。
bool g_RunLatchInRun = false;
//: **留存**（批次 119）：出局那一刻闩锁是几。下一次"继续同一份存档"会把它接回来 ——
//: 用户的裁定是"继续同一份存档算同一局"，而他改开关的唯一途径就是退出到主菜单改
//: （模组页在一局里打不开）⇒ 不把污染留存下来，"中途开启后又关掉仍锁"就永远看不到。
bool g_RunLatchCarriedOver = false;
//: 出局时的留存**等着被接回**（下一次观察点会把它当成一次"0→1 边沿"）。
//: 为什么要等：接回来要有 `PersistentGameData*` 才能补写只读位，而"一条局边界到了"这件事
//: 是在 `GameStart` 中继里发生的（那里只有 `Game*`，没有持久数据指针）⇒ 交给下一帧的观察点。
bool g_RunLatchResumePending = false;
// ---- 批次 120：存档分区里那个"污染过"标记（用户裁定"比 PC 严"：跨重启也要保持）----
//
// 上面那颗闩锁只在内存里，**重启就没了**；用户要的是跨重启 ⇒ 落一个专属小文件
// （`isaac-runtime-run-taint.txt`，与 `isaac-switch-mods-state.txt` 同一种做法，不碰引擎的存档结构体）。
// 三个状态与两个"待办"：
//: 我们认为**文件里**现在是什么（`[56]`）：0 还不知道 / 1 污染过 / 2 干净。
std::uint32_t g_TaintFileState = 0;
//: 局边界要求"读一次文件"（"继续同一份存档"时要先知道上一局有没有污染过）。
//: ★ 由 `NoteNewRun(LoadSave)` 挂上，**在每帧的观察点里做掉**（那里是游戏线程）——
//:   绝不在开局中继里做 I/O（那时还在引擎的开局序列里，做 I/O 风险高）。
bool g_TaintFileReadPending = false;
//: 局边界要求"把文件写成某个值"（开新局 ⇒ 清掉；置位 ⇒ 写上 1）。
bool g_TaintFileWritePending = false;
bool g_TaintFileWriteValue = false;
}  // namespace

//: `[56]` 的取值口径（与 `.hpp` 那段是同一份）。
constexpr std::uint32_t kTaintFileUnknown = 0;
constexpr std::uint32_t kTaintFileTainted = 1;
constexpr std::uint32_t kTaintFileClean = 2;

//: 读那个文件，更新"我们认为它是几"。**只在游戏线程上调**（端口的实现自己也会拒绝别的线程）。
//:
//: 三条纪律（都来自 `run_taint_marker.hpp` 与 `mod_persistence.hpp` 的既有口径）：
//:   * 文件不存在 ⇒ **干净**（不是错误：第一次运行就是这样）；
//:   * 读失败 / 端口不可用 ⇒ 停在"还不知道"并**记一次失败**（`[57]`），**不置位**（fail-open）；
//:   * 读到"污染过" ⇒ 顺手把"待接回"挂上 —— 这就是**跨重启**那条路的入口（见 `.hpp` 的 [54] 段）。
void ReadRunTaintFile() noexcept {
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        ++g_ModMenuState.taintFileFailures;  // 端口还没接上：如实记，不静默
        return;
    }
    std::array<char, isaac::runtime::kRunTaintMaximumBytes + 64> text{};
    std::size_t bytes = 0;
    const isaac::runtime::Status status = storage->Read(
        isaac::runtime::kRunTaintFileName, text.data(), text.size(), &bytes);
    if (status.code() == isaac::runtime::StatusCode::NotFound) {
        g_TaintFileState = kTaintFileClean;
        return;
    }
    if (!status.ok() || bytes > text.size()) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    g_TaintFileState = isaac::runtime::ParseRunTaint(std::string_view(text.data(), bytes))
                           ? kTaintFileTainted
                           : kTaintFileClean;
    if (g_TaintFileState == kTaintFileTainted) {
        // 上一局（可能是上一次开机那一局）污染过 ⇒ 这一次"继续"也要把它接回来。
        g_RunLatchResumePending = true;
    }
}

//: 把标记写进那个文件（`tainted=true` 或 `false`）。成功/失败都记进 `[56]`/`[57]`，不静默。
void WriteRunTaintFile(bool tainted) noexcept {
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    std::array<char, isaac::runtime::kRunTaintMaximumBytes> text{};
    const std::size_t length =
        isaac::runtime::SerializeRunTaint(tainted, text.data(), text.size());
    if (length == 0) {
        ++g_ModMenuState.taintFileFailures;  // 放不下 ⇒ 不写半截（与端口的口径一致）
        return;
    }
    const isaac::runtime::Status status = storage->Write(
        isaac::runtime::kRunTaintFileName, std::string_view(text.data(), length));
    if (!status.ok()) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    g_TaintFileState = tainted ? kTaintFileTainted : kTaintFileClean;
}

//: 每帧一次：把局边界挂上的"读/写"做掉，并把 `[56]` 发布出去。
//: ★ 位置在 `UpdateAchievementDisallow` 的**最开头**（游戏线程、且与菜单/局内状态无关）。
void RunTaintFileTick() noexcept {
    if (g_TaintFileReadPending) {
        g_TaintFileReadPending = false;
        ReadRunTaintFile();
    }
    if (g_TaintFileWritePending) {
        g_TaintFileWritePending = false;
        WriteRunTaintFile(g_TaintFileWriteValue);
    }
    g_ModMenuState.taintFileState = g_TaintFileState;
}

bool ObserveRunLatch(bool conditionHolds) noexcept {
    if (!g_RunLatchArmed) {
        return false;  // 闩锁停用（`GameExit` 挂点缺席）⇒ 完全退回批次 107 的实时判据
    }
    if (!g_RunLatchInRun) {
        // 不在一局里 ⇒ **不观察**（菜单上的开关状态不代表"这一局开过模组"）。
        // 这一条是批次 118 加的：117 没有它，于是开机后在菜单上就置了位（真机读数 [45]=1
        // 而 [35] 从未被调到 ⇒ 还没进过任何一局）。
        return false;
    }
    if (g_RunLatchResumePending) {
        // ★★ 批次 119：**继续同一份存档** —— 把出局时留存的污染接回来，并**当成一次置位边沿**
        //    返回 true ⇒ 调用方（`UpdateAchievementDisallow`，那里拿得到持久数据指针）
        //    会**补写一次锁**。为什么必须补写：引擎那次开局写位发生在
        //    `Game::StartFromSavedState` **体内**，而我们把留存接回来是在它**返回之后**
        //    ⇒ 不补写就等于这一局没锁上（用户要的"中途开启后又关掉仍锁"就落不了地）。
        g_RunLatchResumePending = false;
        g_RunLatchLatched = true;
        g_ModMenuState.runLatch = 1;
        ++g_ModMenuState.runLatchSets;
        ++g_ModMenuState.runLatchResumes;
        return true;
    }
    const bool next = RunLatchNextState(conditionHolds, g_RunLatchLatched);
    if (next == g_RunLatchLatched) {
        return false;
    }
    g_RunLatchLatched = next;
    g_ModMenuState.runLatch = 1;
    ++g_ModMenuState.runLatchSets;
    return true;  // 0→1：调用方要**主动**把只读位写下去（那一局引擎不会再写它）
}

void NoteNewRun(RunBoundaryKind kind) noexcept {
    g_ModMenuState.runLatchResetSource = static_cast<std::uint32_t>(kind);
    // ★★ 三种局边界的处置**不同**（批次 119，用户裁定"继续同一份存档算同一局"）
    //    —— 这个映射只留在这里一处；放到调用点就会变成"三处各自记得"，
    //    而漂移的表现是"有时不锁、有时误锁"，最难查。
    switch (kind) {
        case RunBoundaryKind::GameExit:
            // 出局：把闩锁**留成留存**（而不是清成"这一份存档是干净的"）。
            // ★ 为什么不在出局时清掉：用户能改开关的唯一时机就是出局之后，
            //   清了就永远看不到"中途开启后又关掉仍锁"。
            g_RunLatchCarriedOver = g_RunLatchLatched;
            g_RunLatchResumePending = false;
            g_RunLatchInRun = false;
            break;
        case RunBoundaryKind::LoadSave:
            // 继续同一份存档 = **同一局** ⇒ 把留存接回来（下一帧观察点会补写一次锁）。
            // ★ 留存接回之后就消费掉：下一次出局会按那一刻的闩锁重新留存。
            g_RunLatchResumePending = g_RunLatchCarriedOver;
            g_RunLatchCarriedOver = false;
            g_RunLatchInRun = true;
            // ★★ 批次 120：**还要问一次存档分区里那个文件** —— 跨重启就靠它：
            //    上一次开机那一局污染过的话，内存里已经没有留存了，只有文件知道。
            //    I/O 挂到"待办"、由下一帧的观察点做（绝不在这个中继里做）。
            g_TaintFileReadPending = true;
            break;
        case RunBoundaryKind::NewRun:
        default:
            // 开新局：**真正清掉**（含留存）—— 裁定①：进局前关掉模组 ⇒ 这一局不锁。
            // ★ 必须连留存一起清：开新局那次写只读位发生在 `Game::Start` 体内、
            //   早于这条通知 ⇒ 留存不清就会把新局**误锁**。
            g_RunLatchCarriedOver = false;
            g_RunLatchResumePending = false;
            g_RunLatchInRun = true;
            // ★★ 批次 120：新局是"污染"的**终点** ⇒ 把存档分区里那个标记也清掉。
            //    写失败不致命（下次开新局还会试），但**必须记进 `[57]`**，不许静默。
            g_TaintFileWritePending = true;
            g_TaintFileWriteValue = false;
            break;
    }
    if (kind != RunBoundaryKind::LoadSave) {
        // "把闩锁归 0"这件事只在出局与开新局发生（继续那一支不清，它只是把留存接回来）。
        g_RunLatchLatched = false;
        g_ModMenuState.runLatch = 0;
        ++g_ModMenuState.runLatchResets;
    }
    g_ModMenuState.runLatchCarriedOver = g_RunLatchCarriedOver ? 1U : 0U;
    g_ModMenuState.runInProgress = g_RunLatchInRun ? 1U : 0U;
}

bool RunLatchLatched() noexcept { return g_RunLatchLatched; }

void NoteRunLatchArmed(bool armed) noexcept {
    g_RunLatchArmed = armed;
    g_ModMenuState.runLatchArmed = armed ? 1U : 0U;
    if (!armed) {
        g_RunLatchLatched = false;
        // 停用时把留存与"待接回"一起清掉：它们只在闩锁生效时才有意义，
        // 留着会让下一次误判（"为什么 [54] 是 1 而什么都不锁"）。
        g_RunLatchCarriedOver = false;
        g_RunLatchResumePending = false;
        g_ModMenuState.runLatch = 0;
        g_ModMenuState.runLatchCarriedOver = 0;
    }
}

//: 主动把"本局不给成就"那一位写下去（批次 117 的**边沿动作**）。
//:
//: 为什么必须走引擎自己的 `SetReadOnly`、而不是直接写 `PersistentGameData+0x1`：
//:   ① 那是全镜像**唯一**写它的地方（098 的取证），跟着它走 = 跟着引擎的既有约定；
//:   ② 098 的纪律钉着"我们不许把那个偏移当写目标"（门禁按 `kPersistentReadOnlyOffset,`
//:      这个形状判），直接写会红，而且会绕开引擎自己的记账。
//: 拿不到回退入口 ⇒ **什么都不做**：与中继里那条降级同方向（宁可不禁，也不误禁）。
//:
//: ★ 批次 118：加了两格记账（`[52]` 试了几次 / `[53]` 结果）。为什么非加不可 ——
//:   117 的第一次真机读数里"闩锁置位过 1 次、可只读位读出来还是 0"，
//:   而当时**没有任何格子**能分清"没写进去"与"写进去了又被清掉"，
//:   于是只能靠推断。现在写完**当场读回**，把这件事变成一条可以直接看见的事实。
constexpr std::uint32_t kEdgeWriteVerified = 1;    // [53] 写了、且写后读回确认是 1
constexpr std::uint32_t kEdgeWriteNoOriginal = 2;  // [53] 拿不到回退入口 ⇒ 什么都没写
constexpr std::uint32_t kEdgeWriteNotVisible = 3;  // [53] 写了但读回**不是 1**

void WriteAchievementReadOnly(void* persistentGameData) noexcept {
    using SetReadOnlyFn = void (*)(void*, bool);
    ++g_ModMenuState.runLatchEdgeWrites;
    const auto original = isaac::runtime::Original<SetReadOnlyFn>(
        isaac::runtime::HookId::PersistentGameDataSetReadOnly);
    if (original == nullptr) {
        g_ModMenuState.runLatchEdgeWriteResult = kEdgeWriteNoOriginal;
        return;
    }
    original(persistentGameData, true);
    // 写完当场读回（写法上先算地址、再用 `ReadAt`，理由见上面 ② 那条：别让门禁把这一句
    // 当成"写目标"）。
    const std::uintptr_t address =
        engine_memory::AddressOf(persistentGameData) + kPersistentReadOnlyOffset;
    std::uint8_t value = 0;
    const bool readBackOk =
        engine_memory::ReadAt(address, &value, &engine_memory::EngineMemoryReadable);
    g_ModMenuState.runLatchEdgeWriteResult =
        (readBackOk && value != 0) ? kEdgeWriteVerified : kEdgeWriteNotVisible;
}

bool AchievementsShouldBeBlockedFor(void* persistentGameData) noexcept {
    // ★★ 2026-09-25 批次 117：**先看局内单向闩锁** —— 本局里出现过"开着模组 且 妈腿未解锁"
    //    就一直锁，之后把模组关掉也**不解除**（用户要的语义，见 `.hpp` 那段）。
    //    ★ 下面那套实时口径保留，作为"闩锁还没被置位时"的答案：引擎开局那次调用正落在这一支上
    //    （因此"刚清完零"这一瞬不会漏判），而"中途开启模组"由每帧观察点置位后再由这里短接。
    if (RunLatchLatched()) {
        return true;
    }
    // 规则 = PC 的 `ModManager::AchievementsLocked()` **一比一**（2026-09-24 批次 098 取证；
    // 逐条反汇编见 `runtime_constants.hpp` 的 `SetReadOnly` 那一段）：
    //   ① 模组列表为空 ⇒ 不锁；
    //   ② 任一模组启用 ⇒ 读 `PersistentGameData::Unlocked(4)` 取反
    //      ⇒ 「有模组开着 且 成就 #4（打过妈妈）未解锁」= 锁。
    //
    // ★ ① 用**处于"启用状态"**的真实模组数（`ModMenuEnabledCount()`；口径 = 模组页开关那一份，
    //   与页面上看到的一致，**不看有没有重启**）。
    //   ★★ 2026-09-24 批次 107 改成这一条（用户实测后裁定"按 PC 口径"）：原来的口径是
    //   `ModMenuActiveCount()`（**本局开机时真的加载了几个**），而模组是**开机那一刻**按
    //   存档里的开关过滤后加载的 ⇒ "开关开了但还没重启就进局"时它是 0 ⇒ **漏判**
    //   （真机实测：开着模组进局却照样给成就）。PC 的 `ModManager::AchievementsLocked()`
    //   走的是**列表里每一项的启用位**，界面上一开就变、不需要重启 ⇒ 那才是 PC 语义。
    //   ⇒ 顺带也是对的：**开关关掉**（哪怕本局还加载着）⇒ 不锁，与 PC 一致。
    //   （097 之前那种 fail-closed"发现没出结果就按有模组算"仍然不许回来：那是我们自创的，
    //    会在开机那几秒把**该给的**成就也吞掉。）
    if (isaac::runtime::ModMenuEnabledCount() == 0) {
        return false;
    }
    // ★ 这里**不看**是哪一个成就（批次 096 撤掉 093 给 #4 开的豁免）：妈腿成就本身也不豁免 ——
    //   关掉模组之后本函数一律返回 false，所以不会锁死。
    // ② 打过妈妈没：**直接读持久位**（`PersistentGameData+0x28+成就号`，成就 #4 = 打过妈妈）。
    //    拿不到持久数据 ⇒ 按"没打过"（= 锁）—— 与 PC 同方向（读不到存档也不会放行成就）。
    if (persistentGameData == nullptr) {
        return true;
    }
    std::uint8_t wombByte = 0;
    if (!engine_memory::ReadField(
            engine_memory::AddressOf(persistentGameData),
            kPersistentAchievementArrayOffset + kAchievementWomb, &wombByte,
            &engine_memory::EngineMemoryReadable, 0)) {
        return true;  // 读不到 ⇒ 同"没打过"（= 锁）：与上面那条同方向
    }
    return wombByte == 0;
}

// ── 「开模组 ⇒ 禁成就」：**必须每帧都跑，而且在任何游戏状态下都要跑** ──────────────
//
// ★★ 为什么把它单独抽出来、并在 `ModMenuNativeUpdate` 的**最开头**调用
//    （2026-09-23 真机定位到的根因，这一条是整个"禁成就"一直不生效的原因）：
//
//    `ModMenuNativeUpdate` 里有一道**很早的早退** —— `g_MenuManager`（菜单管理器）
//    "随菜单生命周期出现/消失"（那行注释的原话），**读不到就直接 `return`**。
//    而**在一局游戏里菜单管理器根本不存在** ⇒ 那道早退会命中 ⇒ 原本放在它后面的
//    "写禁成就那两位"**一整局都不会执行**。
//    偏偏 `Game::Start` 是在**开局那一刻**把只读位清成 0 的（`SetReadOnly(false)`）
//    ⇒ 那一局从头到尾都允许成就 ⇒ 用户看到的"成就照样弹"。
//
//    真机读数正是这个形状：真内存 `Manager+0x36D4D = 1`（进局前写下的、没人清），
//    但 `PersistentGameData+0x1 = 0`（开局被清之后**再没写过**），
//    而状态面里那些"看起来对"的值全是**进局前**那一帧的旧值。
//
//    ⇒ 修法就是这一处：**把它挪到早退之前**，让它与菜单/局内状态无关地每帧执行。
void UpdateAchievementDisallow(const TargetModule& module) {
    // ★★ 批次 120：先做掉"局边界"挂上的存档分区 I/O（读/写那个"污染过"标记）。
    //   位置选在这里有两个理由：
    //     ① 这是**游戏线程**（端口的实现只允许游戏线程操作存档分区）；
    //     ② 它与菜单/局内状态无关 ⇒ 放在下面那道早退**之前**，不会被"菜单管理器不存在"挡住。
    RunTaintFileTick();
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kManagerSlotOffset, &manager) || manager == 0) {
        return;
    }
    g_Menu.manager = manager;
    // 「开模组 ⇒ 禁成就」的**查询结果**（读数用）—— 规则与 PC 的 `ModManager::AchievementsLocked()`
    // 一比一：**有真实模组实际加载** 且 成就 #4（打过妈妈）未解锁 ⇒ 该禁；其余一律不锁。
    // ★★ 2026-09-24 批次 098：这里**只算、只记**，一个引擎字节都不写 —— 真正落地在
    //    `SetReadOnly` 入口中继那一步（`hook_manager.cpp`）。闸门从 `TryUnlock` 挪到那里，
    //    因为 `TryUnlock` 只是**查**只读位，`SetReadOnly` 才是**写**它的地方（全镜像唯一）。
    // ★★ 2026-09-24 批次 107（用户裁定"按 PC 口径"）：判据从"**实际加载**的那批"改成
    //    "**处于启用状态**的那批"（`ModMenuEnabledCount`）—— 理由与实测见
    //    `AchievementsShouldBeBlockedFor` 里那一段。这一格同时记下**两个**数（启用 / 实际加载），
    //    因为"读不出到底是哪一种"正是上次定位时最费时间的地方。
    {
        // ★★ 2026-09-24 批次 107：这两格**必须分开记**（它们回答的是不同的问题，
        //    混成一个正是"开着模组进局却照样给成就"那次读不出来的原因）：
        //    * `enabledRealMods` = **处于启用状态**的（判据用的就是它，PC 口径）；
        //    * `activeRealMods`  = 本局**开机时真的加载了**几个（诊断用）。
        const auto active = static_cast<std::uint32_t>(isaac::runtime::ModMenuActiveCount());
        const auto enabled = static_cast<std::uint32_t>(isaac::runtime::ModMenuEnabledCount());
        g_Menu.activeRealMods = active;
        g_Menu.enabledRealMods = enabled;
        // ★ 批次 116：把"发现清单"的自证四格填上（见状态面 `.hpp` 的 [41]..[44]）。
        //   为什么非要有它们：上面那两个是**汇总数**，而待修记录里出现过"`[40] = 0` 但
        //   开关服务读不出来时本该默认全都开着"这种矛盾 —— 只看得汇总数分不出是
        //   "状态文件写着全禁用"、"清单是空的"，还是"发现这一步根本没跑到"，而这三者的处置不同。
        {
            const isaac::runtime::ModMenuDiscoveredReading discovered =
                isaac::runtime::ModMenuDiscoveredForReading();
            g_Menu.discoveredRealMods = discovered.count;
            g_Menu.discoveredEnabledMask = discovered.enabledMask;
            g_Menu.discoveredActiveMask = discovered.activeMask;
            g_Menu.discoveryDone = isaac::runtime::ModMenuDiscoveryDone() ? 1U : 0U;
        }
        bool wombUnlocked = false;
        // ★ 批次 117：把"成就那一段读到没有"提到外层 —— 闩锁的置位判据要**正面证据**
        //   （"读不到持久位"不能当成"没打过妈腿"去置位，那会变成 fail-closed：
        //   红线是"闩锁只许由正向证据置位"，见 `.hpp`）。
        bool achievementBitsOk = false;
        std::uint32_t achievementSample = 0;
        if (g_Menu.manager != 0) {
            // 一次读 8 个字节就够：抽样要 0..3，成就 #4（`kAchievementWomb`）落在同一个块里
            // （那个数组从 `PersistentGameData+0x28` 起、**按成就号逐字节索引**）。
            std::array<std::uint8_t, 8> bits{};
            achievementBitsOk = engine_memory::ReadField(
                g_Menu.manager,
                kManagerPersistentGameDataOffset + kPersistentAchievementArrayOffset, &bits,
                &engine_memory::EngineMemoryReadable, 0);
            // 抽样 0..3（读出来应当全是 0/1 —— 读数里用来自证"位置没读错"）。
            // ★ 读不到就全 0：读数里一眼看得出"这一段没读到"，比留着上一次的旧值不容易误读。
            achievementSample =
                achievementBitsOk ? (static_cast<std::uint32_t>(bits[0]) |
                                     (static_cast<std::uint32_t>(bits[1]) << 8) |
                                     (static_cast<std::uint32_t>(bits[2]) << 16) |
                                     (static_cast<std::uint32_t>(bits[3]) << 24))
                                  : 0U;
            wombUnlocked = achievementBitsOk && bits[kAchievementWomb] != 0;
        }
        g_Menu.achievementSample = achievementSample;
        g_Menu.wombAchievementUnlocked = wombUnlocked ? 1U : 0U;
        // ★★ 批次 117：**局内单向闩锁的每帧观察点**，同时也是"中途开启模组"那一下的**边沿写位点**。
        //
        // 为什么观察放在这里（而不是只放在中继里）：本次更新**在一局里也跑**（理由见本函数
        // 上方那段），而"玩家在局内把模组打开"这件事**只有在这里才看得到** ——
        // 引擎那次写只读位早在开局就发生过了（那 24 个调用点全在开局路径上），不会再来第二次。
        //
        // 判据（**只认正向证据**）：真实模组处于启用状态 **且** 成就那一段**确实读到了**
        // 且成就 #4 未解锁。读不到那一位时**不置位、也不写** —— 这既守住了"不许 fail-closed"
        // 的红线，也避免在开局头几帧（存档还没建好）把成就误锁。
        if (ObserveRunLatch(enabled != 0 && achievementBitsOk && !wombUnlocked)) {
            // 0→1 那一下：把只读位**主动**写下去。不写就等于"中途开启模组"这一局没生效
            // （引擎不会再写它，而中继只在引擎调用时才机会）。
            WriteAchievementReadOnly(engine_memory::AsObject(
                g_Menu.manager + kManagerPersistentGameDataOffset));
            // ★★ 批次 120：把这个"污染"记进**存档分区** —— 跨重启那条路就靠这个文件
            //    （内存里的闩锁/留存都会随重启消失）。文件里已经是"污染过"时不重复写：
            //    "继续"接回来的那一次正是这种情形（刚读过它就是 1）。
            if (g_TaintFileState != kTaintFileTainted) {
                WriteRunTaintFile(true);
            }
        }
        if (g_Menu.manager != 0) {
            // 只读位仍**被读**（它是现场真值，也是 `TryUnlock` 唯一查的东西）—— 但**不写**。
            // 写法上先算出地址再用 `ReadAt`：本文件那条门禁按 `kPersistentReadOnlyOffset,` 这个
            // 形状判"有没有人拿它当**写目标**"（写点必然把它当参数、后面跟逗号）—— 别改成那种形状。
            const std::uintptr_t readOnlyAddress =
                g_Menu.manager + kManagerPersistentGameDataOffset + kPersistentReadOnlyOffset;
            std::uint8_t readOnlyValue = 0;
            const bool readOnlyOk = engine_memory::ReadAt(readOnlyAddress, &readOnlyValue,
                                                          &engine_memory::EngineMemoryReadable);
            g_Menu.achievementsReadOnly = (readOnlyOk && readOnlyValue != 0) ? 1U : 0U;
            // ★★ 查出来的"该不该禁"必须与**判据本身**同一个口径 ——
            //    否则读数会告诉你"不该禁"，而闸门那边其实是按另一个数在判，等于读数说谎。
            //    ★ 批次 117 起那个口径里多了**闩锁**那一层（`RunLatchLatched()`）：本局里出现过
            //    "开着模组 且 妈腿未解锁"就一直是 1，所以"关了模组仍然该禁"这件事在读数里
            //    也看得见（否则现场会以为什么都没发生）。
            g_ModMenuState.achievementsDisallowed = static_cast<std::uint32_t>(
                (RunLatchLatched() || (enabled != 0 && !wombUnlocked)) ? 1U : 0U);
            // 这几格也**跟着每帧填**（不能留在函数尾部 —— 尾部在"一局里"根本不会执行，
            // 读数就会是进局前的旧值，这正是 2026-09-23 那几轮读不懂现场的原因之一）。
            g_ModMenuState.activeRealMods = g_Menu.activeRealMods;
            g_ModMenuState.enabledRealMods = g_Menu.enabledRealMods;
            // 批次 116：发现清单自证四格 —— 与上面两格**同一处发布**（分两处填必然漂）。
            g_ModMenuState.discoveredRealMods = g_Menu.discoveredRealMods;
            g_ModMenuState.discoveredEnabledMask = g_Menu.discoveredEnabledMask;
            g_ModMenuState.discoveredActiveMask = g_Menu.discoveredActiveMask;
            g_ModMenuState.discoveryDone = g_Menu.discoveryDone;
            g_ModMenuState.wombAchievementUnlocked = g_Menu.wombAchievementUnlocked;
            g_ModMenuState.achievementSample = g_Menu.achievementSample;
            g_ModMenuState.persistentReadOnly = g_Menu.achievementsReadOnly;
        }
    }
}

//: 批次 153：**在模组脚本执行之前**喂一次（由 `hook_manager.cpp` 在 `InitializeDefaultManifestMod`
//: 前一行调）。判据与理由见 `.hpp` 里那条声明 —— 一句话：模组是在自己 Lua 文件的**文件作用域**
//: 就把服装编号查成表的（PC 惯例），所以我们必须比它早。
void LoadEngineModRoomsAfterStage(void* config,int stage,int mode) noexcept {
    const auto base=LuaRuntime::EngineModuleBase();
    if(base==0 || !PrepareModRoomSources()) {++g_ModRoomLoadState[4];return;}
    std::uintptr_t owner=0,game=0;
    if(!engine_memory::ReadAt(base+kGameOwnerGlobalSlotOffset,&owner,engine_memory::EngineMemoryReadable) ||
       !owner || !engine_memory::ReadAt(owner,&game,engine_memory::EngineMemoryReadable) ||
       !game || engine_memory::AddressOf(config)!=game+mod_rooms::kGameRoomConfigOffset) {
        ++g_ModRoomLoadState[5];return;
    }
    if(mode==-1) {
        std::uint32_t difficulty=0;
        if(!engine_memory::ReadField(game,kGameDifficultyOffset,&difficulty,engine_memory::EngineMemoryReadable)) {
            ++g_ModRoomLoadState[5];return;
        }
        mode=(difficulty&~1U)==2U?1:0;
    }
    using Update=void (*)(void*,int,int);
    const auto update=engine_call::AsFunction<Update>(base+mod_rooms::kUpdateOffset);
    // 固定NRO仅访问ModManager的前三个vector槽，原读取/合并STB实现完整保留。
    struct View {void** begin;void** end;void** capacity;};
    View view{g_ModRoomSources.begin,g_ModRoomSources.end,g_ModRoomSources.capacity};
    update(&view,stage,mode);
    ++g_ModRoomLoadState[0];g_ModRoomLoadState[2]=static_cast<std::uint32_t>(stage);
    g_ModRoomLoadState[3]=static_cast<std::uint32_t>(mode);
}

void LoadEngineModContentBeforeModScripts() noexcept {
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        return;
    }
    // 1 = "模组脚本之前"（读数里靠这一格分辨"喂成功了但喂晚了"与"压根没喂"）。
    (void)LoadEngineModContent(*module, 1);
    // 即使没有自定义XML，也索引已由游戏加载的原生本体配置。
    static_cast<void>(isaac::runtime::RefreshRuntimeContentNames());
    // ★★ 批次 154：把**这一次**走到的阶段单独留一格（`[61]`）。
    //
    // 为什么必须单独留：`g_ModEngineScanStage` 会被后面的重试覆盖，于是"早期那次到底走到哪"
    // 读不出来 —— 而 2026-09-27 的崩溃正是"早期那次没喂成（或者喂成了又被抹掉）"，
    // 分不清这两种就不知道该修哪一边。这一格的值域与 `g_ModEngineScanStage` 相同
    // （1 = 两个入口已解析 / 2 = 全部走完 / 3 = 失败）。
    g_ModMenuState.modEngineEarlyStage = g_ModEngineScanStage;
}

//: 批次 154：**每帧那条路的重试** —— 不再依赖"用户打开模组页"。
//:
//: 为什么需要它（真机事故链）：模组的 `content/*.xml` 必须在**两个时刻之前**进引擎 ——
//:   ① 模组脚本执行之前（服装编号是模组在自己 Lua 文件的**文件作用域**就查好并固定的）；
//:   ② 模组第一次用那些编号之前（音乐编号是回调里**现查**的）。
//: 而"模组脚本之前"那个时机**不一定**已经能解析挂载路径 ⇒ 2026-09-27 用户按提示直接进局、
//: 没开模组页 ⇒ 模组的 `content/music.xml` 始终没进引擎 ⇒ 它拿到 `-1` 去 `Music::Play` ⇒
//: **进局瞬间崩**（`dist/crash-153-20260927-1121.log`）。
//: ⇒ 结论：**不许依赖任何单一时机**，每约 0.5 秒重试一次、最多 `kMaximumContentLoadAttempts` 次，
//: 直到两个容器任一涨起来（成功之后 `EngineModContentLoaded()` 立刻让它变成空转）。
//:
//: 安全性：调用点与"进模组页"那条**完全同类** —— 游戏线程、`Manager::Update` 帧里、走同一个
//: 入口（`LoadEngineModContent` 里有"涨过就不喂"的闸，所以不会重复加载同一条内容）。
void MaybeRetryEngineModContent(const TargetModule& module) noexcept {
    if (EngineModContentLoaded()) {
        return;
    }
    if (g_LastContentLoadFrame != 0 &&
        g_ModMenuState.drivenFrames - g_LastContentLoadFrame < kContentLoadRetryIntervalFrames) {
        return;
    }
    // 3 = "每帧重试"（读数里用它区分"早期那次没成、靠重试补上"与"早期那次就成了"）。
    (void)LoadEngineModContent(module, 3);
}

void ModMenuNativeUpdate() noexcept {
#if defined(EXL_DIAGNOSTIC_STAGE)
    // ★ 诊断阶段构建的行为**一个字都不变**（那些构建是别的调查在用的）：这里直接什么都不做
    // —— 连一次引擎读都不发生，与"调用点不调"完全等价。
    //
    // ★★ 为什么守卫放在**函数体开头**而不是 `hook_manager.cpp` 的调用点：
    // `runtime/tests/test_stage118_managed_file_write_diagnostic.py` 用
    // `#if !defined(EXL_DIAGNOSTIC_STAGE)` 当**切片结束符**去取 `ManagerUpdateHook::Callback`
    // 那一段（它要确认那里有一句"跑原函数"），在调用点再插一条同样的条件会让它切早、
    // 把那一句切出去 ⇒ 那条既有门禁会红（2026-09-23 批次 077 实测）。
    // 放这里效果相同、也不动别的门禁的解析口径 —— **别挪回调用点**。
    return;
#endif
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        g_ModMenuState.failure = kFailureModuleNotFound;
        return;
    }
    // ★★ 这两件事必须在**任何游戏状态下**都执行 —— 尤其"在一局里"（那时菜单管理器不存在，
    //    下面那道早退会命中）。理由见 `UpdateAchievementDisallow` 上方那段。
    UpdateAchievementDisallow(*module);
    ++g_ModMenuState.drivenFrames;  // [34] 每帧 +1：唯一能证明"我们还在跑"的一格
    NoteHeapUsagePeriodically();    // [58]/[59]：每 60 帧采一次堆余量（见那支注释）
    // ★★★ 批次 425→426：**把"Lua 的 GC 看不见的那笔内存"补给 GC 看**。
    // 为什么必须在这里做：模组在 `MC_POST_RENDER` 里每帧 `Font()` 一个对象、用完即弃，
    // 而那 128 KiB 的块走的是**裸 `frealloc`** ⇒ **不进 Lua 的用量统计** ⇒
    // GC 的触发判断**永远看不到它** ⇒ 攒到 500+ 块（63 MB）才被顺手收掉。
    // 详见 `lua_runtime_state.hpp` 里那段（含 415 那句前提的订正）。
    // ★ 位置：本函数是**每帧路径且不在 Lua 执行中**（GC 会跑终结器，安全点必须在这里）。
    // ★★ 426 订正：425 那版用**全量** `LUA_GCCOLLECT`，一秒一次 stop-the-world
    //   ⇒ 真机表现为**规律性掉帧**（"掉一下回 60、再掉一下"）。现在改成
    //   **按 1 ms 时间预算切片的增量步进**（见那个头文件里的说明）。
    // ★ 返回 1 = 这一拍真走了步进（读数用 `g_FontGcNudges` / `g_FontGcMicrosMax` 对账）。
    (void)LuaRuntime::NudgeLuaGcIfFontBlocksHigh(g_ModMenuState.drivenFrames,
                                                 isaac::runtime::FontStorageLiveBlocks());
    // ★★ 批次 154：把模组的 `content/` 喂给引擎 —— 直到成功为止（每约 0.5 秒一次，上限见常量）。
    // 放在这里（而不是只放在"模组脚本之前"那一刻）的理由见 `MaybeRetryEngineModContent`：
    // 那一个时机**不一定**已经能解析挂载路径，而 2026-09-27 的"进局瞬间崩"就是那样来的。
    // 必须在下面那道"菜单管理器读不到就 return"**早退之前** —— 在一局游戏里菜单管理器不存在，
    // 而"进局前把内容喂好"恰恰是最要紧的场景。
    MaybeRetryEngineModContent(*module);
    // `g_MenuManager` 是这一切的前置条件（它随菜单生命周期出现/消失）。
    std::uintptr_t menuManager = 0;
    if (!ReadSingleton(*module, kMenuManagerSlotOffset, &menuManager) || menuManager == 0) {
        g_SlotInit = 0;        // 离开菜单 ⇒ 下次进来重新取初值
        g_RestoreOurs = 0;     // 连菜单都离开了 ⇒ "回到我们那一格"这件事作废
        g_Menu.menuManager = 0;
        g_Menu.menuState = 0;
        g_Menu.pageWasActive = 0;
        return;
    }
    g_Menu.menuManager = menuManager;
    g_Menu.menuState = ReadMenuState(menuManager);
    // `g_Manager`（条目表与字体对象都在它里面）与可见屏幕尺寸：每帧顺手刷新。
    std::uintptr_t manager = 0;
    if (ReadSingleton(*module, kManagerSlotOffset, &manager)) {
        g_Menu.manager = manager;
    }
    RefreshScreenSize(*module);
    ResolveLanguage();
    // 语言变了 ⇒ 把模组页按新语言重载一次（贴图会跟着换；**排版的不足**见函数注释）。
    // ★ 放在这里（每帧更新、引擎 `Manager::Update` 之前）而不是渲染回调里：那一下会 `ANM2::Load`，
    //   不能在渲染批次中间动引擎对象。页面当前没显示时才会真的动手（见函数注释）。
    ReloadPageForLanguage(*module);

    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        g_ModMenuState.failure = kFailureInputUnavailable;
        return;
    }
    // 这个 thunk 是运行时自己解析好、记下来的（不是"模块基址 + 偏移"）⇒ 只需转换一次签名：
    // 走引擎调用层的 `AsFunction`（批次 108），调用点里不留 `reinterpret_cast`。
    const auto query = engine_call::AsFunction<ActionQueryFn>(thunk);

    // 页面的一次性 `ctor` + `Init`：**在菜单一出现时就做**（探针的"自动驱动"同一形状）。
    // 为什么要提前做而不是等用户按确认：条目表要**等发现结果**（最多 900 帧），而 `Init` 必须
    // 在表写好之后 —— 等到按键那一刻再做，用户会看到"按了没反应"。此处不在任何渲染批次中间，
    // 引擎建贴图/ANM2 的那些锁与状态都干净（避免重入）。
    if (g_Menu.pageInitState == kInitNotTried && TryPrepareModsVector()) {
        InitManualPage();
    }
    // 发现结果后来才到（启动扫描比菜单慢）：表只在"目录数变了"时重写一次。
    // ★ 这里**不重跑 `ctor`/`Init`**：页面对象已经建好（`Init` 会把 ANM2 载进来），重跑等于
    //   再加载一份。`Menu_Mods::Render` 每帧都从 `g_Manager+0x36800` 现读 begin/end ⇒
    //   换表立刻生效，不需要重建页面。
    if (g_Menu.vectorWritten != 0 &&
        g_Menu.writtenDirectories != isaac::runtime::ModMenuDiscoveredCount()) {
        g_Menu.vectorWritten = 0;
        g_Menu.prepareAttempts = 0;
        TryPrepareModsVector();
    }

    if (g_Menu.menuState == kGameMenuState) {
        ModRowUpdate(*module, query);
    } else {
        g_SlotInit = 0;  // 离开那一屏 ⇒ 下次进来重新按引擎行号取初值
    }
    // 模组页（状态 16）期间由我们驱动那一页。与上面同一时机 —— 都在引擎 `Manager::Update`
    // 之前，所以"我们这一帧切的状态"引擎这一帧就按新状态分派。
    ModsPageUpdate(*module, query);

    // 留证：本页**实际**被画的点（= 偏移 + 本页位置 + 200）。过渡期间它会动（纸跟着画布滑），
    // 停稳后应当是 (173, 72) ⇒ 读数里这一格就是"动画在不在动 / 摆对了没有"的直接证据。
    {
        float offset[2] = {0.0F, 0.0F};
        float page[2] = {0.0F, 0.0F};
        const bool observed =
            engine_memory::ReadField(menuManager, kMenuManagerCanvasOffset, &offset,
                                     &engine_memory::EngineMemoryReadable, 0) &&
            engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject), kPagePositionOffset,
                                     &page, &engine_memory::EngineMemoryReadable, 0);
        // 读不到就把这两格写成 0：那是个**一眼看得出不对**的值（正常是 (173, 72)），
        // 比留下上一次的旧值更不容易被当成"当前现场"。
        const float originX = observed ? offset[0] + page[0] + kModsRenderExtraX : 0.0F;
        const float originY = observed ? offset[1] + page[1] : 0.0F;
        std::memcpy(&g_ModMenuState.pageOriginX, &originX, sizeof(originX));
        std::memcpy(&g_ModMenuState.pageOriginY, &originY, sizeof(originY));
    }
    // ---- [22]..[25]：2026-09-23 定位"换语言后 EID 坏掉"用的观测（**只读**，不动引擎）----
    //
    // 为什么要这几格：那条 bug 的根因是"引擎重建挂载点表之后，我们没能把 Mod 的挂载点挂回去"
    // （`SetSessionContentMountService` 从来没被调用 ⇒ 中继拿不到实例）。有了这几格，
    // 真机读数就能直接回答"中继跑没跑、恢复成功没、字体为什么没装上"，不用再猜。
    g_ModMenuState.mountRelayFired =
        IsaacModRuntime_RebuildContentMountPointsRelayFiredCount();
    g_ModMenuState.mountRelayFailures =
        IsaacModRuntime_RebuildContentMountPointsRelayFailureCount();
    g_ModMenuState.mountServicePublished =
        isaac::runtime::SessionContentMountService() != nullptr ? 1U : 0U;
    g_ModMenuState.lastFontLoadWord = isaac::runtime::LastFontLoadWordForProbe();
    // [27]..[30]：`metadata.xml` 三种结果与"真实模组"个数（2026-09-23 批次 085）
    g_ModMenuState.metadataRootRelativeHits = g_Menu.metadataRootRelativeHits;
    g_ModMenuState.metadataPrefixedHits = g_Menu.metadataPrefixedHits;
    g_ModMenuState.metadataMisses = g_Menu.metadataMisses;
}

} // namespace isaac::runtime::modmenu
