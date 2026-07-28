import struct
def parse(path, ssfilter=None):
    raw=open(path,'rb').read()
    def unesc(r):
        u=bytearray();e=False
        for b in r:
            if e:u.append(b^0x20);e=False
            elif b==0x7d:e=True
            else:u.append(b)
        return bytes(u)
    out=[]
    for f in raw.split(b'\x7e'):
        if not f: continue
        p=unesc(f)[:-2]
        if len(p)<20 or p[0] not in (0x79,0x92): continue
        n=p[2];line=struct.unpack_from('<H',p,12)[0];ss=struct.unpack_from('<H',p,14)[0]
        ts=struct.unpack_from('<Q',p,4)[0]
        if ssfilter is not None and ss!=ssfilter: continue
        base = 20 if p[0]==0x79 else 24
        args=[]
        for i in range(n):
            o=base+4*i
            if o+4>len(p): break
            args.append(struct.unpack_from('<I',p,o)[0])
        if p[0]==0x79:
            parts=p[20+4*n:].split(b'\x00')
            fmt=parts[0].decode('ascii','replace') if parts else ''
            fn=parts[1].decode('ascii','replace') if len(parts)>1 else ''
        else:
            fmt=None; fn=''
        out.append((ts,ss,line,fn,fmt,args))
    return sorted(out)
