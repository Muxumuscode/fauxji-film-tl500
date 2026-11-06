"""Tiny ARM32 interpreter (only the instructions the tilt code uses) that runs the real emitted words of fauxji_rot's sky
routines (skyori + skycol) on random AE grids and compares with a Python reference. Run from the project root:
    python tools/test_sky.py
Prints "bad 0" when the machine code matches the reference and leaves r4-r11 and the stack as it found them."""
import sys,struct,random
sys.path.insert(0,'tools')
import capstone as cs
from capstone.arm import *
import fauxji_rot as R
M32=0xFFFFFFFF
class CPU:
    def __init__(s,blobs):
        s.mem={}; s.stubs={}
        for base,b in blobs:
            for i in range(0,len(b),4): s.set32(base+i,struct.unpack_from('<I',b,i)[0])
        s.r=[0]*16; s.N=s.Z=s.C=s.V=0
        s.md=cs.Cs(cs.CS_ARCH_ARM,cs.CS_MODE_ARM); s.md.detail=True; s.cache={}
    def set32(s,a,v):
        for k in range(4): s.mem[a+k]=(v>>(8*k))&255
    def get32(s,a): return sum(s.mem.get(a+k,0)<<(8*k) for k in range(4))
    def get16(s,a): return s.mem.get(a,0)|(s.mem.get(a+1,0)<<8)
    def cond(s,c):
        N,Z,C,V=s.N,s.Z,s.C,s.V
        return {ARM_CC_EQ:Z,ARM_CC_NE:not Z,ARM_CC_HS:C,ARM_CC_LO:not C,ARM_CC_MI:N,ARM_CC_PL:not N,ARM_CC_HI:C and not Z,ARM_CC_LS:(not C) or Z,
                ARM_CC_GE:N==V,ARM_CC_LT:N!=V,ARM_CC_GT:(not Z) and N==V,ARM_CC_LE:Z or N!=V,ARM_CC_AL:1}[c]
    def val(s,op,pc):
        if op.type==ARM_OP_IMM: return op.imm&M32
        v=pc+8 if op.reg==ARM_REG_PC else s.r[s.ri(op.reg)]
        if op.shift.type:
            n=op.shift.value
            if op.shift.type==ARM_SFT_LSL: v=(v<<n)&M32
            elif op.shift.type==ARM_SFT_LSR: v=v>>n
            else: raise Exception('shift')
        return v
    def ri(s,reg):
        names={ARM_REG_SP:13,ARM_REG_LR:14,ARM_REG_PC:15,ARM_REG_IP:12,ARM_REG_FP:11,ARM_REG_SL:10,ARM_REG_SB:9}
        if reg in names: return names[reg]
        return reg-ARM_REG_R0
    def run(s,entry,ret=0xDEAD0000,limit=100000,lr=None):
        s.r[15]=entry; s.r[14]=ret if lr is None else lr; s.r[13]=0x10000000
        n=0
        while s.r[15]!=ret:
            n+=1; assert n<limit,'runaway'
            pc=s.r[15]
            if pc in s.stubs:                       # an outside function: python stand-in, then return to lr
                if s.stubs[pc](s)=='stop': return s
                s.r[15]=s.r[14]; continue
            w=s.get32(pc)
            if pc not in s.cache: s.cache[pc]=next(s.md.disasm(struct.pack('<I',w),pc))
            i=s.cache[pc]; ops=i.operands; s.r[15]=pc+4
            if not s.cond(i.cc): continue
            m=i.mnemonic.split('.')[0]
            for suf in ('eq','ne','hs','lo','ls','hi','ge','lt','gt','le','mi','pl'):
                pass
            base=m
            import re
            mm=re.match(r'^(push|pop|stmdb|ldm|mvn|mov|add|cmp|ldrh|ldr|strh|str|tst|umull|orr|sub|and|lsl|lsr)',m); base=mm.group(1) if mm else None
            if i.id==ARM_INS_B: base='b'
            if i.id==ARM_INS_BL: base='bl'
            if i.id==ARM_INS_LSL: base='lsl'
            if i.id==ARM_INS_LSR: base='lsr'
            if base=='stmdb': base='push'
            if base=='ldm': base='pop'
            if base=='push':
                for op in sorted([o for o in ops],key=lambda o:-s.ri(o.reg)):
                    s.r[13]-=4; s.set32(s.r[13],s.r[s.ri(op.reg)] if s.ri(op.reg)!=15 else pc+8)
            elif base=='pop':
                for op in sorted(ops,key=lambda o:s.ri(o.reg)):
                    v=s.get32(s.r[13]); s.r[13]+=4
                    s.r[s.ri(op.reg)]=v if s.ri(op.reg)!=15 else v
            elif base=='mvn':
                s.r[s.ri(ops[0].reg)]=(~s.val(ops[1],pc))&M32
            elif base in('mov','add','orr','sub') and m.endswith('s') and base in('add','sub') and i.update_flags:
                rd=s.ri(ops[0].reg); a,b=s.val(ops[1],pc),s.val(ops[2],pc)
                res=((a-b) if base=='sub' else (a+b))&M32
                s.N=res>>31; s.Z=res==0
                s.C=(a>=b) if base=='sub' else (a+b>M32)
                s.V=(((a^b)&(a^res))>>31) if base=='sub' else ((~(a^b)&(a^res))>>31)&1
                s.r[rd]=res
            elif base in('mov','add','orr','sub'):
                rd=s.ri(ops[0].reg)
                if base=='mov': v=s.val(ops[1],pc)
                elif base=='add': v=(s.val(ops[1],pc)+s.val(ops[2],pc))&M32
                elif base=='sub': v=(s.val(ops[1],pc)-s.val(ops[2],pc))&M32
                else: v=s.val(ops[1],pc)|s.val(ops[2],pc)
                s.r[rd]=v
            elif base=='tst':
                res=s.val(ops[0],pc)&s.val(ops[1],pc); s.N=res>>31; s.Z=res==0
            elif base=='cmp':
                a,b=s.val(ops[0],pc),s.val(ops[1],pc); res=(a-b)&M32
                s.N=res>>31; s.Z=res==0; s.C=a>=b; s.V=((a^b)&(a^res))>>31
            elif base in('ldr','ldrh','str','strh'):
                mo=ops[1].mem; 
                base_v=pc+8 if mo.base==ARM_REG_PC else s.r[s.ri(mo.base)]
                a=(base_v+mo.disp)&M32
                if mo.index!=0: a=(base_v+s.r[s.ri(mo.index)])&M32
                if base=='strh':
                    v=s.r[s.ri(ops[0].reg)]; s.mem[a]=v&255; s.mem[a+1]=(v>>8)&255
                elif base=='str': s.set32(a,s.r[s.ri(ops[0].reg)])
                else: s.r[s.ri(ops[0].reg)]=s.get32(a) if base=='ldr' else s.get16(a)
            elif base=='umull':
                p=s.r[s.ri(ops[2].reg)]*s.r[s.ri(ops[3].reg)]
                s.r[s.ri(ops[0].reg)]=p&M32; s.r[s.ri(ops[1].reg)]=p>>32
            elif base in('lsl','lsr'):
                s.r[s.ri(ops[0].reg)]=s.val(ops[1],pc)
            elif base in('b','bl'):
                if base=='bl': s.r[14]=pc+4
                s.r[15]=ops[0].imm&M32
            else: raise Exception('unsupported '+i.mnemonic+' '+i.op_str)
        return s
