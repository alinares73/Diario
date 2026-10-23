#!/usr/bin/env python3
"""
isilo2html.py - Convierte un ebook iSilo 3.x/4.x (.pdb, SDoc/SilX) a HTML con
formato, hiperenlaces internos y marcadores.

Reconstruido por ingenieria inversa de iSilo.exe. Ver isilo2txt.py para el
descompresor y las notas del formato.

Uso:  python isilo2html.py libro.pdb [salida.html]
"""
import struct, sys, os, html, re

from isilo2txt import read_records, decompress_record

def be16(b,o): return struct.unpack('>H', b[o:o+2])[0]
def be32(b,o): return struct.unpack('>I', b[o:o+4])[0]

# ---------------------------------------------------------------- contenedor

class Sec2:
    """Tabla de tramos: parte un rango de texto en N tramos con un valor cada uno."""
    def __init__(s, rec):
        h=rec[0]; s.rec=rec
        s.hdrsize=rec[h]; s.kind=rec[h+1]; s.flags=rec[h+2]; s.sub=rec[h+3]
        s.aoff=be16(rec,h+4); s.n=be16(rec,h+6)
        s.start=be32(rec,h+8); s.end=be32(rec,h+12)
        P=h+s.hdrsize; n=s.n; dm=s.flags&3
        lens=[]
        if dm==0:
            lens=[rec[P+i]+1 for i in range(n-1)]
        elif dm==1:
            ext=P+(n-1); j=0
            for i in range(n-1):
                b=rec[P+i]
                if b&0x80: lens.append((b&0x7f)+1+rec[ext+j]*0x80); j+=1
                else: lens.append(b+1)
        elif dm==2:
            lens=[be16(rec,P+2*i)+1 for i in range(n-1)]
        else:
            ext=P+2*(n-1); j=0
            for i in range(n-1):
                v=be16(rec,P+2*i)
                if v&0x8000: lens.append((v&0x7fff)+1+be16(rec,ext+2*j)*0x8000); j+=1
                else: lens.append(v+1)
        s.ranges=[]; p=s.start
        for L in lens: s.ranges.append((p,p+L)); p+=L
        s.ranges.append((p,s.end))
        # bloque de valores
        A=s.aoff; s.blob=None
        if s.kind==2:
            s.blob=(rec[A], rec[A+1], be16(rec,A+2)); A+=rec[A]
        s.values=_vals(rec,A,n,s.flags>>2 & 3)
        s.targets=None
        if s.kind==2:
            s.targets=_vals(rec, s.aoff+s.blob[2], n, rec[h+3]&3)

def _vals(rec, base, n, enc):
    out=[]
    if enc==0:
        out=[rec[base+i] for i in range(n)]
    elif enc==1:
        ext=base+n; j=0
        for i in range(n):
            b=rec[base+i]
            if b&0x80: out.append((b&0x7f)|(rec[ext+j]<<7)); j+=1
            else: out.append(b)
    elif enc==2:
        out=[be16(rec,base+2*i) for i in range(n)]
    else:
        ext=base+2*n; j=0
        for i in range(n):
            v=be16(rec,base+2*i)
            if v&0x8000: out.append((v&0x7fff)|(be16(rec,ext+2*j)<<15)); j+=1
            else: out.append(v)
    return out

def sec1_tables(recs):
    out={}
    for r in recs:
        if len(r)<6 or r[1]!=1: continue
        d=r[r[0]:]; tid=d[1]; cnt=be32(d,2)+1; pl=d[d[0]:]
        if tid==0:   out[tid]=[be16(pl,2*i) for i in range(cnt)]
        elif tid==1: out[tid]=[be32(pl,4*i)&0xffffff for i in range(cnt)]
        else:
            a=be16(pl,0); arr1=pl[4:4+a]
            w=a//cnt if cnt and a%cnt==0 else 0
            out[tid]=[arr1[i*w:(i+1)*w] for i in range(cnt)] if w else [arr1]
    return out


def section6_dir(recs, hdr):
    """Directorio de la seccion 6: {kind: {noff, bpe, extA, extB, first, nrec}}."""
    try:
        r = recs[hdr['single'][0]]
        if r[1] != 6: return {}
        d = r[r[0]:]
    except Exception:
        return {}
    sub, n, base = d[0], d[2], d[3]
    out = {}; p = sub
    for _ in range(n):
        e = d[p:]
        if len(e) < base + 2: break
        sz = ((e[1] + 2) & ~1) + base
        out[e[0]] = dict(noff=e[1], perrec=be16(e,2), first=be16(e,4),
                         nrec=be16(e,6), bpe=e[8],
                         extA=e[9] if sz >= 10 else 0,
                         extB=e[10] if sz >= 12 else 0)
        p += sz
    return out


