/* 内部挂点：x16必须由调用方证明死值，其余GPR/完整SIMD/系统浮点状态保存。 */
.section .text.isaac_internal_hook_context, "ax", %progbits
.global isaac_internal_hook_context
.type isaac_internal_hook_context, %function
.align 2
isaac_internal_hook_context:
    sub sp, sp, #0x340
    stp x0, x1, [sp, #0x00]
    stp x2, x3, [sp, #0x10]
    stp x4, x5, [sp, #0x20]
    stp x6, x7, [sp, #0x30]
    stp x8, x9, [sp, #0x40]
    stp x10, x11, [sp, #0x50]
    stp x12, x13, [sp, #0x60]
    stp x14, x15, [sp, #0x70]
    str xzr, [sp, #0x80]
    str x17, [sp, #0x120]
    ldr x16, [sp, #0x340]
    str x16, [sp, #0x88]
    stp x18, x19, [sp, #0x90]
    stp x20, x21, [sp, #0xA0]
    stp x22, x23, [sp, #0xB0]
    stp x24, x25, [sp, #0xC0]
    stp x26, x27, [sp, #0xD0]
    stp x28, x29, [sp, #0xE0]
    ldr x16, [sp, #0x348]
    str x16, [sp, #0xF0]
    add x16, sp, #0x350
    str x16, [sp, #0xF8]
    mrs x16, nzcv
    str x16, [sp, #0x100]
    mrs x16, fpcr
    str x16, [sp, #0x108]
    mrs x16, fpsr
    str x16, [sp, #0x110]
    stp q0, q1, [sp, #0x140]
    stp q2, q3, [sp, #0x160]
    stp q4, q5, [sp, #0x180]
    stp q6, q7, [sp, #0x1A0]
    stp q8, q9, [sp, #0x1C0]
    stp q10, q11, [sp, #0x1E0]
    stp q12, q13, [sp, #0x200]
    stp q14, q15, [sp, #0x220]
    stp q16, q17, [sp, #0x240]
    stp q18, q19, [sp, #0x260]
    stp q20, q21, [sp, #0x280]
    stp q22, q23, [sp, #0x2A0]
    stp q24, q25, [sp, #0x2C0]
    stp q26, q27, [sp, #0x2E0]
    stp q28, q29, [sp, #0x300]
    stp q30, q31, [sp, #0x320]
    mov x0, sp
    bl isaac_internal_hook_dispatch
    ldr x16, [sp, #0x100]
    msr nzcv, x16
    ldr x16, [sp, #0x108]
    msr fpcr, x16
    ldr x16, [sp, #0x110]
    msr fpsr, x16
    ldp q0, q1, [sp, #0x140]
    ldp q2, q3, [sp, #0x160]
    ldp q4, q5, [sp, #0x180]
    ldp q6, q7, [sp, #0x1A0]
    ldp q8, q9, [sp, #0x1C0]
    ldp q10, q11, [sp, #0x1E0]
    ldp q12, q13, [sp, #0x200]
    ldp q14, q15, [sp, #0x220]
    ldp q16, q17, [sp, #0x240]
    ldp q18, q19, [sp, #0x260]
    ldp q20, q21, [sp, #0x280]
    ldp q22, q23, [sp, #0x2A0]
    ldp q24, q25, [sp, #0x2C0]
    ldp q26, q27, [sp, #0x2E0]
    ldp q28, q29, [sp, #0x300]
    ldp q30, q31, [sp, #0x320]
    ldp x0, x1, [sp, #0x00]
    ldp x2, x3, [sp, #0x10]
    ldp x4, x5, [sp, #0x20]
    ldp x6, x7, [sp, #0x30]
    ldp x8, x9, [sp, #0x40]
    ldp x10, x11, [sp, #0x50]
    ldp x12, x13, [sp, #0x60]
    ldp x14, x15, [sp, #0x70]
    ldr x17, [sp, #0x88]
    ldp x18, x19, [sp, #0x90]
    ldp x20, x21, [sp, #0xA0]
    ldp x22, x23, [sp, #0xB0]
    ldp x24, x25, [sp, #0xC0]
    ldp x26, x27, [sp, #0xD0]
    ldp x28, x29, [sp, #0xE0]
    ldr x30, [sp, #0xF0]
    ldr x16, [sp, #0x118]
    add sp, sp, #0x350
    br x16
.size isaac_internal_hook_context, .-isaac_internal_hook_context
