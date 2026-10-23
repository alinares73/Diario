"""Resolucion de los enlaces entre libros iSilo (a partir de la tabla de enlaces externos).
La tabla solo guarda un desplazamiento de texto; aqui se deduce a que libro apunta cada grupo de enlaces."""
import re, os, unicodedata, datetime
from collections import Counter

def norm(s): return re.sub(r'\s+',' ',s.replace('\xa0',' ')).strip().lower()

def resolver(B, TAB, LINKS, log=print):
    """B: {nombre: Book}; TAB: {nombre: tabla de enlaces externos}; LINKS: {nombre: [(a,e,idx)]}.
    Devuelve RES: {(origen, idx): (libro_destino, desplazamiento, motivo)}"""
    from isilo2html_enlaces import BIBREF, BIBCAP, COMHEAD
    RAW={n:(B[n].enc,B[n].raw) for n in B}; LK=LINKS
    def segs_f(tab):
        out=[];s=0
        for i in range(1,len(tab)):
            if tab[i]>tab[i-1]: out.append((s,i)); s=i
        out.append((s,len(tab))); return out
    def anchors(src):
        enc,raw=RAW[src]; d={}
        for a,e,i in LK[src]:
            if i not in d:
                A=raw[a:e].decode(enc,'replace').strip()
                if A: d[i]=A
        return d
    names=list(B)
    TOP={n:norm(B[n].raw[:700].decode(B[n].enc,'replace')) for n in names}
    def anchor(S,a,e): return S.raw[a:e].decode(S.enc,'replace').strip()
    def txt(n,v,k=90): return norm(B[n].raw[v:v+k].decode(B[n].enc,'replace')).lstrip('* ')
    def evid(src,A,dn,v):
        """0 nada, 1 debil, 3 fuerte"""
        raw=B[dn].raw
        if v>=len(raw): return -99
        ls = v==0 or raw[v-1]==10
        T=txt(dn,v); a=norm(A)
        if dn=='Biblia':
            m=BIBREF.match(A)
            if m and ls and re.match(r'^%s\s'%m.group(1),T): return 3
            m=BIBCAP.match(A)
            if m and ls and re.match(r'^(capítulo|salmo) %s\b'%m.group(1),T): return 3
        if dn=='Comentarios' and src=='Biblia' and ls:
            mm=COMHEAD.match(txt(dn,v,30))
            if mm and mm.group(2) and re.fullmatch(r'\d+[a-z]*',a) and a==mm.group(2): return 3
            m=re.match(r'^(?:cap\w*|salmo)\s+(\d+)',a)
            if mm and m and not mm.group(2) and m.group(1)==mm.group(1): return 3
        if ls and len(a)>=4 and T.startswith(a): return 3
        nums=re.findall(r'\d+',a)
        if ls and nums and re.match(r'^%s(?!\d)'%nums[-1],T) and len(nums[-1])>=1: return 1
        if len(a)>=5 and a in T: return 1
        return 0
    def nameprior(A,dn):
        a=norm(A); d=dn.lower()
        w=re.split(r'[\s\d]',a)[0] if a else ''
        if len(w)>=3 and (d.startswith(w) or w.startswith(d)): return 1
        return 0
    ASSIGN={}
    for src in names:
        tab=TAB[src]; S=B[src]
        if not tab: ASSIGN[src]=[]; continue
        segs=[]; s0=0
        for i in range(1,len(tab)):
            if tab[i]>tab[i-1]: segs.append((s0,i)); s0=i
        segs.append((s0,len(tab)))
        byidx={}
        for a,e,i in LINKS[src]:
            A=anchor(S,a,e)
            if A and i<len(tab) and i not in byidx: byidx[i]=A
        out=[]
        for (s,e) in segs:
            idxs=[i for i in range(s,e) if i in byidx]
            mx=max(tab[s:e]); res=[]
            for dn in names:
                if mx>=len(B[dn].raw): continue
                sc=0; hits=0
                for i in idxs[:400]:
                    ev=evid(src,byidx[i],dn,tab[i])
                    if ev>0: sc+=ev; hits+=1
                    sc+=nameprior(byidx[i],dn)*0.5
                # etiqueta del enlace a la cabecera del documento (valor 0)
                if tab[e-1]==0 and (e-1) in byidx:
                    lab=norm(byidx[e-1])
                    if lab and lab in TOP[dn][:400]: sc+=6
                res.append((sc,hits,dn))
            res.sort(reverse=True)
            out.append((s,e,len(idxs),res[:3]))
        ASSIGN[src]=out
    def key(A):
        a=A.lower(); m=re.match(r'([^\W\d_]*)(\d*)(_?)',a)
        return (m.group(1)[:8],len(m.group(2)),m.group(3)) if m and (m.group(1) or m.group(2)) else None
    BYIDX={}; POS={}
    import unicodedata
    def strip(s): return ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn').lower()
    for src in names:
        d={};P={}
        for a,e,i in LINKS[src]:
            A=anchor(B[src],a,e)
            if A and i not in d: d[i]=A; P[i]=a
        BYIDX[src]=d; POS[src]=P
    # fase 1: segmentos con evidencia fuerte
    SEGDOC={}; KEYV={}; LAB={}
    for src in names:
        for (s,e,n,res) in ASSIGN[src]:
            if not res: continue
            sc1,h1,d1=res[0]; sc2=res[1][0] if len(res)>1 else 0
            if h1>=2 and h1>=0.3*min(n,400) and sc1>=2*sc2:
                SEGDOC[(src,s)]=d1
                for i in range(s,e):
                    A=BYIDX[src].get(i)
                    if A:
                        k=key(A)
                        if k: KEYV.setdefault(k,Counter())[d1]+=1
                if TAB[src][e-1]==0 and (e-1) in BYIDX[src]:
                    LAB.setdefault(norm(BYIDX[src][e-1]),Counter())[d1]+=1
    KEYMAP={k:c.most_common(1)[0][0] for k,c in KEYV.items() if sum(c.values())>=3 and c.most_common(1)[0][1]>=0.9*sum(c.values())}
    LABMAP={l:c.most_common(1)[0][0] for l,c in LAB.items() if c.most_common(1)[0][1]>=0.8*sum(c.values())}
    log('fase1: segmentos fuertes',len(SEGDOC),'claves',len(KEYMAP),'etiquetas',len(LABMAP))
    # fase 1b: evidencia por contexto (inicio de la linea origen == texto destino) y por nombre del documento
    def ctxev(src,i,dn):
        S=B[src]; a=POS[src][i]; v=TAB[src][i]; raw=B[dn].raw
        if v>=len(raw) or not (v==0 or raw[v-1]==10): return 0
        ls=S.raw.rfind(b'\n',0,a)+1
        head=norm(S.raw[ls:ls+40].decode(S.enc,'replace')); T=txt_(dn,v)
        cp=len(os.path.commonprefix([head,T]))
        return 1 if cp>=7 else 0
    def txt_(dn,v,k=60): return norm(B[dn].raw[v:v+k].decode(B[dn].enc,'replace')).lstrip('* ')
    DOCN={n:strip(n) for n in names}
    def nprior(A,dn):
        w=strip(re.split(r'[\s\d_·\-]',A.strip())[0]) if A.strip() else ''
        d=DOCN[dn]
        if len(w)>=3 and (w==d or (len(w)>=4 and (w in d or d in w)) ): return 1
        return 0
    EXTRA={}
    for src in names:
        tab=TAB[src]
        for (s,e,n,res) in ASSIGN[src]:
            if (src,s) in SEGDOC: continue
            idxs=[i for i in range(s,e) if i in BYIDX[src]]
            if len(idxs)<3: continue
            mx=max(tab[s:e]); samp=idxs[::max(1,len(idxs)//300)]
            best=None
            for dn in names:
                if mx>=len(B[dn].raw) or dn==src and False: continue
                c=sum(ctxev(src,i,dn) for i in samp)/len(samp)
                p=sum(nprior(BYIDX[src][i],dn) for i in samp)/len(samp)
                sc=max(c,p)
                if best is None or sc>best[0]: best=(sc,dn,c,p)
            if best and best[0]>=0.6: EXTRA[(src,s)]=best[1]
    for k,v in EXTRA.items(): SEGDOC[k]=v
    log('fase1b: segmentos por contexto/nombre',len(EXTRA))
    # fase 2: segmentos sin evidencia por abreviatura
    INF={}
    for src in names:
        tab=TAB[src]
        for (s,e,n,res) in ASSIGN[src]:
            if (src,s) in SEGDOC: continue
            idxs=[i for i in range(s,e) if i in BYIDX[src]]
            if not idxs: continue
            mx=max(tab[s:e]); votes=Counter(); keyed=0
            for i in idxs:
                k=key(BYIDX[src][i]); 
                if k in KEYMAP: votes[KEYMAP[k]]+=1; keyed+=1
            if keyed and keyed>=0.6*len(idxs):
                d,c=votes.most_common(1)[0]
                if c>=0.8*keyed and mx<len(B[d].raw): INF[(src,s)]=d
    log('fase2: inferidos por abreviatura',len(INF))
    NAV={('Comentarios','Libros'):'Biblia'}
    RES={}   # (src,idx)->(dest,v,why)
    for src in names:
        tab=TAB[src]
        for (s,e,n,res) in ASSIGN[src]:
            d=SEGDOC.get((src,s)); why='verificado' if (src,s) not in EXTRA else 'por contexto/nombre'
            if not d: d=INF.get((src,s)); why='inferido por abreviatura'
            for i in range(s,e):
                v=tab[i]; A=BYIDX[src].get(i)
                dd=d; w=why
                if v==0 and A:
                    L=norm(A); dd=LABMAP.get(L) or NAV.get((src,A)) or d
                    if dd and not LABMAP.get(L) and not NAV.get((src,A)): w=why
                    if LABMAP.get(L) or NAV.get((src,A)): w='cabecera'
                if dd and v<len(B[dd].raw): RES[(src,i)]=(dd,v,w)
    LS={}  # bitmaps de inicio de linea por documento
    def ls_ok(doc,v):
        raw=RAW[doc][1]; return v<len(raw) and (v==0 or raw[v-1]==10)
    def lsfrac(doc,vals):
        n=len(RAW[doc][1]); ok=0
        for v in vals:
            if v>=n: return -1
            if ls_ok(doc,v): ok+=1
        return ok/len(vals)
    def ddoc(prefix,s):
        # fecha del enlace -> libro (JP2 < 2005-04 <= B16 < 2013-03 <= Fco < 2025-05 <= Leon14)
        m=re.fullmatch(r'([a-zA-Z]{1,4})(\d{2})(\d{2})(\d{2})',s) 
        if m: yy,mm,dd=int(m.group(2)),int(m.group(3)),int(m.group(4)); pre=m.group(1)
        else:
            m=re.fullmatch(r'([a-zA-Z]{1,4})(\d{2})',s)
            if not m: return None
            yy,mm,dd=int(m.group(2)),6,15; pre=m.group(1)
        y=1900+yy if yy>=50 else 2000+yy
        d=datetime.date(y,max(1,min(mm,12)),max(1,min(dd,28)))
        if d<datetime.date(2005,4,1): return 'JP2'
        if d<datetime.date(2013,3,1): return 'B16'
        if d<datetime.date(2025,5,1): return 'Fco'
        return 'Leon14'
    HINTS=[(r'^ant\d*[a-z]*$','Antologia'),(r'^Series?\b','DEspiritual'),(r'^Denz','DS'),(r'^Fillion|^VXto','VidaXto'),(r'^Nazaret','B16Libros'),(r'^JP\d+\w+','JP2Libros'),(r'^CQP|^Cqp','SanJosemaria'),(r'^SSede','StaSede')]
    def hint(A):
        for pat,d in HINTS:
            if re.match(pat,A): return d
        m=re.match(r'^([a-zA-Z]{1,4})(\d{2,6})',A)
        if m and m.group(1).lower() in ('ang','a','h','c','ex','m','mens','s','e','ct','cd','hom','cat','ad','dm'):
            return ddoc(m.group(1),m.group(0))
        return None
    NEW={}; why={}
    for src in names:
        tab=TAB[src]; by=anchors(src)
        for s,e in segs_f(tab):
            if (src,s) in SEGDOC or (src,s) in INF: continue
            idxs=[i for i in range(s,e) if i in by]
            if not idxs: continue
            vals=[tab[i] for i in idxs]; mx=max(vals)
            # 1) criterio de inicio de linea
            if len(idxs)>=4:
                cand=sorted(((lsfrac(d,vals),d) for d in names if d!=src or True),reverse=True)
                b,second=cand[0],cand[1]
                if b[0]>=0.6 and second[0]<=0.5*b[0]:
                    NEW[(src,s)]=b[1]; why[(src,s)]='inicio de linea'; continue
            # 2) pistas por el texto del enlace
            hv=Counter(hint(by[i]) for i in idxs); hv.pop(None,None)
            if hv:
                d,c=hv.most_common(1)[0]
                if sum(v<len(RAW[d][1]) for v in vals)>=0.7*len(vals) and ((c>=0.7*len(idxs) and lsfrac(d,vals)>=0.3) or (c>=0.9*len(idxs) and d in ('Antologia','DS','DEspiritual','VidaXto','SanJosemaria','B16Libros','JP2Libros','StaSede'))):
                    NEW[(src,s)]=d; why[(src,s)]='pista'; continue
            # 3) los tres mas frecuentes (JP2, B16, Fco) para el resto
            if len(idxs)>=3:
                best=max(((lsfrac(d,vals),d) for d in ('JP2','B16','Fco')),default=None)
                if best and best[0]>=0.8: NEW[(src,s)]=best[1]; why[(src,s)]='JP2/B16/Fco'
    for k,d in NEW.items():
        src,s=k; tab=TAB[src]
        e=[b for a,b in segs_f(tab) if a==s][0]
        for i in range(s,e):
            v=tab[i]
            if v<len(RAW[d][1]) and (src,i) not in RES: RES[(src,i)]=(d,v,'inferido: '+why[k])
    log('enlaces resueltos:',len(RES))
    return RES
