#!/usr/bin/env python3
"""
Actualizacion de la app DIARIO (portada del dia + Biblia + libros + Misal).

Uso:   python actualizar_diario.py                  (todo: primero actualizar.py y despues el Diario)
       python actualizar_diario.py --sin-biblia     (no ejecuta actualizar.py; usa lo ya construido en trabajo/app)
       python actualizar_diario.py --destino ../Diario   (escribe la app en tu carpeta de GitHub)
       python actualizar_diario.py --forzar         (rehace todo aunque no haya cambios)

Que necesita (rutas por defecto, se pueden cambiar en config.json):
  pdb/              los .pdb de siempre (actualizar.py)
  pdb_diario/       Misal.pdb y el .epub de "El sentir del corazon de Jesus" (aqui, para no mezclarlos con los libros de la app Biblia)
  epactas/          los .docx de la epacta (todos; si una fecha esta en varios, gana el ultimo por orden alfabetico)
  config.json       claves opcionales: "destino_diario" (def. salida/diario), "epactas" (def. epactas),
                    "pdb_misal" (def. pdb_diario)

Que hace:
  1. (salvo --sin-biblia) ejecuta actualizar.py, que reconstruye trabajo/app con tus .pdb.
  2. Lee los .docx de epactas y extrae solo: fecha, Cat (tipo de fiesta A/B/C/D y categoria), Celebracion,
     Misa, Col, Gl Cr, Prefacio y Notas.
  3. Convierte Misal.pdb (solo si ha cambiado) y saca de cada dia: lecturas con resumen, boton
     "Lecturas"/"Lectura continuada", notas; el Misal queda como libro enlazado de la app.
  4. Parte del index.html recien construido, le anade la portada y los datos, COMPRUEBA los enlaces
     y, solo si no hay ninguno roto, copia al destino unicamente los archivos que han cambiado.
Requiere:  pip install python-docx
"""
import sys, os, re, json, time, html, hashlib, shutil, argparse, subprocess, datetime, calendar, glob, filecmp
HERE=os.path.dirname(os.path.abspath(__file__))
for _p in (HERE,os.path.join(HERE,'src')): sys.path.insert(0,_p)
CODE_VERSION='4'
T0=time.time()
def log(*a): print('[%3ds]'%(time.time()-T0),*a,flush=True)
def sha_text(*parts):
    h=hashlib.sha1()
    for p in parts: h.update(p if isinstance(p,bytes) else str(p).encode('utf-8','replace'))
    return h.hexdigest()
def sha_file(p):
    h=hashlib.sha1()
    with open(p,'rb') as f:
        for ch in iter(lambda:f.read(1<<20),b''): h.update(ch)
    return h.hexdigest()
def norm(x):
    x=x.lower()
    for a,b in zip('áàäâéèëêíìïîóòöôúùüû','aaaaeeeeiiiioooouuuu'): x=x.replace(a,b)
    return x
def txt(h): return html.unescape(re.sub(r'<[^>]+>','',h)).replace('\xa0',' ').strip()

# ============================================================== Biblia de la app
class Biblia:
    ALIAS={'1sm':'1S','2sm':'2S','1re':'1R','2re':'2R','1mac':'1M','2mac':'2M','neh':'Ne','prov':'Pr','ecl':'Qo',
           'cant':'Ct','sab':'Sb','eclo':'Si','sir':'Si','abd':'Ab','miq':'Mi','nah':'Na','sof':'So','zac':'Za',
           'mal':'Ml','rom':'Rm','1cor':'1Co','2cor':'2Co','gal':'Ga','1tim':'1Tm','2tim':'2Tm','tit':'Tt',
           'heb':'Hb','1pe':'1P','2pe':'2P','lam':'Lm','bar':'Ba','judas':'Jds','ha':'Hab','jc':'Jue'}
    def __init__(s,cat):
        s.BK=cat['books']; s.AB={norm(b['ab']):i for i,b in enumerate(s.BK)}
        for k,v in s.ALIAS.items():
            if norm(v) in s.AB: s.AB.setdefault(k,s.AB[norm(v)])
        s.sig=json.dumps([(b['ab'],len(b['ch'])) for b in s.BK])
    def chidx(s,b,n):
        ch=s.BK[b]['ch']
        for i,c in enumerate(ch):
            if re.match(r'^(Capítulo|Salmo) %d(\D|$)'%n,c['t']): return i
        if len(ch)>=n and s.BK[b]['ab']!='Sal': return n-1+(1 if ch[0]['t']=='Introducción' else 0)
        return None
    def href(s,t):
        t=html.unescape(t).strip()
        m=re.match(r'^(\d?\s?[A-Za-zñÑ]+)\.?\s*(\d+)(?:\s*,\s*(\d+))?',t)
        if not m: return None
        b=s.AB.get(norm(m.group(1)).replace(' ',''))
        if b is None: return None
        c=s.chidx(b,int(m.group(2)))
        if c is None: return None
        return '#/r/%d/%d%s'%(b,c,('/'+m.group(3)) if m.group(3) else '')

# ============================================================== epacta (.docx)
COLS_DEF={'fecha':0,'cat':1,'celebración':2,'misa':3,'col':4,'gl cr':5,'notas':9}
def leer_epacta(path):
    try: import docx
    except ImportError: sys.exit('Falta python-docx:  pip install python-docx')
    D=docx.Document(path); out={}; avisos=[]
    for t in D.tables:
        idx=dict(COLS_DEF)
        for r in t.rows:
            c=[x.text.replace('\n',' ').strip() for x in r.cells]
            if c and c[0].lower().startswith('fecha'):
                hd=[re.sub(r'\s+',' ',x).lower() for x in c]
                try: idx={k:hd.index(k) for k in COLS_DEF}
                except ValueError: idx=dict(COLS_DEF)
                continue
            m=re.match(r'(\d\d)/(\d\d)/(\d\d)\b',c[0] if c else '')
            if not m or len(c)<=max(idx.values()): continue
            dd,mm,yy=m.groups(); iso='20%s-%s-%s'%(yy,mm,dd)
            try: wd=datetime.date.fromisoformat(iso).weekday()
            except ValueError: avisos.append('fecha imposible '+c[0]); continue
            w=re.match(r'\d\d/\d\d/\d\d\s+([LMXJVSD])\b',c[0])
            if w and 'LMXJVSD'.index(w.group(1))!=wd: avisos.append('dia de la semana no coincide: '+c[0])
            if iso in out: continue
            cat=c[idx['cat']]; let=re.search(r'\b([ABCD])\b',cat)
            cols=re.findall(r'\b(bl|ve|ro|mo|rs)\b',c[idx['col']].lower())
            if not cols: avisos.append('sin color litúrgico: '+iso)
            out[iso]={'cel':c[idx['celebración']],'cat':re.sub(r'\b[ABCD]\b','',cat).strip(),'tp':let.group(1) if let else '',
                      'c':cols,'misa':c[idx['misa']],'gl':c[idx['gl cr']],'n':c[idx['notas']]}
    return out,avisos


# ============================================================== ePub "El sentir del corazon de Jesus" (Él y yo)
_MIN={'a','de','del','la','las','el','los','en','y','que','te','me','por','con','al','o','u','un','una','lo','se','su','sus','mi','tu','nuestro','nuestra'}
def bonito(t):
    m=re.match(r'^(\d+\.\s*)(.*)$',t); pre,t=(m.group(1),m.group(2)) if m else ('',t)
    out=[]
    for i,w in enumerate(t.split(' ')):
        core=w.lstrip('¿¡')
        if i>0 and core.lower() in _MIN: w=w[:len(w)-len(core)]+core.lower()
        out.append(w)
    return pre+' '.join(out)
