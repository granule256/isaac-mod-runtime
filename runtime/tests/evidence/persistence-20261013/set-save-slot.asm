Disassembly of section .text:
00000000003faa28 <.text>:
003faa28  a9bd7bfd  stp        x29, x30, [sp, #-0x30]!
003faa2c  a90157fc  stp        x28, x21, [sp, #0x10]
003faa30  910003fd  mov        x29, sp
003faa34  a9024ff4  stp        x20, x19, [sp, #0x20]
003faa38  d11003ff  sub        sp, sp, #0x400
003faa3c  91006015  add        x21, x0, #0x18
003faa40  2a0103f3  mov        w19, w1
003faa44  aa0003f4  mov        x20, x0
003faa48  aa1503e0  mov        x0, x21
003faa4c  52800021  mov        w1, #0x1                // =1
003faa50  940a08a0  bl         0x67ccd0 <.text+0x2822a8>  ; import _ZN15IsaacRepentance18PersistentGameData5ClearEb
003faa54  34000453  cbz        w19, 0x3faadc <.text+0xb4>
003faa58  d0002501  adrp       x1, 0x89c000 <.text+0x4a15d8>
003faa5c  9101c021  add        x1, x1, #0x70
003faa60  2a1f03e0  mov        w0, wzr
003faa64  2a1303e2  mov        w2, w19
003faa68  9409d496  bl         0x66fcc0 <.text+0x275298>  ; import KAGE_LogMessage
003faa6c  d0003583  adrp       x3, 0xaac000 <.text+0x6b15d8>
003faa70  f9449c63  ldr        x3, [x3, #0x938]  ; _ZN15IsaacRepentance14g_SaveDataPathE
003faa74  b00024e2  adrp       x2, 0x897000 <.text+0x49c5d8>
003faa78  911c4442  add        x2, x2, #0x711  ; "%srep_gamedata%d.dat"
003faa7c  910003e0  mov        x0, sp
003faa80  52808001  mov        w1, #0x400              // =1024
003faa84  2a1303e4  mov        w4, w19
003faa88  9409dbae  bl         0x671940 <.text+0x276f18>  ; import snprintf
003faa8c  910003e1  mov        x1, sp
003faa90  aa1503e0  mov        x0, x21
003faa94  940a0893  bl         0x67cce0 <.text+0x2822b8>  ; import _ZN15IsaacRepentance18PersistentGameData4LoadEPKc
003faa98  36000160  tbz        w0, #0x0, 0x3faac4 <.text+0x9c>
003faa9c  d0003588  adrp       x8, 0xaac000 <.text+0x6b15d8>
003faaa0  f9432508  ldr        x8, [x8, #0x648]  ; _ZN15IsaacRepentance9g_ManagerE
003faaa4  f9400108  ldr        x8, [x8]
003faaa8  528ca309  mov        w9, #0x6518             // =25880
003faaac  72a00069  movk       w9, #0x3, lsl #16
003faab0  aa1403e0  mov        x0, x20
003faab4  2a1303e1  mov        w1, w19
003faab8  3829691f  strb       wzr, [x8, x9]
003faabc  940a088d  bl         0x67ccf0 <.text+0x2822c8>  ; import _ZN15IsaacRepentance7Manager13LoadGameStateENS0_9eSaveSlotE
003faac0  14000007  b          0x3faadc <.text+0xb4>  ; -> ~_ZN15IsaacRepentance7Manager11SetSaveSlotENS0_9eSaveSlotE+0xb4
003faac4  913dc280  add        x0, x20, #0xf70
003faac8  9409fe0e  bl         0x67a300 <.text+0x27f8d8>  ; import _ZN15IsaacRepentance9GameState5ClearEv
003faacc  b0002481  adrp       x1, 0x88b000 <.text+0x4905d8>
003faad0  913dcc21  add        x1, x1, #0xf73
003faad4  2a1f03e0  mov        w0, wzr
003faad8  9409d47a  bl         0x66fcc0 <.text+0x275298>  ; import KAGE_LogMessage
003faadc  b9001293  str        w19, [x20, #0x10]
003faae0  911003ff  add        sp, sp, #0x400
003faae4  a9424ff4  ldp        x20, x19, [sp, #0x20]
003faae8  a94157fc  ldp        x28, x21, [sp, #0x10]
003faaec  a8c37bfd  ldp        x29, x30, [sp], #0x30
003faaf0  d65f03c0  ret        
003faaf4  a9bc7bfd  stp        x29, x30, [sp, #-0x40]!
003faaf8  a9015ffc  stp        x28, x23, [sp, #0x10]
003faafc  910003fd  mov        x29, sp
003fab00  a90257f6  stp        x22, x21, [sp, #0x20]
003fab04  a9034ff4  stp        x20, x19, [sp, #0x30]
003fab08  d11003ff  sub        sp, sp, #0x400
003fab0c  913dc013  add        x19, x0, #0xf70
003fab10  aa0003f4  mov        x20, x0
003fab14  aa1303e0  mov        x0, x19
