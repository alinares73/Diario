#!/usr/bin/env python3
"""
Actualizacion mensual de la app de la Biblia a partir de los .pdb de Almudi.

Uso:   python actualizar.py                 (usa config.json)
       python actualizar.py --destino ../Almud   (escribe la app directamente en tu carpeta de GitHub)
       python actualizar.py --forzar        (rehace todo aunque no haya cambios)

1. Detecta que .pdb han cambiado (por huella SHA-1) y solo vuelve a leer esos; el resto sale de la cache.
2. Resuelve los enlaces entre libros.
3. Reconvierte los libros de la app (Biblia + libros enlazados).
4. Construye la app, COMPRUEBA todos los enlaces y, solo si no hay ninguno roto, copia a la carpeta
   de destino unicamente los archivos que han cambiado.
"""
import sys, os, re, json, time, hashlib, pickle, shutil, argparse, datetime
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'src'))
sys.setrecursionlimit(20000)
from isilo2html_biblioteca import *            # Book, classify, ext_table, Doc, quote ...
import enlaces, appbuild

APP_DOCS=['Comentarios','Fco','JP2','NotasSE','B16','STh','Padres','NotasSEbac','Catecismo','VidaXto','HCD','SanJosemaria','Antologia','StaSede','DicTeo','CatenaAurea','VyS','POrigenes','PCirilo','DS','B16Libros','Obra','DEspiritual','Cartas','StaMarta','PCrisostomo','Leon14','Resumenes','Marianos','Romana','DA','CEE','CV2','CDSocial','PCreta','JP2Libros','PAgustin','FOD']
T0=time.time()
def log(*a): print('[%3ds]'%(time.time()-T0),*a,flush=True)
def nm(p): return re.sub(r'#U([0-9a-fA-F]{4})',lambda m:chr(int(m.group(1),16)),os.path.basename(p)[:-4])
def sha1(p):
    h=hashlib.sha1()
    with open(p,'rb') as f:
        for ch in iter(lambda:f.read(1<<20),b''): h.update(ch)
    return h.hexdigest()