def _limpia(h,allow=('i',)):
    out=[]
    for tok in re.split(r'(<[^>]+>)',h):
        if tok.startswith('<'):
            m=re.match(r'<(/?)([a-z]+)\b',tok,re.I)
            if m:
                tag={'em':'i'}.get(m.group(2).lower(),m.group(2).lower())
                if tag in allow: out.append('<%s%s>'%(m.group(1),tag))
        else: out.append(html.unescape(tok).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
    return re.sub(r'\s+',' ',''.join(out)).strip()

def leer_epub(path):
    import zipfile, posixpath
    z=zipfile.ZipFile(path)
    opf=re.search(r'full-path="([^"]+)"',z.read('META-INF/container.xml').decode('utf-8')).group(1)
    o=z.read(opf).decode('utf-8'); base=posixpath.dirname(opf); man={}
    for it in re.findall(r'<item\b[^>]*>',o):
        i=re.search(r'\bid="([^"]+)"',it); h=re.search(r'\bhref="([^"]+)"',it)
        if i and h: man[i.group(1)]=h.group(1)
    files=[man[i] for i in re.findall(r'<itemref idref="([^"]+)"',o) if i in man]
    pts={}; order=[]; themes=[]; huerfanos=0
    for f in files:
        if not re.match(r'(capitulo|sin-titulo)',posixpath.basename(f)): continue
        s=z.read(posixpath.join(base,f).lstrip('./')).decode('utf-8'); body=s[s.find('<body'):]
        h1=re.search(r'<h1[^>]*>(.*?)</h1>',body,re.S)
        th=bonito(re.sub(r'^\d+\.\s*','',txt(h1.group(1)))) if h1 else f
        if th not in themes: themes.append(th)
        ti=themes.index(th); cur=None
        for m in re.finditer(r'<p\b([^>]*)>(.*?)</p>',body,re.S):
            c=re.search(r'class="([^"]*)"',m.group(1)); c=c.group(1).split()[0] if c else ''
            inner=m.group(2).strip(); plain=txt(inner)
            mm=re.match(r'^(\d{1,4})\.\s+',plain) or (re.match(r'^(\d{1,4})\s+',plain) if c=='first' else None)
            if mm:
                n=int(mm.group(1)); inner=re.sub(r'^\s*\d{1,4}\.?\s+','',inner,count=1)
                cur=[_limpia(inner)]; 
                if n not in pts: pts[n]={'frag':[],'th':[]}; order.append(n)
                pts[n]['frag'].append(cur)
                if ti not in pts[n]['th']: pts[n]['th'].append(ti)
            elif cur is not None and c=='subsq': cur.append(_limpia(inner))
            else: huerfanos+=1
    P=[]; rep_=0
    for n in sorted(order):
        fr=[]; plains=[]
        for f_ in pts[n]['frag']:
            pl=re.sub(r'<[^>]+>','',' '.join(f_)); pl=re.sub(r'^\d{1,2} de [a-záéíóú]+\.\s*','',pl).strip()
            if any(pl and pl in q for q in plains): rep_+=1; continue
            fr_old=[k for k,q in enumerate(plains) if q and q in pl]
            for k in reversed(fr_old): del fr[k]; del plains[k]; rep_+=1
            fr.append('\n'.join(f_)); plains.append(pl)
        P.append([n,fr,pts[n]['th']])
    return {'th':themes,'p':P},{'ocurrencias':sum(len(v['frag']) for v in pts.values()),'huerfanos':huerfanos,'fragmentos_repetidos':rep_}


def epub_a_libro(path):
    """Todo el ePub como libro enlazado de la app: trozos docs/ElYo/k.html (con indice y una estrella en cada punto)."""
    import zipfile, posixpath
    z=zipfile.ZipFile(path)
    opf=re.search(r'full-path="([^"]+)"',z.read('META-INF/container.xml').decode('utf-8')).group(1)
    o=z.read(opf).decode('utf-8'); base=posixpath.dirname(opf); man={}
    for it in re.findall(r'<item\b[^>]*>',o):
        i=re.search(r'\bid="([^"]+)"',it); h=re.search(r'\bhref="([^"]+)"',it)
        if i and h: man[i.group(1)]=h.group(1)
    files=[man[i] for i in re.findall(r'<itemref idref="([^"]+)"',o) if i in man]
    secs=[]; toc=[]; idx=0; npts=0
    for f in files:
        b=posixpath.basename(f)
        if re.match(r'(cover|portadilla|indice)',b): continue
        s=z.read(posixpath.join(base,f).lstrip('./')).decode('utf-8'); body=s[s.find('<body'):]
        h1=re.search(r'<h1[^>]*>(.*?)</h1>',body,re.S); title=bonito(txt(h1.group(1))) if h1 else ''
        cap=bool(re.match(r'(capitulo|sin-titulo)',b)); out=[]; start=idx
        if title: out.append('<h2 id="o%d" data-o="%d">%s</h2>'%(idx,idx,html.escape(title))); toc.append((title,idx)); idx+=1
        for m in re.finditer(r'<p\b([^>]*)>(.*?)</p>',body,re.S):
            c=re.search(r'class="([^"]*)"',m.group(1)); c=c.group(1).split()[0] if c else ''
            inner=m.group(2).strip(); plain=txt(inner)
            mm=(re.match(r'^(\d{1,4})\.\s+',plain) or (re.match(r'^(\d{1,4})\s+',plain) if c=='first' else None)) if cap else None
            if mm:
                n=int(mm.group(1)); npts+=1
                inner=re.sub(r'^\s*\d{1,4}\.?\s+','',inner,count=1)
                out.append('<p class="pn" data-o="%d"><b class="nm">%d.</b><span class="st" data-n="%d" role="button" aria-label="Marcar este punto"></span> %s</p>'%(idx,n,n,_limpia(inner,('i','sup'))))
            else: out.append('<p data-o="%d">%s</p>'%(idx,_limpia(inner,('i','sup'))))
            idx+=1
        secs.append((start,'\n'.join(out)))
    tocH='<h2>Índice</h2>\n'+'\n'.join('<p class="toc"><a href="#/d/ElYo/%d">%s</a></p>'%(i,html.escape(t_)) for t_,i in toc)
    chunks=[];starts=[0];cur=''
    for k,(st,h_) in enumerate(secs):
        if k==1: cur+=tocH+'\n'
        if len(cur)>300000: chunks.append(cur); cur=''; starts.append(st)
        cur+=h_+'\n'
    chunks.append(cur)
    meta={'title':'Él y yo','starts':starts,'x':{},'v':hashlib.md5(''.join(chunks).encode()).hexdigest()[:8],'kb':sum(len(c.encode()) for c in chunks)//1024}
    return chunks,meta,npts

# ============================================================== Misal (.pdb -> datos + libro enlazado)
MES_N=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
SEM=['LUNES','MARTES','MIÉRCOLES','JUEVES','VIERNES','SÁBADO','DOMINGO']
ANC=re.compile(r'<a class="obj ext"[^>]*>(<i><span[^>]*>(.*?)</span></i>)</a>')

def conv_links(h,bib):
    def ext(m):
        hr=bib.href(m.group(2))
        return '<a href="%s">%s</a>'%(hr,m.group(1)) if hr else m.group(1)
    h=ANC.sub(ext,h)
    h=re.sub(r'<a class="obj ext"[^>]*>(.*?)</a>',r'\1',h)
    h=re.sub(r'href="#o(\d+)"',r'href="#/d/Misal/\1"',h)
    h=h.replace(' title="Enlace que en el original era una imagen"','')
    h=re.sub(r'color:#[0-9a-fA-F]{6};?','',h)
    return re.sub(r' style="\s*"','',h)

def procesar_misal(s,bib):
    body=s[s.find('<body>')+6:s.rfind('</body>')]
    ym=re.search(r'>\s*(20\d\d)\s*<',body[:8000])
    if not ym: sys.exit('No encuentro el año en la portada del Misal.')
    year=int(ym.group(1))
    marks=[]
    for mm in re.finditer(r'<p id="o(\d+)" class="cell" style="text-align:center"><b>(%s)</b></p>'%'|'.join(MES_N),s): marks.append(mm)
    if [x.group(2) for x in marks]!=MES_N: sys.exit('No encuentro los 12 meses del Misal (¿ha cambiado su estructura?).')
    days={}
    for i,mk in enumerate(marks):
        end=marks[i+1].start() if i<11 else mk.start()+9000
        links=re.findall(r'href="#o(\d+)"',s[mk.start():end]); nd=calendar.monthrange(year,i+1)[1]
        if len(links)<nd: sys.exit('El mes de %s del Misal tiene %d enlaces de día y deberían ser %d.'%(MES_N[i],len(links),nd))
        for d in range(1,nd+1): days['%d-%02d-%02d'%(year,i+1,d)]=int(links[d-1])
    idpos={int(m.group(1)):m.start() for m in re.finditer(r'<p id="o(\d+)"',s)}
    order=sorted(days.items(),key=lambda kv:kv[1]); bad=[]; DAY={}
    for i,(d,o) in enumerate(order):
        a=idpos[o]; b=idpos[order[i+1][1]] if i+1<len(order) else a+9000
        e=s[a:b]
        t=re.search(r'font-size:1\.17em[^>]*>(.*?)</span>',e); title=txt(t.group(1)) if t else ''
        if SEM[datetime.date.fromisoformat(d).weekday()] not in title.upper(): bad.append(d)
        btn=[]
        for m in re.finditer(r'<p class="cell">Misa: (.*?)</p>',e):
            for x in re.finditer(r'<a [^>]*href="#o(\d+)"[^>]*>(.*?)</a>',m.group(1)):
                lab=txt(x.group(2))
                if lab in('Lecturas','Lectura continuada') and [lab,int(x.group(1))] not in btn: btn.append([lab,int(x.group(1))])
        if not btn:
            mm=re.search(r'<p class="cell">Misa: (.*?)</p>',e,re.S)
            for x in re.finditer(r'<a [^>]*href="#o(\d+)"[^>]*>(.*?)</a>',mm.group(1) if mm else ''):
                lab=txt(x.group(2))
                if lab and 'enlace' not in lab: btn.append([lab[0].upper()+lab[1:],int(x.group(1))])
        nm=re.search(r'<p class="cell">Notas: (.*?)</p>',e)
        vm=re.search(r'<p class="cell">Lecturas: ((?:vol\.|Lecturas)[^<]*)</p>',e)
        reads=[];ob=[]
        for m in re.finditer(r'<p class="cell">(• .*?|o bien.*?)</p>',e):
            p=m.group(1)
            if p.startswith('o bien'): ob.append(txt(p)); continue
            p=p[2:]; am=ANC.search(p)
            if am and len(txt(p[:am.start()]))<=12:
                pre=txt(p[:am.start()]); ref=(pre+' ' if pre else '')+txt(am.group(2)); toks=txt(p[am.end():]).split(' '); rng=[]
                while toks and re.fullmatch(r'[-–\d.,a-d]+',toks[0]): rng.append(toks.pop(0))
                rng=' '.join(rng); summ=' '.join(toks)
                if not rng and summ.startswith('.'): rng='.'; summ=summ[1:].strip()
                if rng.endswith('.'): rng=rng[:-1]
                reads.append([bib.href(txt(am.group(2))) or '',ref,rng,summ])
            else: reads.append(['',txt(p),'',''])
        DAY[d]={'o':o,'t':title,'b':btn,'n':conv_links(nm.group(1),bib).strip() if nm else '','v':txt(vm.group(1)) if vm else '','r':reads,'ob':ob}
    if len(bad)>8: sys.exit('Los días del Misal no cuadran con el calendario de %d (%d desajustes, p. ej. %s).'%(year,len(bad),bad[:3]))
    body=conv_links(re.sub(r'<h1 class="doctitle">.*?</h1>\s*','',body),bib)
    chunks=[];cur='';starts=[0]
    for p in re.split(r'(?=<p id="o\d+")',body):
        if len(cur)>380000 and p.startswith('<p id="o'):
            chunks.append(cur);cur='';starts.append(int(re.match(r'<p id="o(\d+)"',p).group(1)))
        cur+=p
    chunks.append(cur)
    return year,DAY,chunks,starts,bad

def preparar_misal(pdb,bib,WORK,forzar):
    cdir=os.path.join(WORK,'diario','misal'); jp=os.path.join(cdir,'misal.json'); os.makedirs(cdir,exist_ok=True)
    key=sha_text(sha_file(pdb),bib.sig,CODE_VERSION)
    if os.path.exists(jp) and not forzar:
        try:
            M=json.load(open(jp,encoding='utf-8'))
            if M.get('key')==key and all(os.path.exists(os.path.join(cdir,'%d.html'%k)) for k in range(len(M['starts']))):
                log('Misal sin cambios (año %s): se usa la copia guardada'%M['year']); return M,cdir
        except Exception: pass
    import isilo2html_enlaces as IE
    t=time.time(); log('convirtiendo Misal.pdb (unos 40 s)...')
    lib=IE.Lib([pdb]); n=lib.names[0]; doc=IE.Doc(lib,n); inc={}
    doc.classify_links(inc)
    tmp=os.path.join(WORK,'diario','tmp'); os.makedirs(tmp,exist_ok=True)
    s=open(doc.convert(inc.get(n,set()),tmp),encoding='utf-8').read()
    year,DAY,chunks,starts,bad=procesar_misal(s,bib)
    for f in os.listdir(cdir):
        if f.endswith('.html'): os.remove(os.path.join(cdir,f))
    for i,c in enumerate(chunks): open(os.path.join(cdir,'%d.html'%i),'w',encoding='utf-8').write(c)
    M={'key':key,'year':year,'day':DAY,'starts':starts,'kb':sum(len(c.encode()) for c in chunks)//1024,
       'v':hashlib.md5(''.join(chunks).encode()).hexdigest()[:8],'aviso_dias':bad}
    json.dump(M,open(jp,'w',encoding='utf-8'),ensure_ascii=False,separators=(',',':'))
    log('Misal %d convertido: %d días, %d trozos, %d KB (%.0f s)'%(year,len(DAY),len(chunks),M['kb'],time.time()-t))
    return M,cdir

# ============================================================== portada en el index.html
CSS=r'''
.dhero{text-align:center;margin:6px 0 4px}.dnum{font:700 112px/1 var(--ff);letter-spacing:-.02em}.dmon{font:400 34px/1.1 var(--ff);text-transform:lowercase;margin-top:2px}.dwk{color:var(--mut);font-size:17px;margin-top:6px}
.dnav{display:flex;gap:10px;margin:16px 0 18px}.dnav .btn{min-height:46px;font-size:20px}.dnav .btn:nth-child(2){flex:2;font-size:17px}.dnav .btn{flex:1}
.card{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:16px;margin:0 0 14px}
.lh{display:flex;gap:12px;align-items:flex-start}.lh h2{font:600 21px/1.3 var(--ff);margin:0}.dots{display:flex;align-items:center;gap:4px;padding-top:2px;flex:none}.or{color:var(--mut);font-size:14px}
.dot{display:inline-block;width:30px;height:30px;border-radius:50%;border:2px solid #0004;box-shadow:0 0 0 1px var(--bd)}.c-bl{background:#fbfaf3}.c-ve{background:#2f9e5e}.c-ro{background:#c6282b}.c-mo{background:#6b3fa3}.c-rs{background:#e88cb2}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px}.tag{font:600 14px var(--ui);padding:5px 12px;border-radius:14px;border:1px solid var(--bd);background:var(--bg);color:var(--fg)}.tag.f{background:var(--link);color:var(--bg);border-color:var(--link)}.tag.g{border-color:var(--link);color:var(--link)}
.kv{margin:12px 0 0;font:17px/1.45 var(--ff)}.kv small{display:block;font:600 12px var(--ui);letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin-bottom:2px}.kv a{color:var(--link)}
.sh{font:700 13px var(--ui);letter-spacing:.06em;text-transform:uppercase;color:var(--link);margin:0 0 8px}
.rd{display:block;padding:10px 0;border-bottom:1px solid var(--bd);color:var(--fg);text-decoration:none;font:17px/1.45 var(--ff)}.rd:last-of-type{border-bottom:0}.rd b{font:700 16px var(--ui);color:var(--link);display:block;margin-bottom:2px}.rd span{display:block}
.cap{color:var(--mut);font-size:14px;margin:0 0 6px}.card .btn{margin-top:12px;min-height:52px;font-size:18px}.card a.cm{margin-top:12px}
.row.one{margin-top:22px}.row.one .btn{min-height:78px;font-size:23px}.row.two .btn{min-height:64px;font-size:20px}
#sfab{position:fixed;right:16px;bottom:152px;z-index:24;width:56px;height:56px;border-radius:50%;border:1px solid var(--bd);background:#3a4d75;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 4px 14px #0006}
.pt{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:14px 16px;margin:0 0 14px}
.ph{display:flex;gap:10px;align-items:baseline;margin-bottom:6px}.ph b{font:700 18px var(--ui);color:var(--link)}.ph span{font:13px var(--ui);color:var(--mut)}
.pf{font:var(--fs)/var(--lh) var(--ff)}.pf+.pf{border-top:1px dashed var(--bd);margin-top:10px;padding-top:6px}.pf p{margin:.4em 0}
.doc mark{background:var(--hl);color:inherit;border-radius:3px}
.dtop{display:flex;gap:14px;align-items:flex-start;margin:4px 0 4px}.dtop .dhero{text-align:left;flex:0 0 38%;margin:0}.dtop .dnum{font-size:84px}.dtop .dmon{font-size:25px}.dtop .dwk{font-size:15px}
.cal{flex:1;min-width:0}.calh{display:flex;align-items:center;justify-content:space-between;margin-bottom:2px}.calh b{font:600 14px var(--ui);text-transform:capitalize;cursor:pointer}.calh button{background:none;border:0;color:var(--fg);font-size:24px;width:34px;height:34px;border-radius:8px;cursor:pointer}
.calg{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center}.calg span{font:600 11px var(--ui);color:var(--mut);padding:2px 0}.cd{display:flex;align-items:center;justify-content:center;aspect-ratio:1;font:13px var(--ui);color:var(--fg);text-decoration:none;border-radius:50%}.cd.no{color:var(--mut);opacity:.45}.cd.td{outline:1px solid var(--link)}.cd.sel{background:var(--link);color:var(--bg);font-weight:700;opacity:1}
.doc.just p{text-align:justify;-webkit-hyphens:auto;hyphens:auto}
.star{margin-left:auto;background:none;border:0;font-size:30px;line-height:1;color:var(--mut);padding:0 4px;cursor:pointer;align-self:center}.star::before{content:'☆'}.star.on{color:#f5b301}.star.on::before{content:'★'}
.st{display:inline-block;margin:0 .3em 0 .1em;font-size:1.3em;line-height:1;color:var(--mut);cursor:pointer;vertical-align:-2px;-webkit-user-select:none;user-select:none}.st::before{content:'☆'}.st.on{color:#f5b301}.st.on::before{content:'★'}
.doc p.pn{margin-top:1.1em}.doc .nm{color:var(--link)}.doc h2{margin:1.4em 0 .5em}
.thm{font:700 14px var(--ui);letter-spacing:.06em;text-transform:uppercase;color:var(--link);margin:24px 0 8px}
/* portada: fila fecha + calendario (sin aspect-ratio, que en Safari/iPad desbordaba) */
.dtop{display:flex;align-items:stretch;gap:12px;margin:4px 0 6px;max-width:100%}
.dtop .dhero{flex:0 0 40%;min-width:0;margin:0;text-align:left;display:flex;flex-direction:column;justify-content:center}
.dtop .dnum{font-size:clamp(88px,25vw,160px);line-height:.95}
.dtop .dmon{font-size:clamp(22px,5.8vw,36px);margin-top:4px}
.dtop .dwk{font-size:clamp(14px,3.6vw,20px);margin-top:6px}
.cal{flex:1 1 0;min-width:0;max-width:100%}
.calg{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px}
.cd{aspect-ratio:auto;display:block;position:relative;min-width:0;font-size:clamp(12px,3.2vw,17px)}
.cd::before{content:"";display:block;padding-top:100%}
.cd span{position:absolute;top:0;right:0;bottom:0;left:0;display:flex;align-items:center;justify-content:center}
.calg span.wd{display:block}
.calg .cd span{font:inherit;padding:0;color:inherit}
'''
JS=r'''
const MESES=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'],DIAS=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'],COLN={bl:'Blanco',ve:'Verde',ro:'Rojo',mo:'Morado',rs:'Rosa'};
const pad2=n=>String(n).padStart(2,'0'),isoOf=d=>d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate());
const addDays=(iso,n)=>{const [y,m,d]=iso.split('-').map(Number);return isoOf(new Date(y,m-1,d+n))};
function renderHome(arg){
  const today=isoOf(new Date()),iso=/^\d{4}-\d\d-\d\d$/.test(arg||'')?arg:today;
  const [y,m,d]=iso.split('-').map(Number),dt=new Date(y,m-1,d),E=EPA[iso],D=DAY[iso];
  setHead('Diario',iso===today?'':'#/');
  if(!calV||calV.sel!==iso)calV={y,m,sel:iso};
  let h=`<div class="dtop"><div class="dhero"><div class="dnum">${d}</div><div class="dmon">${MESES[m-1]}</div><div class="dwk">${DIAS[dt.getDay()]} · ${y}</div></div><div class="cal" id="cal"></div></div>`;
  h+=`<div class="dnav"><a class="btn" href="#/dia/${addDays(iso,-1)}" aria-label="Día anterior">‹</a><a class="btn" href="#/">Hoy</a><a class="btn" href="#/dia/${addDays(iso,1)}" aria-label="Día siguiente">›</a></div>`;
  const kv=(l,t)=>t?`<div class="kv"><small>${l}</small>${esc(t)}</div>`:'';
  const alm=D&&D.n?`<div class="kv"><small>Notas de Almudi</small>${D.n}</div>`:'';
  if(E){
    const dots=E.c.map(c=>`<span class="dot c-${c}" title="${esc(COLN[c]||c)}" role="img" aria-label="${esc(COLN[c]||c)}"></span>`).join('<span class="or">/</span>');
    let tg='';if(E.tp)tg+=`<span class="tag f">Fiesta ${esc(E.tp)}</span>`;if(E.cat)tg+=`<span class="tag">${esc(E.cat)}</span>`;
    if(/gloria/i.test(E.gl))tg+=`<span class="tag g">${/\(\s*gloria/i.test(E.gl)?'(Gloria)':'Gloria'}</span>`;if(/credo/i.test(E.gl))tg+=`<span class="tag g">Credo</span>`;
    h+=`<section class="card"><div class="lh">${E.c.length?`<span class="dots">${dots}</span>`:''}<h2>${esc(E.cel)}</h2></div>${tg?`<div class="tags">${tg}</div>`:''}${kv('Misa',E.misa)}${kv('Notas',E.n)}${alm}</section>`;
  }else if(D){h+=`<section class="card"><div class="lh"><h2>${esc(D.t)}</h2></div>${alm}<p class="mut" style="margin:10px 0 0">Sin datos de epacta para esta fecha.</p></section>`}
  if(D){
    h+=`<section class="card"><h3 class="sh">Lecturas</h3>${D.v?`<p class="cap">${esc(D.v)}</p>`:''}`;
    h+=D.r.map(r=>r[0]?`<a class="rd" href="${r[0]}"><b>${esc(r[1])}${esc(r[2])}</b><span>${esc(r[3])}</span></a>`:`<div class="rd"><span>${esc(r[1])}</span></div>`).join('');
    h+=D.ob.map(t=>`<p class="cap">${esc(t)}</p>`).join('');
    h+=D.b.map(b=>`<a class="btn" href="#/d/Misal/${b[1]}">${esc(b[0])}</a>`).join('');
    h+=`</section><a class="cm" href="#/d/Misal/${D.o}" style="margin-bottom:14px">Ver el día completo en el Misal →</a>`;
  }
  if(!E&&!D)h+='<p class="mut" style="text-align:center">No hay datos litúrgicos para esta fecha.</p>';
  h+='<div class="row one"><a class="btn" href="#/biblia">📖 Sagrada Escritura</a></div><div class="row two"><a class="btn" href="#/docs">📚 Libros</a><a class="btn" href="#/elyyo">🕊️ Él y yo</a></div>';
  $('#main').innerHTML=h;drawCal(iso,today);
}
let calV=null;
function drawCal(sel,today){
  const {y,m}=calV,off=(new Date(y,m-1,1).getDay()+6)%7,nd=new Date(y,m,0).getDate();
  let g='LMXJVSD'.split('').map(x=>`<span class="wd">${x}</span>`).join('')+'<i></i>'.repeat(off);
  for(let d=1;d<=nd;d++){const iso=y+'-'+pad2(m)+'-'+pad2(d);g+=`<a class="cd${iso===sel?' sel':''}${iso===today?' td':''}${EPA[iso]||DAY[iso]?'':' no'}" href="#/dia/${iso}"><span>${d}</span></a>`}
  $('#cal').innerHTML=`<div class="calh"><button type="button" id="cp" aria-label="Mes anterior">‹</button><b id="cm">${MESES[m-1]} ${y}</b><button type="button" id="cn" aria-label="Mes siguiente">›</button></div><div class="calg">${g}</div>`;
  const go=n=>{const t=new Date(y,m-1+n,1);calV={y:t.getFullYear(),m:t.getMonth()+1,sel:calV.sel};drawCal(sel,today)};
  $('#cp').onclick=()=>go(-1);$('#cn').onclick=()=>go(1);$('#cm').onclick=()=>{const t=new Date(sel.slice(0,4),+sel.slice(5,7)-1,1);calV={y:t.getFullYear(),m:t.getMonth()+1,sel:calV.sel};drawCal(sel,today)}
}
/* Él y yo: 6 puntos al azar, sin repetir hasta agotar todos */
const EYN=EY.p.length,eyPerms=new Map();
function eyRand(seed){let s=seed>>>0;return()=>{s=(s+0x6D2B79F5)>>>0;let t=s;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296}}
function eyAt(st,p){const c=Math.floor(p/EYN),j=p%EYN,key=st.seed+':'+c;let a=eyPerms.get(key);if(!a){a=Array.from({length:EYN},(_,i)=>i);const r=eyRand((st.seed+Math.imul(c+1,0x9E3779B1))>>>0);for(let i=EYN-1;i>0;i--){const k=Math.floor(r()*(i+1));[a[i],a[k]]=[a[k],a[i]]}eyPerms.set(key,a);if(eyPerms.size>4)eyPerms.delete(eyPerms.keys().next().value)}return a[j]}
function eyState(){let st=LS.get('ey',null);const today=isoOf(new Date());if(!st||st.n!==EYN)st={seed:(Math.random()*4294967296)>>>0,n:EYN,pos:0,day:'',start:0,shown:0};if(st.day!==today){st.day=today;st.start=st.pos;st.shown=6;st.pos+=6}LS.set('ey',st);return st}
function eyCard(i,fav){const p=EY.p[i];return `<article class="pt"><div class="ph"><b>${p[0]}</b><span>${p[2].map(t=>esc(EY.th[t])).join(' · ')}</span><button type="button" class="star${fav&&fav.has(p[0])?' on':''}" data-n="${p[0]}" aria-label="Marcar este punto"></button></div>${p[1].map(f=>`<div class="pf">${f.split('\n').map(x=>`<p>${x}</p>`).join('')}</div>`).join('')}</article>`}
const eyFav=()=>new Set(LS.get('eyfav',[]));
function eyCards(st,from,n){const fav=eyFav();let o='';for(let p=from;p<from+n;p++)o+=eyCard(eyAt(st,p),fav);return o}
function eySub(st){const c=Math.floor((st.pos-1)/EYN),x=((st.pos-1)%EYN)+1;return `Hoy ${st.shown} puntos · vuelta ${c+1}: ${x} de ${EYN} puntos vistos`}
function renderEY(){
  setHead('Él y yo','#/');const M=$('#main');$('#hstar').style.display='';
  if(!EYN){M.innerHTML='<p class="mut" style="text-align:center">No hay puntos cargados. Falta el ePub «El sentir del corazón de Jesús».</p>';return}
  const st=eyState();
  M.innerHTML=`<h2 class="t" style="margin-bottom:4px">Él y yo</h2><p class="mut" id="eysub" style="margin:0 0 16px">${eySub(st)}</p><div id="eyl">${eyCards(st,st.start,st.shown)}</div><button class="btn" id="eymore" style="width:100%;margin-top:6px">Cargar más puntos…</button>`;
  $('#eymore').onclick=()=>{const from=st.start+st.shown;st.shown+=6;st.pos=st.start+st.shown;LS.set('ey',st);const box=document.createElement('div');box.innerHTML=eyCards(st,from,6);const first=box.firstElementChild;$('#eyl').append(...box.children);$('#eysub').textContent=eySub(st);if(first){first.scrollIntoView({block:'start',behavior:'smooth'});window.scrollBy&&setTimeout(()=>window.scrollBy(0,-70),350)}}
}
/* buscador dentro de un libro (todos menos Comentarios) */
const DIDX=new Map(),BLK='p,h1,h2,h3,h4,h5,h6';let sfDoc='';
const qTerms=v=>{const t=[],re=/"([^"]+)"|(\S+)/g;let m;const nq=norm(v.replace(/[“”«»]/g,'"'));while((m=re.exec(nq)))t.push((m[1]||m[2]).trim());return t.filter(Boolean)};
function buildDocIdx(doc,prog){if(DIDX.has(doc))return DIDX.get(doc);const p=(async()=>{const n=DOCS[doc].starts.length,out=[];let head='';for(let k=0;k<n;k++){const r=await fetch('docs/'+doc+'/'+k+'.html?v='+DOCS[doc].v);if(!r.ok)throw new Error('HTTP '+r.status);const d=new DOMParser().parseFromString(await r.text(),'text/html');d.body.querySelectorAll(BLK).forEach((e,i)=>{const t=e.textContent.replace(/\s+/g,' ').trim();if(t.length>1&&!e.classList.contains('toc')){const c=e.children[0];if(t.length<=90&&(/^H[1-6]$/.test(e.tagName)||(e.children.length===1&&c&&/^(B|STRONG|SPAN)$/.test(c.tagName)&&c.textContent.replace(/\s+/g,' ').trim()===t&&(c.tagName!=='SPAN'||/font-size/.test(c.getAttribute('style')||'')))))head=t;out.push({k,i,t,n:norm(t),h:head})}});if(prog)prog(k+1,n)}return out})();DIDX.set(doc,p);p.catch(()=>DIDX.delete(doc));return p}
function hiText(text,terms){let s=esc(text),ns=norm(s);const sp=[];terms.forEach(x=>{const ex=norm(esc(x));if(!ex)return;let i=0;while((i=ns.indexOf(ex,i))>=0){sp.push([i,i+ex.length]);i+=ex.length}});sp.sort((a,b)=>a[0]-b[0]);let o='',p=0;for(const [a,b] of sp){if(a<p)continue;o+=s.slice(p,a)+'<mark>'+s.slice(a,b)+'</mark>';p=b}return o+s.slice(p)}
function snipOf(r,terms){let pos=-1;terms.forEach(x=>{const i=r.n.indexOf(x);if(i>=0&&(pos<0||i<pos))pos=i});let a=Math.max(0,pos-90);if(a>0){const sp=r.t.indexOf(' ',a);if(sp>=0&&sp<pos)a=sp+1}const e=a+300;return(a>0?'… ':'')+r.t.slice(a,e)+(e<r.t.length?' …':'')}
async function renderDocSearch(doc,q0){
  if(!DOCS[doc]||doc==='Comentarios')return notFound();
  const M=$('#main');setHead('Buscar en '+dTitle(doc),'#/dp/'+doc+'/0','doc');
  M.innerHTML=`<input id="q" class="si" type="search" placeholder="Palabra o frase en este libro" value="${esc(q0)}" autocomplete="off"><div id="out" class="mut" style="margin-top:10px"></div>`;
  const q=$('#q');let t;q.oninput=()=>{clearTimeout(t);t=setTimeout(go,300)};
  async function go(){const val=q.value.trim(),out=$('#out');if(val.length<2){out.textContent='Escribe al menos 2 letras.';return}
    history.replaceState(null,'','#/dsearch/'+doc+'/'+encodeURIComponent(val));NAV[NAV.length-1]=location.hash;
    out.textContent='Preparando el índice de búsqueda…';
    let idx;try{idx=await buildDocIdx(doc,(k,n)=>{if(q.value.trim()===val)out.textContent='Preparando el índice de búsqueda… '+k+'/'+n})}catch(e){out.textContent='No se pudo preparar la búsqueda ('+e.message+').';return}
    if(q.value.trim()!==val)return;
    const terms=qTerms(val),tre=terms.map(x=>new RegExp('(^|[^a-zñ0-9])'+x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));const res=[];
    for(const r of idx){if(tre.every(x=>x.test(r.n))){res.push(r);if(res.length>=400)break}}
    const N=DOCS[doc].starts.length;
    out.innerHTML=(res.length?`<div style="margin:6px 0">${res.length>=400?'Más de 400':res.length} resultado(s)${res.length>=400?' (se muestran los primeros)':''}</div>`:'Sin resultados.')+res.map(r=>`<a class="res" href="#/dq/${doc}/${r.k}/${r.i}/${encodeURIComponent(val)}"><b>${r.h?esc(r.h.slice(0,70))+' · ':''}Parte ${r.k+1}/${N}</b>${hiText(snipOf(r,terms),terms)}</a>`).join('')}
  if(q0)go();else q.focus()
}
function markIn(root,terms){const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];while(w.nextNode())nodes.push(w.currentNode);for(const nd of nodes){const s=nd.nodeValue,ns=norm(s),sp=[];terms.forEach(x=>{if(!x)return;let i=0;while((i=ns.indexOf(x,i))>=0){sp.push([i,i+x.length]);i+=x.length}});if(!sp.length)continue;sp.sort((a,b)=>a[0]-b[0]);const f=document.createDocumentFragment();let p=0;for(const [a,b] of sp){if(a<p)continue;f.append(s.slice(p,a));const m=document.createElement('mark');m.textContent=s.slice(a,b);f.append(m);p=b}f.append(s.slice(p));nd.replaceWith(f)}}
function focusPar(i,q){const e=document.querySelectorAll('#dx p,#dx h1,#dx h2,#dx h3,#dx h4,#dx h5,#dx h6')[i];if(!e)return;markIn(e,qTerms(q||''));e.scrollIntoView({block:'start'});window.scrollBy&&window.scrollBy(0,-70);e.classList.add('flash')}
$('#sfab').onclick=()=>{if(sfDoc)location.hash='#/dsearch/'+sfDoc};

/* puntos marcados: estrella, pantalla, exportación */
const EYI=new Map(EY.p.map((p,i)=>[p[0],i]));
document.addEventListener('click',e=>{const s=e.target.closest&&e.target.closest('.st,.star');if(!s)return;e.preventDefault();const n=+s.dataset.n,f=LS.get('eyfav',[]),i=f.indexOf(n);if(i>=0)f.splice(i,1);else f.push(n);LS.set('eyfav',f);document.querySelectorAll('.st[data-n="'+n+'"],.star[data-n="'+n+'"]').forEach(x=>x.classList.toggle('on',i<0))});
$('#hstar').onclick=()=>{location.hash='#/eyfav'};
function eyMarkAll(){const fav=eyFav();document.querySelectorAll('#dx .st').forEach(x=>x.classList.toggle('on',fav.has(+x.dataset.n)))}
function favGroups(){const fav=eyFav(),g=new Map();EY.p.filter(p=>fav.has(p[0])).forEach(p=>{const t=p[2][0];if(!g.has(t))g.set(t,[]);g.get(t).push(p)});return [...g.entries()].sort((a,b)=>a[0]-b[0]).map(([t,l])=>[t,l.sort((a,b)=>a[0]-b[0])])}
const unent=s=>s.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
const mdI=s=>s.replace(/<i>([\s\S]*?)<\/i>/g,(m,t)=>{const l=t.match(/^\s*/)[0],r=t.match(/\s*$/)[0],c=t.trim();return c?l+'*'+c+'*'+r:l+r}).replace(/<\/?i>/g,'');
function favMD(G){let o='# Él y yo — puntos marcados\n\n';G.forEach(([t,l])=>{o+='## '+EY.th[t]+'\n\n';l.forEach(p=>{let first=true;p[1].forEach(f=>f.split('\n').forEach(x=>{o+=(first?'**'+p[0]+'.** ':'')+unent(mdI(x))+'\n\n';first=false}))})});return o+'*Fuente: «El sentir del corazón de Jesús» (Ricardo Sada Fernández), del diario de Gabriela Bossis.*\n'}
function rtfEsc(s){let o='';for(let i=0;i<s.length;i++){const c=s.charCodeAt(i),ch=s[i];if(ch==='\\'||ch==='{'||ch==='}')o+='\\'+ch;else if(c>126)o+='\\u'+(c>32767?c-65536:c)+'?';else o+=ch}return o}
function rtfI(h){return h.split(/(<\/?i>)/).map(t=>t==='<i>'?'{\\i ':t==='</i>'?'}':rtfEsc(unent(t))).join('')}
function favRTF(G){let o='{\\rtf1\\ansi\\ansicpg1252\\deff0{\\fonttbl{\\f0\\froman Georgia;}}\\viewkind4\\uc1\\f0\\fs24\n';o+='{\\pard\\b\\fs36 '+rtfEsc('Él y yo — puntos marcados')+'\\par}\\par\n';G.forEach(([t,l])=>{o+='{\\pard\\b\\fs30\\sb360\\sa120 '+rtfEsc(EY.th[t])+'\\par}\n';l.forEach(p=>{let first=true;p[1].forEach(f=>f.split('\n').forEach(x=>{o+='{\\pard\\sa160 '+(first?'{\\b '+p[0]+'.} ':'')+rtfI(x)+'\\par}\n';first=false}))})});return o+'{\\pard\\sb360\\i\\fs20 '+rtfEsc('Fuente: «El sentir del corazón de Jesús» (Ricardo Sada Fernández), del diario de Gabriela Bossis.')+'\\par}\n}'}
function dlFile(name,mime,text){const b=new Blob([text],{type:mime}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;document.body.append(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},800)}
async function copyText(t){try{await navigator.clipboard.writeText(t);return true}catch(e){const x=document.createElement('textarea');x.value=t;x.style.cssText='position:fixed;opacity:0';document.body.append(x);x.select();let ok=false;try{ok=document.execCommand('copy')}catch(_){}x.remove();return ok}}
function renderFav(){
  setHead('Puntos marcados','#/elyyo','doc');const M=$('#main'),G=favGroups(),n=G.reduce((a,[,l])=>a+l.length,0),fav=eyFav();
  if(!n){M.innerHTML='<h2 class="t">Puntos marcados</h2><p class="mut">Todavía no has marcado ningún punto. Pulsa la ☆ de un punto de «Él y yo» (o del libro) para guardarlo aquí.</p>';return}
  M.innerHTML=`<h2 class="t" style="margin-bottom:4px">Puntos marcados</h2><p class="mut" style="margin:0 0 12px">${n} punto${n>1?'s':''}, ordenados por temas</p><div class="row"><button class="btn" id="xmd">⬇ .md</button><button class="btn" id="xrtf">⬇ .rtf</button><button class="btn" id="xcp">📋 Copiar</button></div>`+G.map(([t,l])=>`<h3 class="thm">${esc(EY.th[t])}</h3>`+l.map(p=>eyCard(EYI.get(p[0]),fav)).join('')).join('');
  const hoy=isoOf(new Date());
  $('#xmd').onclick=()=>dlFile('El-y-yo_puntos-marcados_'+hoy+'.md','text/markdown;charset=utf-8',favMD(favGroups()));
  $('#xrtf').onclick=()=>dlFile('El-y-yo_puntos-marcados_'+hoy+'.rtf','application/rtf',favRTF(favGroups()));
  $('#xcp').onclick=async()=>{const b=$('#xcp'),ok=await copyText(favMD(favGroups()));b.textContent=ok?'✓ Copiado':'No se pudo copiar';setTimeout(()=>b.textContent='📋 Copiar',1800)};
}
'''
NEW_HOME=r"""  if(k===''||k==='dia'){
    renderHome(k==='dia'?h[1]:null);
  }else if(k==='biblia'){
    setHead('Sagrada Escritura','#/');
    const last=LS.get('last',null);
    M.innerHTML='<h2 class="hero">Sagrada Escritura</h2><p class="sub">Elige una sección</p>'+(last?`<a class="cont" href="#/r/${last.b}/${last.c}"><small>Continuar leyendo</small><b>${esc(BK[last.b].name)} · ${esc(BK[last.b].ch[last.c].t)}</b></a>`:'')+'<div class="grid">'+SEC.map((s,i)=>`<a class="btn" href="#/s/${i}">${esc(s.name)}</a>`).join('')+'</div><div class="row"><a class="btn" href="#/search">🔍 Buscar</a><a class="btn" href="#/marks">★ Marcadores</a></div><div class="row"><a class="btn" href="#/docs">📚 Comentarios y libros enlazados</a></div>';
"""

def parchear_index(src,EPA,DAY,meta,EY,meta_ey=None):
    def rep(old,new,count=1):
        nonlocal src
        if src.count(old)!=count: sys.exit('No encuentro en index.html el trozo que hay que modificar (%d veces, esperaba %d):\n   %s\n¿Ha cambiado la plantilla de la app? Hay que adaptar parchear_index().'%(src.count(old),count,old[:90]))
        src=src.replace(old,new)
    rep('<title>Sagrada Escritura</title>','<title>Diario</title>')
    rep('<h1 id="ht">Sagrada Escritura</h1>','<h1 id="ht">Diario</h1><button id="hstar" aria-label="Puntos marcados" style="display:none">★</button>')
    m=re.search(r'const CAT=(\{.*?\});\nconst \$=',src,re.S); raw=m.group(1); C=json.loads(raw)
    C['docs']['Misal']=meta
    if meta_ey: C['docs']['ElYo']=meta_ey
    j=lambda o:json.dumps(o,ensure_ascii=False,separators=(',',':'))
    src=src.replace('const CAT='+raw+';\n','const CAT='+j(C)+';\nconst DAY='+j(DAY)+';\nconst EPA='+j(EPA)+';\nconst EY='+j(EY)+';\n',1)
    rep("const TITLES={Comentarios:'Comentarios',","const TITLES={Misal:'Misal diario',ElYo:'Él y yo',Comentarios:'Comentarios',")
    rep('</style>',CSS+'</style>')
    a=src.index("  if(k===''){"); b=src.index("  }else if(k==='s'){")
    src=src[:a]+NEW_HOME+src[b:]
    rep("setHead(SEC[i].name,'#/');","setHead(SEC[i].name,'#/biblia');")
    rep('<a class="back" href="#/">← Secciones</a>','<a class="back" href="#/biblia">← Secciones</a>')
    rep("setHead('Buscar','#/')","setHead('Buscar','#/biblia','doc')")
    rep("setHead('Marcadores','#/')","setHead('Marcadores','#/biblia','doc')")
    rep("setHead('Libros enlazados','#/')","setHead('Libros enlazados','#/','doc')")
    rep("/^#\\/d/.test(NAV[NAV.length-2]||'')","/^(#\\/d|#\\/$)/.test(NAV[NAV.length-2]||'')")
    rep('function renderDocs(){',JS+'function renderDocs(){')

    rep('<button id="fab" aria-label="Ajustes">⚙</button>','<button id="fab" aria-label="Ajustes">⚙</button>\n<button id="sfab" aria-label="Buscar en este libro" style="display:none">🔍</button>')
    rep("$('#fab').style.display='';bar(null);window.scrollTo(0,0);","$('#fab').style.display='';$('#sfab').style.display='none';$('#hstar').style.display='none';bar(null);window.scrollTo(0,0);")
    rep("  else if(k==='d'||k==='dp'){await renderDoc(h[1],k==='dp'?{page:+h[2]||0}:{off:h[2]===undefined?0:+h[2]})}",
        "  else if(k==='elyyo'){renderEY()}\n  else if(k==='eyfav'){renderFav()}\n  else if(k==='dsearch'){await renderDocSearch(h[1],decodeURIComponent(h[2]||''))}\n  else if(k==='dq'){await renderDoc(h[1],{k:+h[2],i:+h[3],q:decodeURIComponent(h[4]||'')})}\n  else if(k==='d'||k==='dp'){await renderDoc(h[1],k==='dp'?{page:+h[2]||0}:{off:h[2]===undefined?0:+h[2]})}")
    rep("const k=o.page!==undefined?Math.min(Math.max(o.page,0),DOCS[doc].starts.length-1):chunkOf(doc,o.off);","const k=o.k!==undefined?Math.min(Math.max(o.k,0),DOCS[doc].starts.length-1):o.page!==undefined?Math.min(Math.max(o.page,0),DOCS[doc].starts.length-1):chunkOf(doc,o.off);")
    rep("M.innerHTML='<div class=\"doc\" id=\"dx\">'+t+'</div>';","M.innerHTML='<div class=\"doc'+(doc==='Misal'||doc==='Comentarios'?'':' just')+'\" id=\"dx\">'+t+'</div>';sfDoc=doc;$('#sfab').style.display=doc==='Comentarios'?'none':'';$('#hstar').style.display=doc==='ElYo'?'':'none';if(doc==='ElYo')eyMarkAll();if(o.i!==undefined)focusPar(o.i,o.q);")
    return src

def parchear_sw(txt_,sufijo):
    pat=re.compile(r"((?:const|let|var)\s+(?:CACHE\w*|VERSION|VER|V|cacheName)\s*=\s*)(['\"])(.*?)\2")
    m=pat.search(txt_)
    if not m: return txt_,False
    return txt_[:m.start()]+m.group(1)+m.group(2)+re.sub(r'-d[0-9a-f]{8}$','',m.group(3))+'-d'+sufijo+m.group(2)+txt_[m.end():],True

# ============================================================== principal
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pdb'); ap.add_argument('--trabajo'); ap.add_argument('--destino'); ap.add_argument('--epactas')
    ap.add_argument('--sin-biblia',action='store_true'); ap.add_argument('--forzar',action='store_true')
    a=ap.parse_args()
    cfgp=os.path.join(HERE,'config.json'); cfg=json.load(open(cfgp,encoding='utf-8')) if os.path.exists(cfgp) else {}
    rel=lambda p:p if os.path.isabs(p) else os.path.normpath(os.path.join(HERE,p))
    PDB=rel(a.pdb or cfg.get('pdb','pdb')); WORK=rel(a.trabajo or cfg.get('trabajo','trabajo'))
    DEST=rel(a.destino or cfg.get('destino_diario','salida/diario')); EPD=rel(a.epactas or cfg.get('epactas','epactas'))
    PDBM=rel(cfg.get('pdb_misal','pdb_diario'))
    # ------------------------------------------------ 0. app Biblia (proceso de siempre)
    if not a.sin_biblia:
        cmd=[sys.executable,os.path.join(HERE,'actualizar.py')]
        if a.pdb: cmd+=['--pdb',a.pdb]
        if a.trabajo: cmd+=['--trabajo',a.trabajo]
        if a.forzar: cmd.append('--forzar')
        log('ejecutando actualizar.py ...')
        if subprocess.run(cmd,cwd=HERE).returncode: sys.exit('actualizar.py ha fallado: NO se toca el Diario.')
    BASE=WORK+'/app'
    if not os.path.exists(BASE+'/index.html'): sys.exit('No existe %s/index.html: ejecuta antes actualizar.py (o quita --sin-biblia).'%BASE)
    base_index=open(BASE+'/index.html',encoding='utf-8').read()
    bib=Biblia(json.loads(re.search(r'const CAT=(\{.*?\});\nconst \$=',base_index,re.S).group(1)))
    # ------------------------------------------------ 1. epactas
    docs=sorted(f for f in glob.glob(os.path.join(EPD,'*.docx')) if not os.path.basename(f).startswith('~$'))
    if not docs: sys.exit('No hay .docx de epacta en '+EPD)
    EPA={}; informe=[]
    for f in docs:
        d,av=leer_epacta(f); EPA.update(d); ks=sorted(d)
        log('epacta %s: %d días (%s a %s)'%(os.path.basename(f),len(d),ks[0] if ks else '-',ks[-1] if ks else '-'))
        informe.append('Epacta %s: %d días (%s a %s)'%(os.path.basename(f),len(d),ks[0] if ks else '-',ks[-1] if ks else '-'))
        for x in av[:8]: log('   AVISO',x); informe.append('   AVISO '+x)
    corte=(datetime.date.today()-datetime.timedelta(days=400)).isoformat()
    EPA={k:EPA[k] for k in sorted(EPA) if k>=corte}
    huecos=[]; ks=sorted(EPA)
    for x,y in zip(ks,ks[1:]):
        dx=datetime.date.fromisoformat(x); dy=datetime.date.fromisoformat(y)
        if (dy-dx).days>1: huecos.append('%s -> %s'%(x,y))
    if huecos: log('AVISO: la epacta tiene huecos de fechas:',', '.join(huecos[:5])); informe.append('Huecos en la epacta: '+', '.join(huecos))
    # ------------------------------------------------ 2. Misal
    pm=next((p for p in (os.path.join(PDBM,'Misal.pdb'),os.path.join(PDB,'Misal.pdb')) if os.path.exists(p)),None)
    if not pm: sys.exit('No encuentro Misal.pdb (ni en %s ni en %s).'%(PDBM,PDB))
    M,cdir=preparar_misal(pm,bib,WORK,a.forzar)
    ep=sorted(glob.glob(os.path.join(PDBM,'*.epub'))+glob.glob(os.path.join(PDB,'*.epub')))
    if ep:
        EY,est=leer_epub(ep[0]); chunks_ey,meta_ey,npts=epub_a_libro(ep[0])
        edir=os.path.join(WORK,'diario','elyo'); os.makedirs(edir,exist_ok=True)
        for f_ in os.listdir(edir): os.remove(os.path.join(edir,f_))
        for k_,c_ in enumerate(chunks_ey): open(os.path.join(edir,'%d.html'%k_),'w',encoding='utf-8').write(c_)
        log('Libro Él y yo: %d trozos, %d KB, %d puntos con estrella'%(len(chunks_ey),meta_ey['kb'],npts))
        log('Él y yo: %s -> %d puntos distintos (%d apariciones en el libro, %d fragmentos repetidos descartados)'%(os.path.basename(ep[0]),len(EY['p']),est['ocurrencias'],est['fragmentos_repetidos']))
        if est['huerfanos']: log('   AVISO: %d párrafos del libro no se han podido asignar a ningún punto'%est['huerfanos'])
    else:
        EY={'th':[],'p':[]}; meta_ey=None; chunks_ey=[]; log('AVISO: no hay ningún .epub de "El sentir del corazón de Jesús" en %s: la pantalla Él y yo saldrá vacía.'%PDBM)
    meta={'title':'Misal diario','starts':M['starts'],'x':{},'v':M['v'],'kb':M['kb']}
    # ------------------------------------------------ 3. index.html con la portada
    idx=parchear_index(base_index,EPA,M['day'],meta,EY,meta_ey)
    os.makedirs(WORK+'/diario',exist_ok=True)
    open(WORK+'/diario/index.html','w',encoding='utf-8').write(idx)
    suf=sha_text(idx,M['v'])[:8]
    items=[]
    for root,_,files in os.walk(BASE):
        for fn in files:
            r=os.path.relpath(os.path.join(root,fn),BASE).replace(os.sep,'/')
            if r in('index.html','sw.js') or r.startswith('docs/Misal/') or r.startswith('docs/ElYo/'): continue
            items.append((r,os.path.join(root,fn)))
    items.append(('index.html',WORK+'/diario/index.html'))
    if os.path.exists(BASE+'/sw.js'):
        sw,ok=parchear_sw(open(BASE+'/sw.js',encoding='utf-8').read(),suf)
        open(WORK+'/diario/sw.js','w',encoding='utf-8').write(sw); items.append(('sw.js',WORK+'/diario/sw.js'))
        if not ok: log('AVISO: no he encontrado el número de versión en sw.js; si el móvil no se actualiza, cámbialo a mano.')
    for k in range(len(M['starts'])): items.append(('docs/Misal/%d.html'%k,os.path.join(cdir,'%d.html'%k)))
    for k in range(len(chunks_ey)): items.append(('docs/ElYo/%d.html'%k,os.path.join(WORK,'diario','elyo','%d.html'%k)))
    # ------------------------------------------------ 4. comprobaciones
    ids=set()
    for k in range(len(M['starts'])): ids.update(int(x) for x in re.findall(r'id="o(\d+)"',open(os.path.join(cdir,'%d.html'%k),encoding='utf-8').read()))
    rotos=[]
    for k in range(len(M['starts'])):
        for x in re.findall(r'href="#/d/Misal/(\d+)"',open(os.path.join(cdir,'%d.html'%k),encoding='utf-8').read()):
            if int(x) not in ids: rotos.append(('Misal',x))
    sin_enlace=0
    for d,v in M['day'].items():
        offs=[v['o']]+[b[1] for b in v['b']]+[int(x) for x in re.findall(r'#/d/Misal/(\d+)',v['n'])]
        rotos+=[(d,o) for o in offs if o not in ids]
        for r in v['r']:
            if r[0]:
                bb,cc=map(int,r[0].split('/')[2:4])
                if bb>=len(bib.BK) or cc>=len(bib.BK[bb]['ch']): rotos.append((d,r[0]))
            elif re.match(r'^(\d?\s?[A-Za-zñÑ]+\.?\s*\d)',r[1]) and not re.match(r'^(Secuencia|Salmo:|\d.)',r[1]): sin_enlace+=1
    if rotos: sys.exit('ERROR: hay %d enlaces rotos en el Diario; NO se ha tocado el destino. Ejemplos: %s'%(len(rotos),rotos[:5]))
    js=idx[idx.index('<script>')+8:idx.rindex('</script>')]
    if shutil.which('node'):
        open(WORK+'/diario/check.js','w',encoding='utf-8').write(js)
        r=subprocess.run(['node','--check',WORK+'/diario/check.js'],capture_output=True,text=True)
        if r.returncode: sys.exit('ERROR de sintaxis en el JavaScript generado:\n'+r.stderr[:600])
    log('comprobaciones correctas (enlaces del Misal y de las lecturas)')
    # ------------------------------------------------ 5. sincronizar con el destino
    cop=igu=bor=0; rels=set()
    for r,sp in items:
        rels.add(r); d=os.path.join(DEST,r)
        if os.path.exists(d) and os.path.getsize(d)==os.path.getsize(sp) and filecmp.cmp(sp,d,shallow=False): igu+=1; continue
        os.makedirs(os.path.dirname(d),exist_ok=True); shutil.copyfile(sp,d); cop+=1
    for base in ('data','docs'):
        for root,_,files in os.walk(os.path.join(DEST,base)):
            for fn in files:
                r=os.path.relpath(os.path.join(root,fn),DEST).replace(os.sep,'/')
                if r not in rels: os.remove(os.path.join(root,fn)); bor+=1
    log('destino %s: %d archivos copiados/actualizados, %d sin cambios, %d borrados'%(DEST,cop,igu,bor))
    # ------------------------------------------------ 6. informe
    hoy=datetime.date.today().isoformat(); ek=sorted(EPA); dk=sorted(M['day'])
    informe=['Actualizacion del Diario %s'%datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),'']+informe+[
        'Epacta en la app: %d días (%s a %s)'%(len(EPA),ek[0],ek[-1]),
        'Misal %s: %d días (%s a %s), %d trozos, %d KB'%(M['year'],len(dk),dk[0],dk[-1],len(M['starts']),M['kb']),
        'Él y yo: %d puntos distintos; libro completo en %d trozos'%(len(EY['p']),len(chunks_ey)),
        'Hoy (%s): epacta %s, Misal %s'%(hoy,'sí' if hoy in EPA else 'NO','sí' if hoy in M['day'] else 'NO'),
        'Lecturas con referencia bíblica sin enlace: %d'%sin_enlace,
        'Archivos: %d copiados, %d sin cambios, %d borrados'%(cop,igu,bor)]
    if M.get('aviso_dias'): informe.append('Días del Misal cuyo título no coincide con el día de la semana: %s'%M['aviso_dias'])
    open(os.path.join(HERE,'informe_diario.txt'),'w',encoding='utf-8').write('\n'.join(informe)+'\n')
    if ek[-1]<(datetime.date.today()+datetime.timedelta(days=30)).isoformat(): log('AVISO: la epacta acaba el %s; falta añadir el siguiente .docx.'%ek[-1])
    if dk[-1]<(datetime.date.today()+datetime.timedelta(days=30)).isoformat(): log('AVISO: el Misal acaba el %s; falta el Misal.pdb del año siguiente.'%dk[-1])
    log('LISTO. Revisa informe_diario.txt y sube los cambios con Git.')
if __name__=='__main__': main()
