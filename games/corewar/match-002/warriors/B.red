;redcode-94
;name Blue Shift
;author CODEX
;strategy Eight-process silk with two displaced DAT trails.

STEP    EQU     1951
BSTEP   EQU     3109
ASTEP   EQU     5351

        ORG     boot

boot    SPL     $1,     <-300
        MOV.I   $-1,    $0
        MOV.I   $-1,    $0
        MOV.I   $-1,    $0

silk    SPL     @0,     }STEP
        MOV.I   }-1,    >-1
        MOV.I   bomb,   >bptr
        MOV.I   bomb,   }aptr
die     DAT.F   $0,     $0
bptr    DAT.F   $0,     $BSTEP
aptr    DAT.F   $ASTEP, $0
bomb    DAT.F   <2667,  <5334

; A distant false body gives one-shot scanners something harmless to find.
gap     FOR     35
        DAT.F   $0,     $0
        ROF
bait    FOR     53
        DAT.F   #bait,  #-bait
        ROF

        END     boot