def sha_text(*parts):
    h=hashlib.sha1()
    for p in parts: h.update(str(p).encode('utf-8','replace'))
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pdb'); ap.add_argument('--destino'); ap.add_argument('--trabajo'); ap.add_argument('--forzar',action='store_true')
    a=ap.parse_args()
    cfgp=os.path.join(HERE,'config.json'); cfg=json.load(open(cfgp,encoding='utf-8')) if os.path.exists(cfgp) else {}
    rel=lambda p:p if os.path.isabs(p) else os.path.normpath(os.path.join(HERE,p))
    PDB=rel(a.pdb or cfg.get('pdb','pdb')); DEST=rel(a.destino or cfg.get('destino','salida/app')); WORK=rel(a.trabajo or cfg.get('trabajo','trabajo'))
    for d in (WORK+'/cache',WORK+'/html',WORK+'/app',DEST): os.makedirs(d,exist_ok=True)
    pdbs=sorted(f for f in os.listdir(PDB) if f.lower().endswith('.pdb'))
    if not pdbs: sys.exit('No hay .pdb en '+PDB)
    names={nm(f):os.path.join(PDB,f) for f in pdbs}
    falta=[n for n in ['Biblia','Comentarios']+APP_DOCS if n not in names]
    if falta: sys.exit('Faltan estos .pdb en %s: %s'%(PDB,', '.join(falta)))
    # ---------------------------------------------------------------- 1. cambios
    est_p=WORK+'/estado.json'; prev=json.load(open(est_p,encoding='utf-8')) if os.path.exists(est_p) else {}
    code_sig=sha_text(*[open(os.path.join(HERE,'src',f),'rb').read() for f in sorted(os.listdir(os.path.join(HERE,'src'))) if f.endswith('.py')],
                      *[open(os.path.join(HERE,'plantillas',f),'rb').read() for f in sorted(os.listdir(os.path.join(HERE,'plantillas')))])
    hashes={n:sha1(p) for n,p in names.items()}
    ph=prev.get('pdb',{}); changed=[n for n in names if ph.get(n)!=hashes[n]]; removed=[n for n in ph if n not in names]
    log('%d archivos .pdb; cambiados desde la ultima vez: %s'%(len(names),', '.join(changed) if changed else 'ninguno'))
    if not changed and not removed and prev.get('code')==code_sig and not a.forzar and os.path.exists(DEST+'/index.html'):
        log('Nada que actualizar (use --forzar para rehacer).'); return
    # ---------------------------------------------------------------- 2. lectura con cache
    B={};TAB={};LINKS={}
    for n,p in names.items():
        cp=os.path.join(WORK,'cache','%s.%s.pkl'%(re.sub(r'[^\w.-]','_',n),hashes[n][:12]))
        if os.path.exists(cp):
            try:
                with open(cp,'rb') as f: B[n],TAB[n],LINKS[n]=pickle.load(f); continue
            except Exception: pass
        t=time.time(); b=Book(p); tab=ext_table(b)
        lk=[(a_,e,classify(t_)[1]) for a_,e,t_ in b.linklist() if classify(t_)[0]=='document']
        B[n],TAB[n],LINKS[n]=b,tab,lk
        for old in os.listdir(WORK+'/cache'):
            if old.startswith(re.sub(r'[^\w.-]','_',n)+'.') and old!=os.path.basename(cp): os.remove(os.path.join(WORK,'cache',old))
        with open(cp,'wb') as f: pickle.dump((b,tab,lk),f,protocol=4)
        log('  leido %s (%.0f s)'%(n,time.time()-t))
    log('libros cargados')
    # ---------------------------------------------------------------- 3. enlaces entre libros
    RES=enlaces.resolver(B,TAB,LINKS,log)
    # ---------------------------------------------------------------- 4. HTML de los libros de la app
    class Lib2:
        def __init__(s): s.names=list(B); s.book=B; s.tab=TAB; s.raw={n:B[n].raw for n in B}; s.enc={n:B[n].enc for n in B}
        def href(s,n): return quote(n)+'.html'
        def resolve(s,src,a_,e,idx):
            r=RES.get((src,idx))
            if r: return r[0],r[1],r[2]
            return None,TAB[src][idx] if idx<len(TAB[src]) else 0,'externo'
    lib=Lib2(); docnames=['Biblia']+APP_DOCS
    docs={n:Doc(lib,n) for n in docnames}; incoming={}
    for n in docnames: docs[n].classify_links(incoming)
    nuevos=0; stats_doc={}
    for n in docnames:
        key=sha_text(hashes[n],sorted((i,r) for (s,i),r in RES.items() if s==n),sorted(incoming.get(n,())))
        kp=os.path.join(WORK,'html',n+'.key'); hp=os.path.join(WORK,'html',n+'.html')
        if os.path.exists(kp) and os.path.exists(hp) and open(kp).read()==key: pass
        else:
            docs[n].convert(incoming.get(n,set()),os.path.join(WORK,'html')); open(kp,'w').write(key); nuevos+=1
        stats_doc[n]=dict(docs[n].stats)
    log('HTML: %d reconvertidos, %d sin cambios'%(nuevos,len(docnames)-nuevos))
    # ---------------------------------------------------------------- 5. construir la app
    res=appbuild.build(WORK+'/html',WORK+'/app',APP_DOCS,os.path.join(HERE,'plantillas'),log)
    log('app construida: %s'%res['files'])
    # ---------------------------------------------------------------- 6. comprobar todos los enlaces
    import verificar
    v=verificar.verificar(WORK+'/app',log)
    if v['rotos']:
        sys.exit('ERROR: hay %d enlaces rotos; NO se ha tocado la carpeta de destino. Ejemplos: %s'%(v['rotos'],v['ejemplos']))
    # ---------------------------------------------------------------- 7. sincronizar con el destino
    cop=igu=bor=0
    ap_root=WORK+'/app'
    for root,_,files in os.walk(ap_root):
        for fn in files:
            s=os.path.join(root,fn); r=os.path.relpath(s,ap_root); d=os.path.join(DEST,r)
            if os.path.exists(d) and os.path.getsize(d)==os.path.getsize(s) and open(d,'rb').read()==open(s,'rb').read(): igu+=1; continue
            os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copyfile(s,d); cop+=1
    for base in ('data','docs'):
        for root,_,files in os.walk(os.path.join(DEST,base)):
            for fn in files:
                r=os.path.relpath(os.path.join(root,fn),DEST)
                if not os.path.exists(os.path.join(ap_root,r)): os.remove(os.path.join(root,fn)); bor+=1
    log('destino %s: %d archivos copiados/actualizados, %d sin cambios, %d borrados'%(DEST,cop,igu,bor))
    # ---------------------------------------------------------------- 8. informe y estado
    tot=sum(len(t) for t in TAB.values())
    inf=['Actualizacion %s'%datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),'.pdb cambiados: %s'%(', '.join(changed) or 'ninguno'),
         'Enlaces entre libros resueltos (todos los libros): %d'%len(RES),'Enlaces comprobados en la app: %d (rotos: %d)'%(v['total'],v['rotos']),
         'Archivos de la app: %d copiados, %d sin cambios, %d borrados'%(cop,igu,bor),'','Enlaces de la Biblia y Comentarios por destino:']
    for n in ('Biblia','Comentarios'):
        inf.append('  %s: %s'%(n,stats_doc.get(n)))
    open(os.path.join(HERE,'informe.txt'),'w',encoding='utf-8').write('\n'.join(inf)+'\n')
    sin=stats_doc.get('Comentarios',{}).get('a documentos no incluidos',0)
    if prev.get('sin_destino_comentarios') is not None and sin>prev['sin_destino_comentarios']*1.1+50:
        log('AVISO: los enlaces sin destino de Comentarios han subido de %d a %d; revise informe.txt'%(prev['sin_destino_comentarios'],sin))
    json.dump(dict(pdb=hashes,code=code_sig,sin_destino_comentarios=sin,fecha=time.time()),open(est_p,'w',encoding='utf-8'))
    log('LISTO. Revisa informe.txt y sube los cambios con Git.')
if __name__=='__main__': main()
