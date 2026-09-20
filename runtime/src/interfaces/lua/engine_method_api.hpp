#pragma once

// ============================================================================
// "调用一个引擎方法"的数据行机制（架构整改第一批，2026-09-19）
// ============================================================================
//
// **问题（实测口径，见 `tools/runtime_budget_forecast.py`）**：
// 一条"调引擎方法"的 API 原本要写一份独立的 `lua_CFunction` + 一份入口守卫校验，
// 代码段 **≈490 字节**（其中守卫校验 **224**、handler 192–236、thunk 32），
// 而代码段只有 512 KiB、保留线 32 KiB。242 条目录行已经把它挤到只剩 32.3 KiB，
// 于是"想一次补 8 条 ⇒ 构建直接失败"。
//
// **做法**：与"字段读取型 API"（`field_api.hpp`，一条 16 字节数据、**0 字节代码**）完全同形 ——
// 把"不变的流程"提成**一个共享处理器**，每个 API 只剩一行数据：
//
//   1. 参数个数与类型校验（按 `argumentCount`）；
//   2. 从第 1 个参数解出接收者（复用字段那套 `FieldReceipt`）；
//   3. 用"模块基址 + 偏移 + 入口 4 字节指纹"解析引擎方法（偏移写错会调到别的函数，这一步不是可选项）；
//   4. 按 `shape` 调进去（有限几种 ABI，一个 switch 覆盖）；
//   5. 按 `shape` 的返回类型压回 Lua 栈。
//
// **怎么绑定**：`AttachOwnerMethods` 支持"带数据行的闭包"——把这一行作为上值
// （`lua_pushcclosure`）交给共享处理器，同一个 `lua_CFunction` 能服务成百上千个方法。
//
// **什么时候不能用它**（宁可手写，别硬塞 —— 与字段那套同一口径）：
//   * 参数里有**字符串/布尔/实体指针**等非整数（除非 `shape` 已经覆盖那一类）；
//   * 返回值是**指针/结构体**（要经过句柄包装，例如 `Level:GetCurrentRoomDesc`）；
//   * 需要"多个候选签名按运行时 kind 选一个"的写法；
//   * 接收者不是"句柄 + 固定偏移"的形状（要走容器、要链式解析）。

#include <cstddef>
#include <cstdint>

extern "C" {
#include "lua.h"
}

#include "interfaces/lua/field_api.hpp"