def make(grid_y,grid_r,grid_b):
    blobs,lab=R.build_full()
    c=CPU(blobs)
    for plane,off in ((grid_y,0),(grid_r,0x1BA),(grid_b,0x52E)):
        for k,v in enumerate(plane): 
            a=R.YGRID+off+2*k; c.mem[a]=v&255; c.mem[a+1]=v>>8
    return c,lab
def ref_sky(Y,Rr,Bb,color=True):
    cells=lambda P,rows,cols:sum(P[r*17+c] for r in rows for c in cols)
    L=cells(Y,range(13),(0,1))*17; Rt=cells(Y,range(13),(15,16))*17
    T=cells(Y,(0,1),range(17))*13; Bo=cells(Y,(11,12),range(17))*13
    tag=0
    for side,other,t in ((L,Rt,6),(Rt,L,8)):
        if 2*side<=3*other: continue
        if 8*side<=9*T: continue
        if 8*side<=9*Bo: continue
        tag=t; break
    if tag and color:
        co,oo=((0,15) if tag==6 else (15,0))
        def band(P,c0): return cells(P,range(13),(c0,c0+1))
        rc,bc,ro,bo_=band(Rr,co),band(Bb,co),band(Rr,oo),band(Bb,oo)
        if 8*bc*ro < 9*bo_*rc: tag=0
    return tag
