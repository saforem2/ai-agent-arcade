;redcode-94
;name Twin Ember
;author KIMI
;strategy two mod-1 bomb loops and an imp tail
        org     start
start   spl     imp,     0
        spl     loop2,   0
loop1   mov.i   bomb,   @p1
        add.ab  #2367,  p1
        jmp     loop1,  0
loop2   mov.i   bomb,   @p2
        add.ab  #1271,  p2
        jmp     loop2,  0
p1      dat     #0,     #0
p2      dat     #0,     #4000
bomb    dat     #0,     #0
imp     mov.i   $0,     $1
        end
