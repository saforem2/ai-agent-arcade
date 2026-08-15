;redcode-94
;name Blue Fugue
;author CODEX
;strategy Two interleaved silk waves with a disruptive field clear.
;strategy Wide replication, redundant processes, and anti-imp bombs.

TSTEP   equ     1801
CSTEP   equ     3741
NSTEP   equ     -1921
FSTEP   equ     1871

        org     boot

boot    spl     1,          <300
        spl     1,          <1500
        mov.i   -1,         0

silk1   spl     @silk1,     }TSTEP
        mov.i   }silk1,     >silk1
silk2   spl     @silk2,     }CSTEP
        mov.i   }silk2,     >silk2
        mov.i   bomb,       >bomb
        mov.i   {silk2,     <silk2
        mov.i   {silk1,     <silk1
        djn.f   @silk1,     <NSTEP

bomb    dat.f   >2667,      >5334

        end     boot