def test_latch():
    # live-view draw (combo, Auto+) stores the sky guess; the EXIF stub then uses the latch, not the grid at write time
    def grid(side):
        Y=[100]*221
        for r in range(13):
            for c in ((0,1) if side=='l' else (15,16)): Y[r*17+c]=900
        return Y
    c,lab=make(grid('l'),[100]*221,[100]*221)
    c.r[1]=2; c.set32(R.FACE_ORI,0)
    c.run(lab['combo'],ret=0xDEAD0000); assert c.r[2]==6 and c.get32(R.SKY_LATCH)==6,(c.r[2],c.get32(R.SKY_LATCH))
    # now the grid changes (after the shot): the writer still reports the latched 6
    c2,lab2=make(grid('r'),[100]*221,[100]*221)
    c2.mem=dict(c.mem)                                   # keep the latch, replace the grid
    for k,v in enumerate(grid('r')):
        a=R.YGRID+2*k; c2.mem[a]=v&255; c2.mem[a+1]=v>>8
    c2.set32(R.STATE,2); c2.set32(R.FACE_ORI,0); c2.r[14]=1; c2.r[3]=0xDEAD0000; c2.r[0]=0x77
    c2.run(lab2['wcommon'],ret=0xDEAD0000,lr=1); assert c2.r[14]==6 and c2.r[0]==0x77,(c2.r[14],hex(c2.r[0]))
    # latch 0 = no tag (stock value kept)
    c2.set32(R.SKY_LATCH,0); c2.r[3]=0xDEAD0000; c2.run(lab2['wcommon'],ret=0xDEAD0000,lr=1); assert c2.r[14]==1,c2.r[14]
    # a sideways face still wins over the latch
    c2.set32(R.SKY_LATCH,6); c2.set32(R.FACE_ORI,8); c2.r[3]=0xDEAD0000; c2.run(lab2['wcommon'],ret=0xDEAD0000,lr=1); assert c2.r[14]==8
    print('latch: live guess stored, writer uses it, face still wins: ok')


def test_gates():
    # movie-mode gates in front of the name / tilt box (top left corner = where the movie timer shows)
    def setup(mode):
        c,lab=make([100]*221,[100]*221,[100]*221)
        log=[]
        c.stubs[R.GET_SYSVAL]=lambda cpu: (cpu.r.__setitem__(0,mode) or None)
        c.stubs[R.ui.ITEM44_DRAW]=lambda cpu: log.append(('item44',cpu.r[0]))
        for name,a in (('tf4',R.ui.TILT_FORCE+4),('td4',R.ui.TILT_DRAW+4),('t4',R.ui.TOAST_CODE+4)):
            c.stubs[a]=(lambda n: lambda cpu: (log.append((n,cpu.r[0],cpu.r[1])) or 'stop'))(name)
        return c,lab,log
    for mode,movie in ((8,True),(0,False),(4,False),(9,False)):
        for gate,tag in (('gate1','tf4'),('gate2','td4'),('gate3','t4')):
            c,lab,log=setup(mode)
            c.r[0]=0x55; c.r[1]=7; c.r[4]=0x44
            c.run(lab[gate],ret=0xDEAD0000,lr=0xDEAD0000)
            if movie:
                want=[] if gate=='gate3' else [('item44',0)]
                assert log==want and c.r[15]==0xDEAD0000 and c.r[13]==0x10000000,(mode,gate,log,hex(c.r[15]))
            else:
                assert log and log[-1][0]==tag,(mode,gate,log)
                if gate=='gate1': assert log[-1][2]==0xFFFFFFFF
                if gate=='gate2':   # push {r0,r4,lr} done, r0 intact
                    assert c.r[13]==0x10000000-12 and c.get32(c.r[13])==0x55
                if gate=='gate3': assert c.r[13]==0x10000000-8
    print('movie gates: hidden/skipped in movie mode, normal path otherwise: ok')


