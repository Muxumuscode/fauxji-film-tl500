import sys, math, re, collections
def ent(b):
    c=collections.Counter(b); n=len(b)
    return -sum(v/n*math.log2(v/n) for v in c.values()) if n else 0
for p in sys.argv[1:]:
    d=open(p,'rb').read(); print('==',p,len(d),'entropy %.3f'%ent(d))
    step=max(len(d)//16,1)
    print('  per-block:',' '.join('%.1f'%ent(d[i:i+step]) for i in range(0,len(d),step)))
    s=re.findall(rb'[\x20-\x7e]{8,}',d); print('  strings:',len(s))
    for x in s[:12]: print('   ',x[:90].decode())
    print('  keywords:',{k:len(re.findall(k,d,re.I)) for k in [b'ITRON',b'VxWorks',b'ThreadX',b'Linux',b'Samsung',b'RSA',b'CRC',b'MD5',b'SHA']})
