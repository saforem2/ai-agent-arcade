;redcode-94
;name Iron Lotus Gate
;author KIMI
;strategy mod-1 stone + imp gate + 8-process imp spiral
step    equ 2367
first   equ 4100
        org start
start   spl gate
        spl spiral
stone   mov.i bomb, @sptr
        add.ab #step, sptr
        jmp stone
sptr    dat #0, #first
bomb    dat #0, #0
gate    mov.i gbomb, 2667
        jmp gate
gbomb   dat #0, #0
spiral  spl 1
        spl 1
        spl 1
imp     mov.i $0, $1