namespace isaac::runtime {

//: 调进去的**参数表 + 返回类型**（就是 C++ 侧的 ABI 形状）。
//:
//: 批次 055（2026-09-19）起，**形状本身也是数据**：下面这个枚举只是"行 → 描述符"的索引，
//: 真正的参数表在 `kEngineCallShapes`（`EngineCallShapeRow`，16 字节一行只读数据）；
//: 调进去的动作由通用跳板 `EngineCallTrampoline` 完成（见 `engine_call_trampoline.hpp`）。
//: 于是**新增一种签名组合只花一行描述符数据**，不再需要在共享处理器里加 `case`。
enum class EngineCallShape : std::uint8_t {
    Void0 = 0,   //: `void (*)(this)`——例如 `EntityPlayer:AnimateHappy()`
    Void1 = 1,   //: `void (*)(this, i32)`——例如 `EntityPlayer:AddCoins(int)`
    Void2 = 2,   //: `void (*)(this, i32, i32)`——例如 `Game:ChangeRoom(int, int)`
    Int0 = 3,    //: `i32 (*)(this)`——例如 `EntityPlayer:GetBlackHearts()`
    VoidFloat1 = 4,               //: `void (*)(this, float)`——`RoomConfig_Spawn:PickEntry` 一类
    VoidIntIntIntHandleInt = 5,   //: `void (*)(this, i32, i32, i32, EntityPlayer*, i32)`
    Bool0 = 6,                    //: `bool (*)(this)`——例如 `Entity:IsFlying()`（无参、返回布尔）
                                  //: ——`Game:StartRoomTransition(room, dir, anim, player, dim)`
};

//: 一个参数在 ABI 上属于哪一类（决定进 `x` 寄存器还是 `d` 寄存器、以及怎么从 Lua 栈上取值）。
enum class EngineArgKind : std::uint8_t {
    Int = 0,     //: Lua 整数 → 下一个 `x` 寄存器
    Float = 1,   //: Lua 数值 → 下一个 `d` 寄存器（**与整数各自独立计数**）
    Bool = 2,    //: Lua 布尔 → 下一个 `x` 寄存器（0/1）
    Handle = 3,  //: Lua 句柄（userdata）→ 引擎对象指针 → 下一个 `x` 寄存器；
                 //: 传 `nil` 时按**空指针**（PC 的可选对象参数默认就是 nil）；校验方式见
                 //: `EngineCallShapeRow::handleReceipt`
};

//: 返回值怎么解释（跳板把 `x0` 与 `d0` 都回填，这里只说读哪一个）。
enum class EngineReturnKind : std::uint8_t {
    Void = 0,
    Int = 1,    //: `x0` 低 32 位按整数压回
    Bool = 2,   //: `x0 != 0`
    Float = 3,  //: `d0` 按浮点压回
};

//: 一行描述符 = 一种签名（参数种类 + 返回种类）。**16 字节只读数据、0 字节代码。**
//:
//: 为什么参数上限是 8：AAPCS64 的寄存器参数就是 `x0..x7` 与 `d0..d7`；本项目的引擎方法
//: 都落在这个范围内。超过 8 个（或需要栈上传参、结构体返回）的那类，继续手写。
struct EngineCallShapeRow {
    std::uint8_t argumentCount;        //: Lua 侧参数个数（不含接收者），0..8
    EngineArgKind argumentKinds[8];    //: 前 `argumentCount` 个有效
    EngineReturnKind returnKind;
    FieldReceipt handleReceipt;        //: `Handle` 参数用哪套句柄校验（其余情况忽略）
    std::uint8_t reserved[5];          //: 凑满 16 字节（改结构体先看下面的 static_assert）
};

static_assert(sizeof(EngineCallShapeRow) == 16,
              "EngineCallShapeRow 必须保持 16 字节（同 EngineMethodRow 的成本前提）");

//: 一行 = 一个 API。字段顺序按"对齐后最小"排：4+4+4+1+1+1+1 = 16 字节。
struct EngineMethodRow {
    std::uint32_t id;             //: catalog id（必须与 `api_catalog.cpp` 里那条对得上）
    std::uint32_t offset;         //: 引擎方法相对**模块基址**的偏移
    std::uint32_t entryWord;      //: 入口首 4 字节（小端整字），调用前核对
    FieldReceipt receipt;         //: 接收者怎么解（复用字段那套：EntityPlayer / Level / Room …）
    EngineCallShape shape;        //: 参数表 + 返回类型
    std::uint8_t argumentCount;   //: Lua 侧应收的**整数**参数个数（不含接收者）
    std::uint8_t probeBit;        //: `api_sequence_probe.hpp` 的位号；`0xFF` = 不记
};

//: 一行必须正好 16 字节。这是这套机制的**成本前提**：行变大就会削弱
//: "每个 API 只花一行数据"的结论。改结构体先看这条断言。
static_assert(sizeof(EngineMethodRow) == 16, "EngineMethodRow 必须保持 16 字节（见成本说明）");

//: 引擎方法类的**共享处理器**。行通过闭包上值传入（见 `AttachOwnerMethods`）。
//:
//: 错误消息按 catalog 里的 `owner`/`name` 现拼（与手写处理器同口径）：拼消息只在出错路径上做，
//: 稳态零成本。
//:
//: 拿不到接收者 / 拿不到方法 / 指纹不匹配时**不报错**（按 PC 语义降级：返回 void 就什么都不做、
//: 返回整数就压 0）—— 报错会把整条模组回调摘掉，而那比"这一次没生效"严重得多。
[[nodiscard]] int EngineMethodHandler(lua_State* state);

//: 取**签名描述符表**（`EngineCallShape` 的索引就是它的下标）。表定义在 `isaac_api.cpp` 的
//: 匿名命名空间里，所以用访问器而不是 `extern` 数组。门禁按它核对"行里的参数个数与形状一致"。
[[nodiscard]] const EngineCallShapeRow* EngineCallShapeRows(std::size_t* count) noexcept;

} // namespace isaac::runtime