def test_roll():
    import random
    random.seed(3); bad=0
    for t in range(2000):
        n=random.choice((0,24,36)); cnt=random.randint(0,60); real=random.choice((0,1,5,23,24,35,36,37,120,5000,random.randint(0,99999)))
        c,lab=make([100]*221,[100]*221,[100]*221)
        c.set32(R.ROLL_COUNT,cnt); c.set32(R.ROLL_N,n)
        c.r[0]=real
        c.run(lab['rollclamp'],ret=R.ROLL_BACK)
        exp=real if n==0 else min(real,max(n-cnt,0))
        if c.r[0]!=exp or c.r[13]!=0x10000000+0x58: bad+=1; print('ROLL MISMATCH',n,cnt,real,c.r[0],exp)
    print('roll cases 2000 bad',bad)
    # the EXIF stub counts one frame per call and keeps r0
    for st in (0,1,2,3,4):
        c,lab=make([100]*221,[100]*221,[100]*221)
        c.set32(R.STATE,st); c.set32(R.ROLL_COUNT,5); c.r[0]=0x1234; c.r[3]=0xDEAD0000
        c.run(lab['wcommon'],ret=0xDEAD0000,lr=1)
        assert c.get32(R.ROLL_COUNT)==6 and c.r[0]==0x1234,(st,c.get32(R.ROLL_COUNT),hex(c.r[0]))
    print('wcommon counts 1 per call, state 0-4 ok')


if __name__=='__main__':
    test_latch()
    test_gates()
    test_roll()
    random.seed(7); bad=0; stats={0:0,6:0,8:0}
    for t in range(1500):
        mode=random.choice(('sky_l','sky_r','lamp','flat','rand','dark'))
        Y=[random.randint(50,300) for _ in range(221)]; Rr=[random.randint(50,300) for _ in range(221)]; Bb=[random.randint(50,300) for _ in range(221)]
        if mode in('sky_l','sky_r','lamp'):
            cols=(0,1) if mode!='sky_r' else (15,16)
            for r in range(13):
                for c in cols:
                    Y[r*17+c]+=random.randint(800,1500)
                    if mode=='lamp': Rr[r*17+c]+=1000; Bb[r*17+c]+=random.randint(300,700)
                    else: Bb[r*17+c]+=1000; Rr[r*17+c]+=random.randint(100,300)
        if mode=='dark': Y=[random.randint(0,4) for _ in range(221)]; Rr=[0]*221; Bb=[0]*221
        if mode=='flat': Y=[200]*221; Rr=[100]*221; Bb=[100]*221
        for P in (Y,Rr,Bb): 
            for k in range(221): P[k]=min(P[k],65535)
        c,lab=make(Y,Rr,Bb)
        sp=0x10000000
        regs_before=None
        c.r[4:12]=[0xA4,0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xAB]; keep=c.r[4:12][:]
        c.run(lab['skyori']); got=c.r[0]
        exp=ref_sky(Y,Rr,Bb,color=R.SKY_COLOUR_CHECK)
        # callee-saved regs and stack restored
        if c.r[4:12]!=keep or c.r[13]!=0x10000000: print('REGS/STACK CLOBBERED',mode,c.r[4:12],hex(c.r[13])); bad+=1
        if got!=exp: bad+=1; print('MISMATCH',mode,got,exp)
        stats[got]+=1
    print('cases 1500 bad',bad,'tags',stats)
