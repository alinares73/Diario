#!/usr/bin/env python3
"""
isilo2html_enlaces.py - Convierte VARIOS ebooks iSilo (.pdb) a HTML conservando
tambien los enlaces ENTRE libros (p. ej. "Mt 16, 16" en Leon14 -> Biblia.html).

Se apoya en isilo2html.py / isilo2txt.py (sin modificarlos) y anade:
  1. Decodificacion de la tabla de enlaces externos (registros tipo 16): cada
     enlace "document" guarda un indice; la tabla da el desplazamiento de texto
     de destino. La tabla NO dice a que libro pertenece ese desplazamiento.
  2. Resolucion del libro destino por verificacion del texto: solo se crea un
     enlace cuando en el desplazamiento hay justo lo que el enlace anuncia
     (versiculo, capitulo, cabecera de comentario, paginas de navegacion).
  3. Indice rapido de tramos (el script original era cuadratico y no termina
     en libros grandes).
Uso:  python isilo2html_enlaces.py Leon14.pdb Comentarios.pdb Cartas.pdb Biblia.pdb
Los HTML se escriben junto a los .pdb y se enlazan por nombre de archivo.
"""
import sys, os, re, html
from urllib.parse import quote, unquote
from bisect import bisect_left, bisect_right
from collections import Counter
import isilo2html as I
from isilo2html import Book, classify, css_char, be16, be32, CSS
from isilo2txt import build_trees, Bits, LEN_BASE, DIST_BASE

# ----------------------------------------------------- tabla de enlaces externos
def _inflate_blocks(rec, off, ln, lt, dt):
    br=Bits(rec,off*4,ln); blocks=[]; out=bytearray()
    while br.err==0:
        sym=lt.decode(br)
        if sym is None: break
        if sym<0x100: out.append(sym); continue
        if sym==0x100: blocks.append(bytes(out)); out=bytearray(); continue
        if sym<0x109: l=sym-0xfe
        elif sym<0x11d: l=br.bits((sym-0x105)>>2)+LEN_BASE[sym]
        elif sym==0x11d: l=0x102
        else: break
        dc=dt.decode(br)
        if dc is None or dc>0x1c: break
        dist=dc+1 if dc<4 else br.bits((dc-2)>>1)+DIST_BASE[dc]
        if dist>len(out) or dist==0: break
        s=len(out)-dist
        for i in range(l): out.append(out[s+i])
    if out: blocks.append(bytes(out))
    return blocks