def sec1_via_dir(recs, dirs, tid):
    """Lee la tabla `tid` de la seccion 1 con el numero REAL de offsets de
    cabecera, que viene del directorio de la seccion 6.  La tabla 6 (estilos
    de parrafo) tiene TRES, no dos: leerla a ojo desplaza dos bytes."""
    D = dirs.get(tid)
    if not D: return None
    ri = D['first']
    if ri >= len(recs) or recs[ri][1] != 1: return None
    d = recs[ri][recs[ri][0]:]
    cnt = struct.unpack('>I', d[2:6])[0] + 1
    pl = d[d[0]:]
    ev = 2 * D['noff']; w = D['bpe']
    return [pl[ev + i*w: ev + (i+1)*w] for i in range(cnt)]


def doc_header(r):
    h={'textlen':be32(r,0x14),'ndiv':be32(r,0x1c),
       'bm':(be16(r,0x20),be16(r,0x22))}
    # El directorio de flujos NO empieza siempre en 0x80: su posicion es el
    # tamano de la parte fija, declarado en los dos primeros bytes. Hay libros
    # con cabecera corta (p.ej. 0x40) de versiones antiguas de iSiloX.
    p=be16(r,0)
    if not (0x24 <= p <= len(r)-4):
        p=0x80
    h['hdrsize']=p
    ns=be16(r,p); p+=2
    h['single']=[be16(r,p+2*i) for i in range(ns)]; p+=2*ns
    nm=be16(r,p); p+=2
    first=[be16(r,p+2*i) for i in range(nm)]; p+=2*nm
    cnt=[be16(r,p+2*i) for i in range(nm)]
    h['streams']=list(zip(first,cnt))
    return h

def decode_name(b, enc='cp1252'):
    """Los nombres de marcador van en la codificacion del documento, que no
    tiene por que ser UTF-8. Se prueba UTF-8 estricto y, si no cuela, la del
    documento: asi acierta en los dos casos sin depender de la deteccion."""
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return b.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return b.decode('latin-1', 'replace')


def parse_bookmarks(rec, enc='cp1252'):
    try:
        so,cnt,sl = be16(rec,0), be16(rec,4), be16(rec,6)
        names=[]; p=so
        for _ in range(cnt):
            e=rec.index(b'\0',p); names.append(decode_name(rec[p:e], enc)); p=e+1
        off=so+((sl+1)&~1)
        return [(names[i], be32(rec,off+4*i)) for i in range(cnt)]
    except Exception:
        return []

def classify(v):
    if (v & 0xC0000000)==0: return ('text', v)
    if (v & 0xFFFF0000)==0x7FF00000: return ('menu', v&0xFFFF)
    if (v & 0xFFFF0000)==0x7FF10000: return ('imagemap', v&0xFFFF)
    if (v & 0xFF000000)==0x70000000: return ('vcalendar', v&0xFFFFFF)
    if (v & 0xFF000000)==0x71000000: return ('vcard', v&0xFFFFFF)
    if (v & 0xF0000000) in (0x40000000,0x50000000): return ('document', v&0x0FFFFFFF)
    return ('unknown', v)

# ------------------------------------------------------------------ modelo

class Book:
    def __init__(s, path):
        s.recs=read_records(path)
        s.raw=b''.join(decompress_record(r)[1] for r in s.recs
                       if len(r)>8 and r[0]>=4 and r[1]==0)
        s.enc='utf-8'
        try: s.raw.decode('utf-8')
        except UnicodeDecodeError: s.enc='cp1252'
        s.hdr=doc_header(s.recs[0])
        t1=sec1_tables(s.recs)
        s.fonts=t1.get(0,[]); s.colors=t1.get(1,[])
        s.para_tab=t1.get(6,[]); s.char_tab=t1.get(7,[])
        s.dirs=section6_dir(s.recs, s.hdr)
        fixed=sec1_via_dir(s.recs, s.dirs, 6)
        if fixed: s.para_tab=fixed
        fixed=sec1_via_dir(s.recs, s.dirs, 7)
        if fixed: s.char_tab=fixed
        s.para=s._stream(2); s.char=s._stream(3); s.links=s._stream(5)
        # tamano de fuente dominante = base tipografica del documento
        w={}
        for t in s.char:
            for (a,bb),v in zip(t.ranges,t.values):
                if v and v-1 < len(s.char_tab):
                    fi=s.char_tab[v-1][2]
                    if fi and fi-1 < len(s.fonts):
                        w[s.fonts[fi-1]&0xff]=w.get(s.fonts[fi-1]&0xff,0)+(bb-a)
        s.base=max(w,key=w.get) if w else 12
        s.bookmarks=[]
        for ri in s.hdr['bm']:
            if 0 <= ri < len(s.recs): s.bookmarks += parse_bookmarks(s.recs[ri], s.enc)

    def _stream(s,i):
        first,cnt = s.hdr['streams'][i] if i < len(s.hdr['streams']) else (0,0)
        return [Sec2(s.recs[first+k]) for k in range(cnt)] if cnt else []

    def runs(s, streams):
        for t in streams:
            for (a,b),v in zip(t.ranges,t.values): yield a,b,v

    def linklist(s):
        out=[]
        for t in s.links:
            for (a,b),ln,tg in zip(t.ranges,t.values,t.targets):
                if ln: out.append((a,a+ln,tg))
        return out

