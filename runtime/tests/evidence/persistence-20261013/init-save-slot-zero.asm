Disassembly of section .text:
00000000003f5898 <.text>:
003f5898  d10543ff  sub        sp, sp, #0x150
003f589c  a9107bfd  stp        x29, x30, [sp, #0x100]
003f58a0  910403fd  add        x29, sp, #0x100
003f58a4  a91167fc  stp        x28, x25, [sp, #0x110]
003f58a8  a9125ff8  stp        x24, x23, [sp, #0x120]
003f58ac  a91357f6  stp        x22, x21, [sp, #0x130]
003f58b0  a9144ff4  stp        x20, x19, [sp, #0x140]
003f58b4  528e6008  mov        w8, #0x7300             // =29440
003f58b8  72a003a8  movk       w8, #0x1d, lsl #16
003f58bc  8b080017  add        x23, x0, x8
003f58c0  528d9808  mov        w8, #0x6cc0             // =27840
003f58c4  72a00068  movk       w8, #0x3, lsl #16
003f58c8  528ca589  mov        w9, #0x652c             // =25900
003f58cc  72a00069  movk       w9, #0x3, lsl #16
003f58d0  8b080014  add        x20, x0, x8
003f58d4  aa0003f3  mov        x19, x0
003f58d8  8b090018  add        x24, x0, x9
003f58dc  900024e1  adrp       x1, 0x891000 <.text+0x49b768>
003f58e0  911c6c21  add        x1, x1, #0x71b  ; "stringtable.sta"
003f58e4  aa1403e0  mov        x0, x20
003f58e8  940a1b52  bl         0x67c630 <.text+0x286d98>  ; import _ZN4KAGE4Util11StringTable4LoadEPKc
003f58ec  528da008  mov        w8, #0x6d00             // =27904
003f58f0  72a00068  movk       w8, #0x3, lsl #16
003f58f4  8b080275  add        x21, x19, x8
003f58f8  90002581  adrp       x1, 0x8a5000 <.text+0x4af768>
003f58fc  913f8021  add        x1, x1, #0xfe0  ; "stringtable_nx.sta"
003f5900  aa1503e0  mov        x0, x21
003f5904  940a1b4b  bl         0x67c630 <.text+0x286d98>  ; import _ZN4KAGE4Util11StringTable4LoadEPKc
003f5908  f00035a0  adrp       x0, 0xaac000 <.text+0x6b6768>
003f590c  f9446000  ldr        x0, [x0, #0x8c0]  ; _ZN4KAGE6System9g_ManagerE
003f5910  940a1b4c  bl         0x67c640 <.text+0x286da8>  ; import _ZN4KAGE6System7Manager17GetSystemLanguageEv
003f5914  2a1f03f6  mov        w22, wzr
003f5918  7100341f  cmp        w0, #0xd
003f591c  54000148  b.hi       0x3f5944 <.text+0xac>  ; -> ~_ZN15IsaacRepentance7Manager4InitEv+0xac
003f5920  52800028  mov        w8, #0x1                // =1
003f5924  1ac02108  lsl        w8, w8, w0
003f5928  528586a9  mov        w9, #0x2c35             // =11317
003f592c  6a09011f  tst        w8, w9
003f5930  540000a0  b.eq       0x3f5944 <.text+0xac>  ; -> ~_ZN15IsaacRepentance7Manager4InitEv+0xac
003f5934  f00035a0  adrp       x0, 0xaac000 <.text+0x6b6768>
003f5938  f9446000  ldr        x0, [x0, #0x8c0]  ; _ZN4KAGE6System9g_ManagerE
003f593c  940a1b41  bl         0x67c640 <.text+0x286da8>  ; import _ZN4KAGE6System7Manager17GetSystemLanguageEv
003f5940  2a0003f6  mov        w22, w0
003f5944  aa1403e0  mov        x0, x20
003f5948  2a1603e1  mov        w1, w22
003f594c  940a1b41  bl         0x67c650 <.text+0x286db8>  ; import _ZN4KAGE4Util11StringTable18SetCurrentLanguageENS_9eLanguageE
003f5950  aa1503e0  mov        x0, x21
003f5954  2a1603e1  mov        w1, w22
003f5958  940a1b3e  bl         0x67c650 <.text+0x286db8>  ; import _ZN4KAGE4Util11StringTable18SetCurrentLanguageENS_9eLanguageE
003f595c  940a1729  bl         0x67b600 <.text+0x285d68>  ; import _ZN15IsaacRepentance25RebuildContentMountPointsEv
003f5960  52800039  mov        w25, #0x1               // =1
003f5964  b90002ff  str        wzr, [x23]
003f5968  f00035a3  adrp       x3, 0xaac000 <.text+0x6b6768>
003f596c  390772f9  strb       w25, [x23, #0x1dc]
003f5970  f00025c2  adrp       x2, 0x8b0000 <.text+0x4ba768>
003f5974  91224442  add        x2, x2, #0x891  ; "%s%s"
003f5978  3920831f  strb       wzr, [x24, #0x820]
003f597c  f9449c63  ldr        x3, [x3, #0x938]
003f5980  d0002504  adrp       x4, 0x897000 <.text+0x4a1768>
003f5984  911c0884  add        x4, x4, #0x702  ; "options.ini"
003f5988  910003e0  mov        x0, sp
003f598c  52802001  mov        w1, #0x100              // =256
003f5990  9409efec  bl         0x671940 <.text+0x27c0a8>  ; import snprintf
003f5994  528c9a08  mov        w8, #0x64d0             // =25808
003f5998  72a00068  movk       w8, #0x3, lsl #16
003f599c  8b080276  add        x22, x19, x8
003f59a0  aa1603e0  mov        x0, x22
003f59a4  940a1b2f  bl         0x67c660 <.text+0x286dc8>  ; import _ZN15IsaacRepentance13OptionsConfig16LoadGlobalConfigEv
003f59a8  910003e1  mov        x1, sp
003f59ac  aa1603e0  mov        x0, x22
003f59b0  940a1b30  bl         0x67c670 <.text+0x286dd8>  ; import _ZN15IsaacRepentance13OptionsConfig4LoadEPKc
003f59b4  aa1403e0  mov        x0, x20
003f59b8  9409f256  bl         0x672310 <.text+0x27ca78>  ; import _ZN4KAGE4Util11StringTable18GetCurrentLanguageEv
003f59bc  2a0003f6  mov        w22, w0
003f59c0  aa1403e0  mov        x0, x20
003f59c4  2a1603e1  mov        w1, w22
003f59c8  940a1b22  bl         0x67c650 <.text+0x286db8>  ; import _ZN4KAGE4Util11StringTable18SetCurrentLanguageENS_9eLanguageE
003f59cc  aa1503e0  mov        x0, x21
003f59d0  2a1603e1  mov        w1, w22
003f59d4  940a1b1f  bl         0x67c650 <.text+0x286db8>  ; import _ZN4KAGE4Util11StringTable18SetCurrentLanguageENS_9eLanguageE
003f59d8  940a170a  bl         0x67b600 <.text+0x285d68>  ; import _ZN15IsaacRepentance25RebuildContentMountPointsEv
003f59dc  f00035b4  adrp       x20, 0xaac000 <.text+0x6b6768>
003f59e0  f9437694  ldr        x20, [x20, #0x6e8]  ; _ZN4KAGE8Graphics9g_ManagerE
003f59e4  aa1403e0  mov        x0, x20
003f59e8  9409ee46  bl         0x671300 <.text+0x27ba68>  ; import _ZN4KAGE8Graphics11ManagerBase21SetRenderTargetScreenEv
003f59ec  aa1403e0  mov        x0, x20
003f59f0  9409ec08  bl         0x670a10 <.text+0x27b178>  ; import _ZN4KAGE8Graphics7Manager5ClearEv
003f59f4  aa1403e0  mov        x0, x20
003f59f8  9409ec12  bl         0x670a40 <.text+0x27b1a8>  ; import _ZN4KAGE8Graphics7Manager7PresentEv
003f59fc  940a1b21  bl         0x67c680 <.text+0x286de8>  ; import _ZN15IsaacRepentance5Seeds12InitSeedInfoEv
003f5a00  aa1303e0  mov        x0, x19
003f5a04  3920871f  strb       wzr, [x24, #0x821]
003f5a08  940a1b22  bl         0x67c690 <.text+0x286df8>  ; import _ZN15IsaacRepentance7Manager15create_surfacesEv
003f5a0c  91205308  add        x8, x24, #0x814
003f5a10  528faa00  mov        w0, #0x7d50             // =32080
003f5a14  72a00680  movk       w0, #0x34, lsl #16
003f5a18  f900067f  str        xzr, [x19, #0x8]
003f5a1c  b900127f  str        wzr, [x19, #0x10]
003f5a20  7900111f  strh       wzr, [x8, #0x8]
003f5a24  f900011f  str        xzr, [x8]
