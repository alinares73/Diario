"""Comprueba que todos los enlaces internos de la app (#/d/..., #/r/...) llevan a un destino existente."""
import re,json,os,bisect
def verificar(A,log=print):
    cat=json.load(open(A+'/catalog.json',encoding='utf-8')); D=cat['docs']; BKS=cat['books']
    chunks={}; bdata={}
    def chunk(doc,k):
        if (doc,k) not in chunks:
            chunks[(doc,k)]=open(A+'/docs/%s/%d.html'%(doc,k),encoding='utf-8').read()
            if len(chunks)>40: chunks.pop(next(iter(chunks)))
        return chunks[(doc,k)]
    def book(b):
        if b not in bdata: bdata[b]=json.load(open(A+'/data/b%02d.json'%b,encoding='utf-8'))
        return bdata[b]
    st={'total':0,'rotos':0,'sin_id':0,'ejemplos':[]}
    def bad(src,h,why):
        st['rotos']+=1
        if len(st['ejemplos'])<8: st['ejemplos'].append((src,h,why))
    def chk(h,src):
        st['total']+=1
        m=re.match(r'#/d/([^/]+)/(\d+)$',h)
        if m:
            doc,N=m.group(1),int(m.group(2))
            if doc not in D: return bad(src,h,'libro')
            x=D[doc]['x'].get(str(N)); k=x if x is not None else max(0,bisect.bisect_right(D[doc]['starts'],N)-1)
            if not os.path.exists(A+'/docs/%s/%d.html'%(doc,k)): return bad(src,h,'trozo')
            if ('id="o%d"'%N) not in chunk(doc,k): st['sin_id']+=1
            return
        m=re.match(r'#/r/(\d+)/(\d+)(?:/(\w+))?$',h)
        if m:
            b,c,v=int(m.group(1)),int(m.group(2)),m.group(3)
            if b>=len(BKS) or c>=len(BKS[b]['ch']): return bad(src,h,'capitulo')
            if v and ('data-v="%s"'%v) not in book(b)['ch'][c]['h']: return bad(src,h,'versiculo')
    for b in range(len(BKS)):
        for ci,c in enumerate(book(b)['ch']):
            for h in re.findall(r'href="(#/[^"]+)"',c['h']): chk(h,'Biblia %d:%d'%(b,ci))
            if c.get('k'): chk('#/d/Comentarios/%d'%c['k'],'Biblia cap %d:%d'%(b,ci))
    for doc in D:
        for k in range(len(D[doc]['starts'])):
            for h in re.findall(r'href="(#/[^"]+)"',chunk(doc,k)): chk(h,doc)
    log('enlaces comprobados: %d, rotos: %d (destinos sin marca exacta: %d)'%(st['total'],st['rotos'],st['sin_id']))
    return st