# -------------------------------------------------------------------- HTML

def css_char(book, idx):
    if not idx or idx-1 >= len(book.char_tab): return None
    e=book.char_tab[idx-1]
    f1,f2,fi,ci = e[0],e[1],e[2],e[3]
    tags=[]
    if f1&0x04: tags.append('b')
    if f1&0x01: tags.append('i')
    if f1&0x02: tags.append('u')
    if f2&0x08: tags.append('s')
    if f2&0x10: tags.append('sub')
    if f2&0x20: tags.append('sup')
    st=[]
    if fi and fi-1 < len(book.fonts):
        fv=book.fonts[fi-1]; fam=fv>>8; size=fv&0xff
        if size and size!=book.base: st.append('font-size:%.2fem'%(size/float(book.base)))
        if fam==1: st.append('font-family:monospace')
    if ci and ci-1 < len(book.colors):
        st.append('color:#%06x'%book.colors[ci-1])
    return tags, ';'.join(st), bool(f1&0x08)

def convert(path, out_path=None, title=None):
    b=Book(path)
    raw=b.raw
    links=b.linklist()
    link_start={a:(e,t) for a,e,t in links}
    targets=sorted({v for a,e,t in links for k,v in [classify(t)] if k=='text'})
    targets_set=set(targets)
    # estilos de parrafo por offset
    pruns=sorted(b.runs(b.para)); cruns=sorted(b.runs(b.char))
    def find(runs, pos):
        lo,hi=0,len(runs)-1; r=None
        while lo<=hi:
            m=(lo+hi)//2
            if runs[m][0]<=pos<runs[m][1]: return runs[m][2]
            if pos<runs[m][0]: hi=m-1
            else: lo=m+1
        return 0

    # --- recoger parrafos ---
    paras=[]; p=0; N=len(raw)
    while p<=N:
        q=raw.find(b'\n',p)
        if q<0: q=N
        st=find(pruns,p) if p<N else 0
        e=b.para_tab[st-1] if st and st-1<len(b.para_tab) else None
        paras.append({'a':p,'b':q,
                      'align':((e[0] & 3) if e else 0),
                      'li':bool(e[1]) if e else False,
                      'cell':bool(e[2]) if e else False,
                      'body':render_span(b,raw,p,q,cruns,link_start,targets_set),
                      'txt':raw[p:q].decode(b.enc,'replace'),
                      'marker':None})
        if q>=N: break
        p=q+1

    # --- fusionar los marcadores de lista numerada con su item ---
    NUM=re.compile(r'^\s*([0-9]+|[a-zA-Z]|[ivxlIVXL]+)[.)]\s*$')
    merged=[]; i=0
    while i<len(paras):
        cur=paras[i]
        if NUM.match(cur['txt']) and not cur['body'].count('<a href'):
            j=i+1
            while j<len(paras) and not paras[j]['txt'].strip(): j+=1
            if j<len(paras) and paras[j]['li']:
                paras[j]['marker']=cur['txt'].strip()
                if cur['a'] in targets_set: paras[j]['anchor_extra']=cur['a']
                i=j; merged.append(paras[j]); i+=1; continue
        merged.append(cur); i+=1
    paras=merged

    # --- render ---
    o=[]
    o.append('<h1 class="doctitle">%s</h1>'%html.escape(title or os.path.splitext(os.path.basename(path))[0]))
    if b.bookmarks:
        o.append('<nav><h2>Contenido</h2><ul>')
        for name,off in b.bookmarks:
            o.append('<li><a href="#o%d">%s</a></li>'%(off,html.escape(name)))
        o.append('</ul></nav>')
    for pa in paras:
        cls=[]; style=[]
        if pa['align']==1: style.append('text-align:center')
        elif pa['align']==2: style.append('text-align:right')
        elif pa['align']==3: style.append('text-align:justify')
        if pa['li']:
            cls.append('li')
            if pa['marker'] is None and not NUM.match(pa['txt'][:8]): cls.append('bullet')
        if pa['cell']: cls.append('cell')
        idattr=' id="o%d"'%pa['a'] if pa['a'] in targets_set else ''
        if 'anchor_extra' in pa and not idattr: idattr=' id="o%d"'%pa['anchor_extra']
        body=pa['body']
        if pa['marker']: body='<span class="mk">%s</span>%s'%(html.escape(pa['marker']),body)
        if not body.strip():
            if idattr: o.append('<p class="blank"%s></p>'%idattr)
            elif not (o and o[-1].startswith('<p class="blank"')):
                o.append('<p class="blank"></p>')
        else:
            o.append('<p%s%s%s>%s</p>'%(idattr,
                     ' class="%s"'%' '.join(cls) if cls else '',
                     ' style="%s"'%';'.join(style) if style else '', body))
    return write_html(o, out_path or os.path.splitext(path)[0]+'.html',
                      title or os.path.splitext(os.path.basename(path))[0])

