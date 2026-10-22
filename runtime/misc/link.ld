OUTPUT_FORMAT(elf64-littleaarch64)
OUTPUT_ARCH(aarch64)
ENTRY(__module_start)

PHDRS
{
  text PT_LOAD FLAGS(5);
  rodata PT_LOAD FLAGS(4);
  data PT_LOAD FLAGS(6);
  dynamic PT_DYNAMIC;
}

SECTIONS
{
  PROVIDE_HIDDEN(__start__ = 0x0);
  . = __start__;
  __code_start__ = .;

  /* App code */
  .text : {
    HIDDEN(__text_start__ = .);
    KEEP (*(.text.crt0))
    *(.text .text.*)
    HIDDEN(__text_end__ = .);
  } :text

  /* Trampoline and stuffs */
  .plt : { *(.plt .plt.*) } :text
  __code_end__ = .;

  /* Read-only sections */
  ASSERT(!DEFINED(EXL_STARTUP_PROBE_COMPAT_LAYOUT) || __code_end__ < 0x55000,
         "Stage 6 compatibility layout requires RX below 0x55000")
  /*
   * 段地址按体积推导：只读段紧接代码段，读写段紧随只读段，中间不留未映射页。
   * exlaunch 的 FindModules() 走 svcQueryMemory，靠 CodeStatic+Rx ->
   * CodeStatic+R -> CodeMutable+Rw 这个连续三元组识别模块；中间插入未映射页会让
   * 状态机复位、Runtime 找不到自己，mem_layout 断言中止（2026-09-10 真机 Data Abort，
   * "ModuleIdx < ModuleIndex::End"）。硬件要求只有这一条，加上“只读段非空”。
   *
   * 2026-09-12 复核：原来的 `--defsym=EXL_LAYOUT_PIN=0x54000` 把某次真机验证过的
   * **历史地址**（代码 0x54000、只读段结束 0x75000）当成了上限断言。自 806adbd 起段
   * 地址已改为按体积推导，这两个常数不再是放置指令，只剩“涨过就链接失败”的闸门作用，
   * 会在功能没写满之前先把构建拦住（探针构建曾真实撞线，见 misc/mk/common.mk）。
   * 因此这里换成两条**失控增长**闸门：单段 1 MiB / 只读段结束 2 MiB，比实测用量留出
   * 一倍以上余量；实际用量与余量由 `tools/runtime_layout_budget.py` 在每次构建后报告。
   *
   * 2026-09-19 抬升（理由与当时用量）：原值 512 KiB / 1 MiB 在"每加一条 API 都要手写
   * ≈490 字节代码"的成本模型下只剩 272 字节可用额度，碰线就构建失败。抬升前核实过：
   *   ① 这两条是**自设的失控增长闸门**、不是平台限制 —— 上游 Atmosphere 的加载器
   *      （docs/components/modules/loader.md）只要求"把 exefs 里的各个 NSO 连续装进进程"，
   *      没有体积上限；
   *   ② exlaunch 的 `FindModules()` 只按 `CodeStatic+Rx -> CodeStatic+R -> CodeMutable+Rw`
   *      权限三元组匹配（`runtime/exlaunch/source/lib/util/sys/mem_layout.cpp`），
   *      唯一的容量限制是模块**个数**，没有体积上限；
   *   ③ 内存不是瓶颈：模块三段映射 Rx 480 KiB / R 224 KiB / **Rw 35.5 MiB**
   *      （其中 32 MiB 是我们自己的 `__fake_heap`），而游戏本体 `Repentance.nro` 是 11.2 MiB。
   * 抬升时用量：代码结束 `0x77ef0`、只读段结束 `0xaf7fc`。
   */
  /* 2026-10-13：新65方法、字段和真实Shader链的逐对象账见
   * dist/callback-rplus-20261013/object-sizes-build9.txt。
   * 链接RX=0x107A00（仅超过旧闸门31232B），已排除重复旧实现。
   * RX闸门增加128KiB到1.125MiB；RO仍2MiB。449预算从实际NSO重新生成。 */
  /* 2026-10-14：用户明确要求代码预算扩展到4MiB，依据见
   * docs/API扩展容量与预算说明-20261014.md。API300已共享重复检查；
   * 这两个限额只控制增长，不预填地址空间。RO累计上限同步为6MiB，
   * 使代码到4MiB时仍有2MiB只读预算；实际NSO占用另重算原生内存补丁。
   * 152MiB假堆、32KiB保留线、页对齐/连续三段及展开信息保持原要求。 */
  ASSERT(__code_end__ <= 0x400000,
         "RX 段超过 4 MiB：先确认是否为失控增长，再按预算规则调整上限")
  . = DEFINED(EXL_STARTUP_PROBE_COMPAT_LAYOUT) ? 0x55000 : ALIGN(0x1000);

  /* App name */
  .module_name : { KEEP (*(.nx-module-name)) } :rodata

  /* Make sure everything is aligned */
  . = ALIGN(8);

  /* App rodata */
  .layout_padding : { KEEP(*(.rodata.layout_padding)) } :rodata
  .rodata : {
    *(.rodata .rodata.*)
  } :rodata

  /* All the symbols needed for relocation lookup */
  .hash     : { *(.hash) } :rodata
  .gnu.hash : { *(.gnu.hash) } :rodata
  .dynsym   : { *(.dynsym .dynsym.*) } :rodata
  .dynstr   : { *(.dynstr .dynstr.*) } :rodata

  __rel_dyn_start__ = .;
  .rel.dyn : { *(.rel.dyn) } :rodata
  __rel_dyn_end__ = .;

  __rela_dyn_start__ = .;
  .rela.dyn : { *(.rela.dyn) } :rodata
  __rela_dyn_end__ = .;

  __rel_plt_start__ = .;
  .rel.plt        : { *(.rel.plt) } :rodata
  __rel_plt_end__ = .;

  __rela_plt_start__ = .;
  .rela.plt       : { *(.rela.plt) } :rodata
  __rela_plt_end__ = .;

  /* All exception handling sections */
  .gcc_except_table : { *(.gcc_except_table .gcc_except_table.*) } :rodata

  /*
   * ★★ 展开表（`.eh_frame` / `.eh_frame_hdr`）**必须保留** —— 2026-09-24（批次 104）恢复。
   *
   * ★ 2026-09-25（批次 134）**更正**：批次 104 当初写的"**系统加载器**按 MOD0 那对区间把本模块的
   * 展开信息注册给 libgcc"是**未经验证的推断，且是错的**。实测（`dist/freeze-20260925/`）：
   *   ① 本模块的 `_Unwind_Find_FDE` **只查自己 .bss 里那张"已登记对象"链表**，不查任何模块表；
   *   ② 那张链表**永远是空的** —— 本模块是 `-nostartfiles`，没有 crtbegin ⇒ 没人调
   *      `__register_frame_info_bases`（平时由 crtbegin 的 `frame_dummy` 做），而且那个入口
   *      **根本没被链接进来**、也没有导出，外部无从替我们登记。
   *   ⇒ 于是 2026-09-25 又一次真机"画面卡死、音乐还在"（同 09-21 / 09-24 的签名）。
   *
   * ★★ 同一批还发现**第二个必需件**：展开器是"**按长度逐个走、直到遇到零长条目为止**"，
   *   而那个零长终止符平时由 **crtend.o** 提供 —— `-nostartfiles` 同样没有它。
   *   实测（离线走链）：我们的 `.eh_frame` 里 2 CIE + 1880 FDE 正好把区间走完，
   *   **始终没有终止符** ⇒ libgcc 继续往后读垃圾长度 ⇒ `classify_object_over_fdes` 返回 −1
   *   ⇒ 把这个对象**判定为空**（`u`/`s` 被换成只读段里的哨兵 `0xAC888`/`0x7F8`，设备读数与
   *   `search_object` 的失败分支反汇编逐字一致）⇒ 登记了也永远查不到 FDE。
   *   ⇒ **本段末尾必须补一个 4 字节零**（`LONG(0)`，等价于 crtend 的 `__FRAME_END__`）。
   *
   * 所以本段有**三件事**不能少：① `.eh_frame`/`.eh_frame_hdr` 不被丢；
   * ② 由我们自己登记（`source/eh_frame_registration.cpp`，所以要导出起止符号）；
   * ③ **末尾那个零长终止符**。判据由 `runtime/tests/test_architecture_layout.py` 钉住。
   *
   * MOD0 那对 `__eh_frame_hdr_start__/end__` **仍然要填对**（`crt0.s` 写入、`/DISCARD/` 不许丢），
   * 那是模块头自描述的一部分；但**它不等于"已经登记"** —— 别再把两者混为一谈。
   *
   * 只读预算：实测仍远低于闸门上限（代码段 1 MiB / 只读段 2 MiB），所以不用放宽上限。
   */
  .eh_frame_hdr : {
    HIDDEN(__eh_frame_hdr_start__ = .);
    KEEP (*(.eh_frame_hdr .eh_frame_hdr.*))
    HIDDEN(__eh_frame_hdr_end__ = .);
  } :rodata
  .eh_frame : {
    HIDDEN(__eh_frame_start__ = .);
    KEEP (*(.eh_frame .eh_frame.*))
    /* ★ crtend 的零长终止符（`-nostartfiles` 没有 crtend ⇒ 必须自己补）。
       展开器靠它判断"这个对象走完了"；没有它，链会一直往后读、直到把整支判成空。*/
    LONG(0);
    HIDDEN(__eh_frame_end__ = .);
  } :rodata

  /* Misc .rodata stuffs (build-id, etc.) */
  .note.gnu.build-id : { *(.note.gnu.build-id) } :rodata

  /* Read-write sections */
  ASSERT(. > __code_end__, "只读段必须非空：exlaunch 靠 Rx->R->Rw 三元组识别模块")
  ASSERT(. <= 0x600000,
         "代码与只读段累计结束超过 6 MiB：先确认是否为失控增长，再按预算规则调整上限")
  . = DEFINED(EXL_STARTUP_PROBE_COMPAT_LAYOUT) ? 0x76000 : ALIGN(0x1000);
  ASSERT((. & 0xFFF) == 0,
         "读写段起点必须 4 KiB 对齐：SaltyNX 1.8.1 用 PT_DYNAMIC 计算插件映射跨度")

  /*
   * SaltyNX 1.8.1 includes PT_DYNAMIC when calculating an external
   * plugin's mapping span. Keep it at the start of this page so that span
   * remains page-aligned even for a minimal plugin with only a small GOT.
   */
  .dynamic : {
    HIDDEN(__dynamic_start__ = .);
    *(.dynamic)
  } :data :dynamic

  /* App data */
  .data : {
    *(.data .data.*)
  } :data

  /* This section should be made read only after relocation but in practice we will not do that */
  .data.rela.ro : {
    *(.data.rela.ro.local*)
    *(.data.rela.ro .data.rela.ro.*)
  } :data

  /* This section should be made read only after relocation but in practice we will not do that */
  .data.rel.ro : {
    *(.data.rel.ro.local*)
    *(.data.rel.ro .data.rel.ro.*)
  } :data

  /* All GOT sections */
  __got_start__ = .;
  .got : { *(.got.plt) *(.igot.plt) *(.got) *(.igot) } :data
  __got_end__ = .;

  /* Align for .init_array/.fini_array */
  . = ALIGN(8);

  .preinit_array ALIGN(8) :
  {
    PROVIDE_HIDDEN (__preinit_array_start = .);
    KEEP (*(.preinit_array))
    PROVIDE_HIDDEN (__preinit_array_end = .);
  } :data

  /* App init array */
  .init_array : {
    PROVIDE_HIDDEN (__init_array_start = .);
    KEEP (*(SORT_BY_INIT_PRIORITY(.init_array.*)))
    KEEP (*(.init_array))
    PROVIDE_HIDDEN (__init_array_end  = .);
  } :data

  /* App fini array */
  .fini_array : {
    PROVIDE_HIDDEN (__fini_array_start__ = .);
    KEEP (*(SORT_BY_INIT_PRIORITY(.fini_array.*)))
    KEEP (*(.fini_array))
    PROVIDE_HIDDEN (__fini_array_end__ = .);
  } :data

  /* Thread Local sections */

  .tdata : {
    __tdata_align_abs__ = ABSOLUTE(.);
    __tdata_start__ = .;
    *(.tdata .tdata.*)
    __tdata_end__ = .;
  } :data

  .tbss : {
    __tbss_align_abs__ = ABSOLUTE(.);
    __tbss_start__ = .;
    *(.tbss .tbss.*)
    *(.tcommon)
    __tbss_end__ = .;
  } :data

  /* BSS section */
  . = ALIGN(0x1000);

  .bss : {
    HIDDEN(__bss_start__ = .);
    *(.bss .bss.*)
    *(COMMON)
    . = ALIGN(8);
    HIDDEN(__bss_end__ = .);
    . = ALIGN(0x1000);
  } :data

  __end__ = ABSOLUTE(.);

  HIDDEN(__argdata__ = .);

  /DISCARD/ : {
    /* No need of the interpreter */
    *(.interp)
    /* ★ 展开表**不在这里丢**（2026-09-24 批次 104 起）：`.eh_frame*` 必须在只读段里、
       并被 MOD0 的那对符号框住 —— 理由与代价见上面对 `.eh_frame_hdr` 的说明。*/
  }
}