def ext_table(book):
    """Lista idx -> desplazamiento (32 bits) del documento destino.
    Registro tipo 16: [4 cab][16 subcab: byte18 = n.o de flujos][5 tamanos de
    arbol][n tamanos de flujo][relleno a 4]; cada flujo = 'registro' 04 02 <n>
    seguido de n valores de 32 bits, codificado con los mismos arboles que el texto."""
    vals=[]
    for ri,x in enumerate(book.recs):
        if len(x)<30 or x[1]!=16: continue
        nf=x[18]; words=[be16(x,20+2*k) for k in range(5+nf)]
        tsz,dsz=words[:5],words[5:]
        p=(20+2*(5+nf)+3)&~3; trees=[]
        for t in tsz:
            try: trees.append(build_trees(x,p//4,t//4))
            except Exception: trees.append(None)
            p+=t
        for d in dsz:
            got=None
            for tr in trees:
                if tr is None: continue
                bl=_inflate_blocks(x,p//4,d//4,*tr)
                if bl and len(bl[0])>=4 and bl[0][:2]==b'\x04\x02' and len(bl[0])==4+4*be16(bl[0],2):
                    got=bl[0]; break
            if got is None: raise ValueError('flujo de la tabla externa no decodificado (reg %d)'%ri)
            vals+=[be32(got,4+4*k) for k in range((len(got)-4)//4)]
            p+=d
    return vals

# --------------------------------------------------- resolucion del libro destino
BIBREF = re.compile(r'^\s*(?:[1-3]\s?)?[A-Za-zÁÉÍÓÚáéíóúñ]{1,6}\.?\s*\d+\s*,\s*(\d+)')
BIBCAP = re.compile(r'^\s*(?:[1-3]\s?)?[A-Za-zÁÉÍÓÚáéíóúñ]{1,6}\.?\s+(\d+)\s*$')
COMHEAD = re.compile(r'^(?:[1-3]\s?)?[A-Za-zÁÉÍÓÚáéíóúñ]{1,6}\s+(\d+)(?:,\s*(\d+[a-z]*))?(?:\s|$)')

class Lib:
    def __init__(s, paths):
        s.names=[os.path.splitext(os.path.basename(p))[0] for p in paths]
        s.book={n:Book(p) for n,p in zip(s.names,paths)}
        s.tab={n:ext_table(s.book[n]) for n in s.names}
        s.raw={n:s.book[n].raw for n in s.names}
        s.enc={n:s.book[n].enc for n in s.names}
    def text(s,n,v,k=40): return s.raw[n][v:v+k].decode(s.enc[n],'replace')
    def line_start(s,n,v): return v==0 or s.raw[n][v-1:v]==b'\n'

    def resolve(s, src, a, e, idx):
        """-> (libro_destino|None, offset, motivo)"""
        v=s.tab[src][idx]; S=s.book[src]
        anc=S.raw[a:e].decode(S.enc,'replace').strip(); N=s.names
        if 'Biblia' in N and src!='Biblia' and v<len(s.raw['Biblia']) and s.line_start('Biblia',v):
            m=BIBREF.match(anc)
            if m and re.match(r'^%s[ \xa0]'%m.group(1), s.text('Biblia',v,12)):
                return 'Biblia',v,'versiculo'
            if m and re.match(r'^\d+[ \xa0]', s.text('Biblia',v,12)):
                return 'Biblia',v,'versiculo (destino original en otro versiculo del pasaje)'
            m=BIBCAP.match(anc)
            if m and re.match(r'^\*? ?(?:Cap\xedtulo|Capítulo|Salmo) %s\b'%m.group(1), s.text('Biblia',v,30)):
                return 'Biblia',v,'capitulo'
        if 'Comentarios' in N and src=='Biblia' and v<len(s.raw['Comentarios']) and s.line_start('Comentarios',v):
            mm=COMHEAD.match(s.text('Comentarios',v,30))
            if mm:
                if mm.group(2) and re.fullmatch(r'\d+[a-z]*',anc) and anc==mm.group(2):
                    return 'Comentarios',v,'comentario-versiculo'
                m=re.match(r'^(?:Cap\w*|Salmo)\s+(\d+)',anc)
                if m and not mm.group(2) and m.group(1)==mm.group(1):
                    return 'Comentarios',v,'comentario-capitulo'
        # paginas de navegacion (verificadas con un enlace interno equivalente o por cabecera)
        NAV={('Cartas','Sagrada Escritura'):'Biblia',('Cartas','León XIV'):'Leon14',
             ('Comentarios','Libros'):'Biblia',('Biblia','Comentarios'):'Comentarios'}
        t=NAV.get((src,anc))
        if t in N and v==0: return t,0,'navegacion'
        if src=='Biblia' and anc=='Siglas' and 'Comentarios' in N:
            # Comentarios tiene un enlace INTERNO 'Siglas' al mismo desplazamiento
            C=s.book['Comentarios']
            for a2,e2,t2 in C.linklist():
                if classify(t2)[0]=='text' and C.raw[a2:e2]==b'Siglas' and classify(t2)[1]==v:
                    return 'Comentarios',v,'navegacion'
        return None,v,'externo'

# --------------------------------------------------------------------- render
class Doc:
    def __init__(s, lib, name):
        s.lib=lib; s.name=name; s.b=lib.book[name]
        s.info={}     # a -> (end, href|None, clase, titulo)
        s.fallback={} # posicion de salto de linea -> (href, titulo)
        s.stats=Counter(); s.unres=Counter(); s.ext_targets=set()

    def classify_links(s, incoming):
        b=s.b; raw=b.raw
        for a,e,tg in b.linklist():
            kind,val=classify(tg); anc=raw[a:e].strip()
            href=None; cls=None; title=None
            if kind=='text':
                href='#o%d'%val; s.stats['internos']+=1
            elif kind=='document':
                idx=val
                if not anc: s.stats['iconos de barra (sin texto)']+=1; continue
                dest,v,why=s.lib.resolve(s.name,a,e,idx)
                if dest:
                    href='%s#o%d'%(s.lib.href(dest),v); cls='xdoc'
                    incoming.setdefault(dest,set()).add(v)
                    s.stats['entre libros -> '+dest]+=1
                else:
                    cls='obj ext'; title='Enlace a otro documento cuyo destino no se ha podido identificar (desplazamiento %d)'%v
                    s.stats['a documentos no incluidos']+=1
                    s.unres[anc.decode(b.enc,'replace')[:24]]+=1
            elif kind=='menu':
                cls='obj'; title='Menu de iSilo %d (selector de capitulo; no convertible)'%val
                s.stats['menus de iSilo (no convertibles)']+=1
            else:
                cls='obj'; title='%s %d'%(kind,val); s.stats['otros (%s)'%kind]+=1
            if not anc:
                # enlace sobre un salto de linea (en iSilo era una imagen): se anade etiqueta visible
                if href: s.fallback[a]=(href,cls)
                continue
            s.info[a]=(e,href,cls,title)

    def label_for(s, href):
        if href.startswith('#o'): n=s.name; v=int(href[2:])
        else:
            n,v=href.rsplit('.html#o',1); n=unquote(n); v=int(v)
        r=s.lib.raw[n]; enc=s.lib.enc[n]
        seg=r[v:v+120].decode(enc,'replace')
        seg=re.sub(r'[\s\xa0*]+',' ',seg).strip()
        return (seg[:16] or '→')

    def render_span(s, p, q, X):
        b=s.b; raw=b.raw; out=[]
        cuts={p,q}
        for lst in (X['cstarts'],X['cends'],X['lstarts'],X['lends'],X['targets']):
            cuts.update(lst[bisect_right(lst,p):bisect_left(lst,q)])
        cuts=sorted(cuts); open_end=None
        cr=X['cr']
        for i in range(len(cuts)-1):
            a,e=cuts[i],cuts[i+1]
            if a in X['tset'] and a!=p: out.append('<span id="o%d"></span>'%a)
            if open_end is not None and a>=open_end: out.append('</a>'); open_end=None
            if a in s.info:
                end,href,cls,title=s.info[a]
                if href: out.append('<a href="%s"%s%s>'%(href,' class="%s"'%cls if cls else '',' title="%s"'%html.escape(title) if title else ''))
                else: out.append('<a class="%s" title="%s">'%(cls,html.escape(title or '')))
                open_end=end
            k=bisect_right(X['cstarts'],a)-1; idx=0
            if k>=0 and cr[k][0]<=a<cr[k][1]: idx=cr[k][2]
            txt=html.escape(raw[a:e].decode(b.enc,'replace'))
            c=css_char(b,idx or 0)
            if c:
                tags,st,_=c
                if st: txt='<span style="%s">%s</span>'%(st,txt)
                txt=''.join('<%s>'%t for t in tags)+txt+''.join('</%s>'%t for t in reversed(tags))
            out.append(txt)
        if open_end is not None: out.append('</a>')
        return ''.join(out)

    def convert(s, incoming_targets, outdir):
        b=s.b; raw=b.raw; N=len(raw)
        links=b.linklist()
        tset={v for a,e,t in links for k,v in [classify(t)] if k=='text'} | set(incoming_targets)
        pruns=sorted(b.runs(b.para)); cruns=sorted(b.runs(b.char))
        X=dict(cr=cruns,cstarts=[r[0] for r in cruns],cends=sorted(r[1] for r in cruns),
               lstarts=sorted(s.info),lends=sorted(v[0] for v in s.info.values()),
               targets=sorted(tset),tset=tset)
        def find(runs,pos):
            lo,hi=0,len(runs)-1
            while lo<=hi:
                m=(lo+hi)//2
                if runs[m][0]<=pos<runs[m][1]: return runs[m][2]
                if pos<runs[m][0]: hi=m-1
                else: lo=m+1
            return 0
        paras=[]; p=0
        while p<=N:
            q=raw.find(b'\n',p)
            if q<0: q=N
            st=find(pruns,p) if p<N else 0
            e=b.para_tab[st-1] if st and st-1<len(b.para_tab) else None
            body=s.render_span(p,q,X)
            if q in s.fallback:
                href,cls=s.fallback[q]
                body+='<a class="img %s" href="%s" title="Enlace que en el original era una imagen">%s</a>'%(cls or '',href,html.escape(s.label_for(href)))
                s.stats['enlaces de imagen (con etiqueta anadida)']+=1
            paras.append({'a':p,'b':q,'align':((e[0]&3) if e else 0),'li':bool(e[1]) if e else False,
                          'cell':bool(e[2]) if e else False,'body':body,
                          'txt':raw[p:q].decode(b.enc,'replace'),'marker':None,'extra':[],
                          'endid':[q] if (q in tset and q!=p) else []})
            if q>=N: break
            p=q+1
        NUM=re.compile(r'^\s*([0-9]+|[a-zA-Z]|[ivxlIVXL]+)[.)]\s*$')
        merged=[]; i=0
        while i<len(paras):
            cur=paras[i]
            if NUM.match(cur['txt']) and '<a ' not in cur['body']:
                j=i+1
                while j<len(paras) and not paras[j]['txt'].strip(): j+=1
                if j<len(paras) and paras[j]['li']:
                    paras[j]['marker']=cur['txt'].strip()
                    if cur['a'] in tset: paras[j]['extra'].append(cur['a'])
                    paras[j]['extra']+=cur['endid']
                    i=j; merged.append(paras[j]); i+=1; continue
            merged.append(cur); i+=1
        paras=merged
        title=s.name; o=['<h1 class="doctitle">%s</h1>'%html.escape(title)]
        for pa in paras:
            cls=[]; style=[]
            if pa['align']==1: style.append('text-align:center')
            elif pa['align']==2: style.append('text-align:right')
            elif pa['align']==3: style.append('text-align:justify')
            if pa['li']:
                cls.append('li')
                if pa['marker'] is None and not NUM.match(pa['txt'][:8]): cls.append('bullet')
            if pa['cell']: cls.append('cell')
            ids=([pa['a']] if pa['a'] in tset else [])+pa['extra']
            idattr=' id="o%d"'%ids[0] if ids else ''
            spans=''.join('<span id="o%d"></span>'%x for x in ids[1:])
            endspans=''.join('<span id="o%d"></span>'%x for x in pa['endid'])
            body=spans+pa['body']
            if pa['marker']: body='<span class="mk">%s</span>%s'%(html.escape(pa['marker']),body)
            body+=endspans
            if not pa['body'].strip():
                if idattr or spans or endspans: o.append('<p class="blank"%s>%s%s</p>'%(idattr,spans,endspans))
                elif not (o and o[-1].startswith('<p class="blank"')): o.append('<p class="blank"></p>')
            else:
                o.append('<p%s data-o="%d"%s%s>%s</p>'%(idattr,pa['a'],' class="%s"'%' '.join(cls) if cls else '',
                         ' style="%s"'%';'.join(style) if style else '',body))
        css=CSS+"""
a.xdoc{text-decoration-style:solid}
a.obj.ext{color:inherit;border-bottom:1px dotted #c60;text-decoration:none;cursor:help}
a.img{font:.72em system-ui,sans-serif;opacity:.8;margin-left:.4em;border:1px solid #0003;border-radius:.3em;padding:0 .3em;text-decoration:none}
"""
        doc=('<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>%s</title><style>%s</style></head><body>\n%s\n</body></html>\n'
             %(html.escape(title),css,'\n'.join(o)))
        path=os.path.join(outdir,s.name+'.html'); open(path,'w',encoding='utf-8').write(doc)
        return path

def main(paths, outdir=None):
    outdir=outdir or os.path.dirname(os.path.abspath(paths[0]))
    lib=Lib(paths); docs={n:Doc(lib,n) for n in lib.names}; incoming={}
    for n in lib.names: docs[n].classify_links(incoming)
    for n in lib.names:
        p=docs[n].convert(incoming.get(n,set()),outdir)
        print('%s -> %s (%d KB)'%(n,os.path.basename(p),os.path.getsize(p)//1024))
        for k,v in sorted(docs[n].stats.items()): print('    %-45s %d'%(k,v))
    return lib,docs

if __name__=='__main__':
    if len(sys.argv)<2: raise SystemExit(__doc__)
    main(sys.argv[1:])
