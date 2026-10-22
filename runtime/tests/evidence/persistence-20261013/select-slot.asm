Disassembly of section .text:
0000000000413b7c <.text>:
00413b7c  d10303ff  sub        sp, sp, #0xc0
00413b80  a9077bfd  stp        x29, x30, [sp, #0x70]
00413b84  9101c3fd  add        x29, sp, #0x70
00413b88  a90867fa  stp        x26, x25, [sp, #0x80]
00413b8c  a9095ff8  stp        x24, x23, [sp, #0x90]
00413b90  a90a57f6  stp        x22, x21, [sp, #0xa0]
00413b94  a90b4ff4  stp        x20, x19, [sp, #0xb0]
00413b98  b00034d9  adrp       x25, 0xaac000 <.text+0x698484>
00413b9c  f9432739  ldr        x25, [x25, #0x648]  ; _ZN15IsaacRepentance9g_ManagerE
00413ba0  aa0003f3  mov        x19, x0
00413ba4  f9400320  ldr        x0, [x25]
00413ba8  9409a45e  bl         0x67cd20 <.text+0x2691a4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
00413bac  f9400328  ldr        x8, [x25]
00413bb0  397da109  ldrb       w9, [x8, #0xf68]
00413bb4  34000189  cbz        w9, 0x413be4 <.text+0x68>
00413bb8  d00034c8  adrp       x8, 0xaad000 <.text+0x699484>
00413bbc  f940d908  ldr        x8, [x8, #0x1b0]  ; _ZN15IsaacRepentance13g_MenuManagerE
00413bc0  f9400100  ldr        x0, [x8]
00413bc4  a94b4ff4  ldp        x20, x19, [sp, #0xb0]
00413bc8  52800061  mov        w1, #0x3                // =3
00413bcc  a94a57f6  ldp        x22, x21, [sp, #0xa0]
00413bd0  a9495ff8  ldp        x24, x23, [sp, #0x90]
00413bd4  a94867fa  ldp        x26, x25, [sp, #0x80]
00413bd8  a9477bfd  ldp        x29, x30, [sp, #0x70]
00413bdc  910303ff  add        sp, sp, #0xc0
00413be0  1409a3c0  b          0x67cae0 <.text+0x268f64>  ; import _ZN15IsaacRepentance11MenuManager8SetStateENS0_6eStateE
00413be4  91006100  add        x0, x8, #0x18
00413be8  9409a7de  bl         0x67db60 <.text+0x269fe4>  ; import _ZN15IsaacRepentance18PersistentGameData23GetMostRecentBackupDateEv
00413bec  52816008  mov        w8, #0xb00              // =2816
00413bf0  72a00108  movk       w8, #0x8, lsl #16
00413bf4  7100041f  cmp        w0, #0x1
00413bf8  b8286a60  str        w0, [x19, x8]
00413bfc  540007eb  b.lt       0x413cf8 <.text+0x17c>  ; -> ~_ZN15IsaacRepentance9Menu_Save16select_save_slotEi+0x17c
00413c00  5290a3e8  mov        w8, #0x851f             // =34079
00413c04  72aa3d68  movk       w8, #0x51eb, lsl #16
00413c08  9ba87c0a  umull      x10, w0, w8
00413c0c  d365fd4a  lsr        x10, x10, #37
00413c10  9b087d48  mul        x8, x10, x8
00413c14  5282eb29  mov        w9, #0x1759             // =5977
00413c18  72ba36e9  movk       w9, #0xd1b7, lsl #16
00413c1c  52800c94  mov        w20, #0x64              // =100
00413c20  1b148155  msub       w21, w10, w20, w0
00413c24  528d9818  mov        w24, #0x6cc0            // =27840
00413c28  72a00078  movk       w24, #0x3, lsl #16
00413c2c  d365fd08  lsr        x8, x8, #37
00413c30  1b14a916  msub       w22, w8, w20, w10
00413c34  9ba97c08  umull      x8, w0, w9
00413c38  f9400320  ldr        x0, [x25]
00413c3c  d36dfd08  lsr        x8, x8, #45
00413c40  9b097d09  mul        x9, x8, x9
00413c44  d36dfd29  lsr        x9, x9, #45
00413c48  5284e20a  mov        w10, #0x2710            // =10000
00413c4c  8b180001  add        x1, x0, x24
00413c50  b00024a2  adrp       x2, 0x8a8000 <.text+0x494484>
00413c54  911ee442  add        x2, x2, #0x7b9  ; "#SAVE_DATA_CORRUPTED_HAS_BACKUP_LINE_3"
00413c58  1b0aa137  msub       w23, w9, w10, w8
00413c5c  94098fd5  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413c60  aa0003e2  mov        x2, x0
00413c64  910033e0  add        x0, sp, #0xc
00413c68  aa1403e1  mov        x1, x20
00413c6c  2a1603e3  mov        w3, w22
00413c70  2a1503e4  mov        w4, w21
00413c74  2a1703e5  mov        w5, w23
00413c78  94097732  bl         0x671940 <.text+0x25ddc4>  ; import snprintf
00413c7c  f9400320  ldr        x0, [x25]
00413c80  8b180001  add        x1, x0, x24
00413c84  d0002422  adrp       x2, 0x899000 <.text+0x485484>
00413c88  91043842  add        x2, x2, #0x10e  ; "#SAVE_DATA_CORRUPTED_HAS_BACKUP_LINE_1"
00413c8c  9120e274  add        x20, x19, #0x838
00413c90  94098fc8  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413c94  aa0003f5  mov        x21, x0
00413c98  f9400320  ldr        x0, [x25]
00413c9c  8b180001  add        x1, x0, x24
00413ca0  f0002422  adrp       x2, 0x89a000 <.text+0x486484>
00413ca4  91326442  add        x2, x2, #0xc99  ; "#SAVE_DATA_CORRUPTED_HAS_BACKUP_LINE_2"
00413ca8  94098fc2  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413cac  aa0003f6  mov        x22, x0
00413cb0  f9400320  ldr        x0, [x25]
00413cb4  8b180001  add        x1, x0, x24
00413cb8  b00024e2  adrp       x2, 0x8b0000 <.text+0x49c484>
00413cbc  912e6042  add        x2, x2, #0xb98  ; "#SAVE_DATA_CORRUPTED_HAS_BACKUP_LINE_4"
00413cc0  94098fbc  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413cc4  aa0003f7  mov        x23, x0
00413cc8  f9400320  ldr        x0, [x25]
00413ccc  8b180001  add        x1, x0, x24
00413cd0  90002462  adrp       x2, 0x89f000 <.text+0x48b484>
00413cd4  91189842  add        x2, x2, #0x626  ; "#SAVE_DATA_CORRUPTED_HAS_BACKUP_LINE_5"
00413cd8  94098fb6  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413cdc  aa0003e5  mov        x5, x0
00413ce0  910033e3  add        x3, sp, #0xc
00413ce4  aa1403e0  mov        x0, x20
00413ce8  aa1503e1  mov        x1, x21
00413cec  aa1603e2  mov        x2, x22
00413cf0  aa1703e4  mov        x4, x23
00413cf4  14000027  b          0x413d90 <.text+0x214>  ; -> ~_ZN15IsaacRepentance9Menu_Save16select_save_slotEi+0x214
00413cf8  f9400320  ldr        x0, [x25]
00413cfc  528d981a  mov        w26, #0x6cc0            // =27840
00413d00  72a0007a  movk       w26, #0x3, lsl #16
00413d04  8b1a0001  add        x1, x0, x26
00413d08  90002502  adrp       x2, 0x8b3000 <.text+0x49f484>
00413d0c  9134f042  add        x2, x2, #0xd3c  ; "#SAVE_DATA_CORRUPTED_NO_BACKUP_LINE_1"
00413d10  9120e274  add        x20, x19, #0x838
00413d14  94098fa7  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413d18  aa0003f5  mov        x21, x0
00413d1c  f9400320  ldr        x0, [x25]
00413d20  8b1a0001  add        x1, x0, x26
00413d24  90002502  adrp       x2, 0x8b3000 <.text+0x49f484>
00413d28  91358842  add        x2, x2, #0xd62  ; "#SAVE_DATA_CORRUPTED_NO_BACKUP_LINE_2"
00413d2c  94098fa1  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413d30  aa0003f6  mov        x22, x0
00413d34  f9400320  ldr        x0, [x25]
00413d38  8b1a0001  add        x1, x0, x26
00413d3c  900024c2  adrp       x2, 0x8ab000 <.text+0x497484>
00413d40  9111ec42  add        x2, x2, #0x47b  ; "#SAVE_DATA_CORRUPTED_NO_BACKUP_LINE_3"
00413d44  94098f9b  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413d48  aa0003f7  mov        x23, x0
00413d4c  f9400320  ldr        x0, [x25]
00413d50  8b1a0001  add        x1, x0, x26
00413d54  d00023e2  adrp       x2, 0x891000 <.text+0x47d484>
00413d58  911dc042  add        x2, x2, #0x770  ; "#SAVE_DATA_CORRUPTED_NO_BACKUP_LINE_4"
00413d5c  94098f95  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413d60  aa0003f8  mov        x24, x0
00413d64  f9400320  ldr        x0, [x25]
00413d68  8b1a0001  add        x1, x0, x26
00413d6c  900023e2  adrp       x2, 0x88f000 <.text+0x47b484>
00413d70  910aec42  add        x2, x2, #0x2bb  ; "#SAVE_DATA_CORRUPTED_NO_BACKUP_LINE_5"
00413d74  94098f8f  bl         0x677bb0 <.text+0x264034>  ; import _ZN15IsaacRepentance7Manager9GetStringERN4KAGE4Util11StringTableEPKc
00413d78  aa0003e5  mov        x5, x0
00413d7c  aa1403e0  mov        x0, x20
00413d80  aa1503e1  mov        x1, x21
00413d84  aa1603e2  mov        x2, x22
00413d88  aa1703e3  mov        x3, x23
00413d8c  aa1803e4  mov        x4, x24
00413d90  94099f6c  bl         0x67bb40 <.text+0x267fc4>  ; import _ZN15IsaacRepentance13GenericPrompt7SetTextEPKcS2_S2_S2_S2_
00413d94  9120e260  add        x0, x19, #0x838
00413d98  9409984e  bl         0x679ed0 <.text+0x266354>  ; import _ZN15IsaacRepentance13GenericPrompt4ShowEv
00413d9c  52800068  mov        w8, #0x3                // =3
00413da0  b9000268  str        w8, [x19]
00413da4  a94b4ff4  ldp        x20, x19, [sp, #0xb0]
00413da8  a94a57f6  ldp        x22, x21, [sp, #0xa0]
00413dac  a9495ff8  ldp        x24, x23, [sp, #0x90]
00413db0  a94867fa  ldp        x26, x25, [sp, #0x80]
00413db4  a9477bfd  ldp        x29, x30, [sp, #0x70]
00413db8  910303ff  add        sp, sp, #0xc0
00413dbc  d65f03c0  ret        
00413dc0  a9bd7bfd  stp        x29, x30, [sp, #-0x30]!
00413dc4  a90157f6  stp        x22, x21, [sp, #0x10]
00413dc8  910003fd  mov        x29, sp
00413dcc  a9024ff4  stp        x20, x19, [sp, #0x20]
00413dd0  b00034d6  adrp       x22, 0xaac000 <.text+0x698484>
00413dd4  f94326d6  ldr        x22, [x22, #0x648]  ; _ZN15IsaacRepentance9g_ManagerE
00413dd8  aa0003f5  mov        x21, x0
00413ddc  f94002c0  ldr        x0, [x22]
00413de0  b9401013  ldr        w19, [x0, #0x10]
00413de4  2a0103f4  mov        w20, w1
00413de8  6b01027f  cmp        w19, w1
00413dec  54000161  b.ne       0x413e18 <.text+0x29c>  ; -> ~_ZN15IsaacRepentance9Menu_Save12refresh_slotEi+0x58
00413df0  52802b08  mov        w8, #0x158              // =344
00413df4  9b285688  smaddl     x8, w20, w8, x21
00413df8  91006113  add        x19, x8, #0x18
00413dfc  aa1303e1  mov        x1, x19
00413e00  9409a748  bl         0x67db20 <.text+0x269fa4>  ; import _ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E
00413e04  aa1303e0  mov        x0, x19
00413e08  a9424ff4  ldp        x20, x19, [sp, #0x20]
00413e0c  a94157f6  ldp        x22, x21, [sp, #0x10]
00413e10  a8c37bfd  ldp        x29, x30, [sp], #0x30
00413e14  14096fa3  b          0x66fca0 <.text+0x25c124>  ; import _ZN15IsaacRepentance4ANM212LoadGraphicsEv
00413e18  2a1403e1  mov        w1, w20
00413e1c  9409a3c1  bl         0x67cd20 <.text+0x2691a4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
00413e20  52802b08  mov        w8, #0x158              // =344
00413e24  9b285688  smaddl     x8, w20, w8, x21
00413e28  91006114  add        x20, x8, #0x18
00413e2c  aa1403e1  mov        x1, x20
00413e30  9409a73c  bl         0x67db20 <.text+0x269fa4>  ; import _ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E
00413e34  aa1403e0  mov        x0, x20
00413e38  94096f9a  bl         0x66fca0 <.text+0x25c124>  ; import _ZN15IsaacRepentance4ANM212LoadGraphicsEv
00413e3c  f94002c0  ldr        x0, [x22]
00413e40  2a1303e1  mov        w1, w19
00413e44  a9424ff4  ldp        x20, x19, [sp, #0x20]
00413e48  a94157f6  ldp        x22, x21, [sp, #0x10]
00413e4c  a8c37bfd  ldp        x29, x30, [sp], #0x30
00413e50  1409a3b4  b          0x67cd20 <.text+0x2691a4>  ; import _ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE
00413e54  d101c3ff  sub        sp, sp, #0x70
00413e58  a9027bfd  stp        x29, x30, [sp, #0x20]
00413e5c  910083fd  add        x29, sp, #0x20
00413e60  a90367fa  stp        x26, x25, [sp, #0x30]
00413e64  a9045ff8  stp        x24, x23, [sp, #0x40]
00413e68  a90557f6  stp        x22, x21, [sp, #0x50]
00413e6c  a9064ff4  stp        x20, x19, [sp, #0x60]
00413e70  b00034c8  adrp       x8, 0xaac000 <.text+0x698484>
00413e74  f9432508  ldr        x8, [x8, #0x648]  ; _ZN15IsaacRepentance9g_ManagerE
00413e78  f9400116  ldr        x22, [x8]
00413e7c  397da2c8  ldrb       w8, [x22, #0xf68]
00413e80  aa0103f3  mov        x19, x1
00413e84  34000188  cbz        w8, 0x413eb4 <.text+0x338>
00413e88  910062d4  add        x20, x22, #0x18
00413e8c  52804fa1  mov        w1, #0x27d              // =637
00413e90  aa1403e0  mov        x0, x20
00413e94  940973f7  bl         0x670e70 <.text+0x25d2f4>  ; import _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
00413e98  360001a0  tbz        w0, #0x0, 0x413ecc <.text+0x350>
00413e9c  2a1f03f9  mov        w25, wzr
00413ea0  aa1f03f4  mov        x20, xzr
00413ea4  5280003a  mov        w26, #0x1               // =1
00413ea8  900024b5  adrp       x21, 0x8a7000 <.text+0x493484>
00413eac  911a5eb5  add        x21, x21, #0x697  ; "gfx/ui/main menu/SaveDrawings/DeadGod.png"
00413eb0  14000065  b          0x414044 <.text+0x4c8>  ; -> ~_ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E+0x1f0
00413eb4  2a1f03f9  mov        w25, wzr
00413eb8  aa1f03f4  mov        x20, xzr
00413ebc  5280003a  mov        w26, #0x1               // =1
00413ec0  f0002435  adrp       x21, 0x89a000 <.text+0x486484>
00413ec4  9133a2b5  add        x21, x21, #0xce8  ; "gfx/ui/main menu/SaveDrawings/CorruptData.png"
00413ec8  1400005f  b          0x414044 <.text+0x4c8>  ; -> ~_ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E+0x1f0
00413ecc  b94a72c8  ldr        w8, [x22, #0xa70]
00413ed0  340000e8  cbz        w8, 0x413eec <.text+0x370>
00413ed4  2a1f03f9  mov        w25, wzr
00413ed8  aa1f03f4  mov        x20, xzr
00413edc  5280003a  mov        w26, #0x1               // =1
00413ee0  90002475  adrp       x21, 0x89f000 <.text+0x48b484>
00413ee4  911936b5  add        x21, x21, #0x64d  ; "gfx/ui/main menu/SaveDrawings/Beast.png"
00413ee8  14000057  b          0x414044 <.text+0x4c8>  ; -> ~_ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E+0x1f0
00413eec  b94e9ec8  ldr        w8, [x22, #0xe9c]
00413ef0  7100011f  cmp        w8, #0x0
00413ef4  540000ed  b.le       0x413f10 <.text+0x394>  ; -> ~_ZN15IsaacRepentance9Menu_Save21replace_slot_graphicsERNS_4ANM2E+0xbc
00413ef8  2a1f03f9  mov        w25, wzr