def render_span(b, raw, p, q, cruns, link_start, targets_set):
    out=[]
    # puntos de corte
    cuts={p,q}
    for a,e,v in cruns:
        if p<a<q: cuts.add(a)
        if p<e<q: cuts.add(e)
    for a,(e,t) in link_start.items():
        if p<a<q: cuts.add(a)
        if p<e<q: cuts.add(e)
    for t in targets_set:
        if p<t<q: cuts.add(t)
    cuts=sorted(cuts)
    open_link=None
    for i in range(len(cuts)-1):
        a,e=cuts[i],cuts[i+1]
        if a in targets_set and a!=p: out.append('<span id="o%d"></span>'%a)
        if open_link and a>=open_link[0]:
            out.append('</a>'); open_link=None
        if a in link_start:
            end,tg=link_start[a]; kind,val=classify(tg)
            href='#o%d'%val if kind=='text' else None
            if href: out.append('<a href="%s">'%href); open_link=(end,)
            else: out.append('<a class="obj" title="%s %d">'%(kind,val)); open_link=(end,)
        idx=None
        for ra,re_,rv in cruns:
            if ra<=a<re_: idx=rv; break
        seg=raw[a:e].decode(b.enc,'replace')
        txt=html.escape(seg)
        c=css_char(b, idx or 0)
        if c:
            tags,st,islink=c
            pre=''.join('<%s>'%t for t in tags); post=''.join('</%s>'%t for t in reversed(tags))
            if st: txt='<span style="%s">%s</span>'%(st,txt)
            txt=pre+txt+post
        out.append(txt)
    if open_link: out.append('</a>')
    return ''.join(out)

CSS = """
:root{color-scheme:light dark}
body{max-width:44em;margin:2rem auto;padding:0 1.2rem;
     font:16px/1.65 Georgia,"Times New Roman",serif;background:#fdfdfb;color:#1b1b1b}
@media (prefers-color-scheme:dark){body{background:#16181c;color:#e6e4e0}}
h1.doctitle{font-size:1.7em;line-height:1.25;margin:0 0 1.5rem}
nav{border:1px solid #0002;border-radius:.5rem;padding:.6rem 1rem 1rem;margin-bottom:2.5rem;
    font-family:system-ui,sans-serif;font-size:.92em}
nav h2{font-size:1em;text-transform:uppercase;letter-spacing:.08em;opacity:.65;margin:.4rem 0 .6rem}
nav ul{margin:0;padding-left:1.1rem}
p{margin:0 0 .55rem}
p.blank{margin:0;height:.5rem}
p.li{margin-left:1.9rem;position:relative}
p.bullet::before{content:'\u2022';position:absolute;left:-1.15rem;opacity:.55;font-family:system-ui,sans-serif}
p .mk,p>span.mk{position:absolute;left:-1.6rem;opacity:.75;font-size:.9em}
a{color:#1a4fb4;text-decoration-thickness:1px;text-underline-offset:2px}
@media (prefers-color-scheme:dark){a{color:#7aa7ff}}
a.obj{color:inherit;text-decoration:none;border-bottom:1px dotted #0004}
sub,sup{line-height:0}
"""

def write_html(parts, out_path, title):
    doc=('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>%s</title><style>%s</style></head><body>\n%s\n</body></html>\n'
         % (html.escape(title), CSS, '\n'.join(parts)))
    open(out_path,'w',encoding='utf-8').write(doc)
    return out_path

if __name__=='__main__':
    if len(sys.argv)<2: raise SystemExit(__doc__)
    src=sys.argv[1]
    dst=sys.argv[2] if len(sys.argv)>2 else os.path.splitext(src)[0]+'.html'
    p=convert(src,dst)
    print("%s -> %s (%d KB)"%(os.path.basename(src),os.path.basename(p),os.path.getsize(p)//1024))
