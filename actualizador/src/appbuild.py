"""Construye la app web (index.html, sw.js, data/, docs/) a partir del HTML convertido de los .pdb."""
import re, json, os, hashlib, bisect, html as H
from urllib.parse import unquote
# --- catalogo (orden del archivo) ---
BOOKS=[("Génesis","Gn"),("Éxodo","Ex"),("Levítico","Lv"),("Números","Nm"),("Deuteronomio","Dt"),
("Josué","Jos"),("Jueces","Jue"),("Rut","Rt"),("1 Samuel","1S"),("2 Samuel","2S"),("1 Reyes","1R"),("2 Reyes","2R"),
("1 Crónicas","1Cro"),("2 Crónicas","2Cro"),("Esdras","Esd"),("Nehemías","Ne"),("Tobías","Tb"),("Judit","Jdt"),("Ester","Est"),
("1 Macabeos","1M"),("2 Macabeos","2M"),("Job","Jb"),("Salmos","Sal"),("Cantar de los Cantares","Ct"),("Lamentaciones","Lm"),
("Proverbios","Pr"),("Eclesiastés","Qo"),("Sabiduría","Sb"),("Eclesiástico","Si"),("Isaías","Is"),("Jeremías","Jr"),("Baruc","Ba"),
("Ezequiel","Ez"),("Daniel","Dn"),("Oseas","Os"),("Joel","Jl"),("Amós","Am"),("Abdías","Ab"),("Jonás","Jon"),("Miqueas","Mi"),
("Nahún","Na"),("Habacuc","Hab"),("Sofonías","So"),("Ageo","Ag"),("Zacarías","Za"),("Malaquías","Ml"),
("Mateo","Mt"),("Marcos","Mc"),("Lucas","Lc"),("Juan","Jn"),("Hechos de los Apóstoles","Hch"),("Romanos","Rm"),
("1 Corintios","1Co"),("2 Corintios","2Co"),("Gálatas","Ga"),("Efesios","Ef"),("Filipenses","Flp"),("Colosenses","Col"),
("1 Tesalonicenses","1Ts"),("2 Tesalonicenses","2Ts"),("1 Timoteo","1Tm"),("2 Timoteo","2Tm"),("Tito","Tt"),("Filemón","Flm"),
("Hebreos","Hb"),("Santiago","St"),("1 Pedro","1P"),("2 Pedro","2P"),("1 Juan","1Jn"),("2 Juan","2Jn"),("3 Juan","3Jn"),("Judas","Jds"),("Apocalipsis","Ap")]
assert len(BOOKS)==73
SECT=[("Pentateuco",range(0,5)),("Históricos",range(5,21)),
("Sapienciales",[22,23,25,26,27,28,21]),
("Proféticos",[29,30,24,31,32,33]+list(range(34,46))),
("Evangelios",range(46,51)),("Ep. paulinas",range(51,65)),("C. católicas",list(range(65,72))+[72])]
# Job va primero en sapienciales
SECT[2]=("Sapienciales",[21,22,25,26,27,28,23])
SECT[2]=("Sapienciales",[21,22,25,26,27,23,28][:0]+[21,22,25,26,27,28,23])
used=sorted(i for _,r in SECT for i in r); assert used==list(range(73)),used

def build(SRC, OUT, DOCS, plantillas, log=print, CHUNK=400000):
    WRITTEN=set(); REPORT={}; stats_files={'nuevos':0,'cambiados':0,'iguales':0}
    def put(rel,text):
        data=text if isinstance(text,bytes) else text.encode('utf-8')
        p=os.path.join(OUT,rel); WRITTEN.add(rel.replace(os.sep,'/'))
        if os.path.exists(p):
            with open(p,'rb') as f:
                if f.read()==data: stats_files['iguales']+=1; return hashlib.md5(data).hexdigest()[:8]
            stats_files['cambiados']+=1
        else: stats_files['nuevos']+=1
        os.makedirs(os.path.dirname(p),exist_ok=True)
        with open(p,'wb') as f: f.write(data)
        return hashlib.md5(data).hexdigest()[:8]
    # ------------------------------------------------------------ Biblia
    h=open(SRC+'/Biblia.html',encoding='utf-8').read()
    body=h[h.index('<body>')+6:h.index('</body>')]
    RAW=re.findall(r'<p([^>]*)>(.*?)</p>',body,flags=re.S)
    def clean(x):
        x=re.sub(r'<span id="o\d+"></span>','',x); return re.sub(r'</?a\b[^>]*>','',x)
    def comlink(b):
        m=re.search(r'href="Comentarios\.html#o(\d+)"',b); return int(m.group(1)) if m else None
    def doff(a):
        m=re.search(r'data-o="(\d+)"',a); return int(m.group(1)) if m else None
    START=1586
    titles=[i for i,(a,b) in enumerate(RAW) if i>=START and 'font-size:1.25em' in b]; assert len(titles)==73
    titles.append(len(RAW))
    CH=re.compile(r'^\*?\s*(Capítulo|Salmo)\s+(\d+)(.*)$')
    def txt(b): return H.unescape(re.sub(r'<[^>]+>','',b)).replace('\xa0',' ').strip()
    def inline(b):
        b=re.sub(r'</span></sup><sup><span[^>]*>','',b)
        b=re.sub(r'<sup><span[^>]*>(.*?)</span></sup>',lambda m:'\x01%s\x02'%m.group(1),b)
        b=re.sub(r'<span[^>]*>','',b); b=b.replace('</span>','')
        return re.sub(r'</b><b>','',b)
    MAP=[]  # (offset,b,c,v)
    def build_book(k):
        to=doff(RAW[titles[k]][0])
        if to is not None: MAP.append((to,k,0,None))
        items=[]
        for a,braw in RAW[titles[k]+1:titles[k+1]]:
            if 'class="blank"' in a: continue
            b=clean(braw); t=txt(b)
            if not t: continue
            o=doff(a); L=comlink(braw)
            m=CH.match(t)
            if 'font-size:1.08em' in b and m: items.append(('chap',re.sub(r'^\*\s*','',t),o,L)); continue
            bi=inline(b); mv=re.match(r'^\s*\x01([^\x02]*)\x02\s*',bi)
            if not mv and re.fullmatch(r'\s*(<b>.*</b>\s*)+',bi,flags=re.S):
                items.append(('sec' if 'font-size:1.17em' in b else 'sub',re.sub(r'</?b>','',bi).replace('\x01','').replace('\x02','').strip(),o,None)); continue
            if mv: items.append(('v',mv.group(1),bi[mv.end():].strip(),o,L))
            else: items.append(('c',bi.replace('\x01','<b class="n">').replace('\x02','</b>').strip(),o,None))
        chs=[]; cur={'t':None,'items':[],'o':None,'k':None}
        for it in items:
            if it[0]=='chap':
                carry=[]
                while cur['items'] and cur['items'][-1][0] in('sec','sub'): carry.insert(0,cur['items'].pop())
                chs.append(cur); cur={'t':it[1],'items':carry,'o':it[2],'k':it[3]}
            else: cur['items'].append(it)
        chs.append(cur)
        first=chs[0]
        if first['t'] is None:
            if len(chs)>1:
                if any(i[0] in('v','c') for i in first['items']): first['t']='Introducción'
                else: chs[1]['items']=first['items']+chs[1]['items']; chs=chs[1:]
            else: first['t']='Capítulo 1'
        out=[]
        for ci,c in enumerate(chs):
            parts=[]; cur_v=None
            def numtag(n,L): return ('<a class="n" href="#/d/Comentarios/%d">%s</a>'%(L,n)) if L else '<b class="n">%s</b>'%n
            for it in c['items']:
                if it[0]=='sec': parts.append('</div>' if cur_v else ''); cur_v=None; parts.append('<h3>%s</h3>'%it[1])
                elif it[0]=='sub': parts.append('</div>' if cur_v else ''); cur_v=None; parts.append('<h4>%s</h4>'%it[1])
                elif it[0]=='v':
                    if cur_v: parts.append('</div>')
                    cur_v=it[1]
                    parts.append('<div class="vs" data-v="%s"><p>%s %s</p>'%(it[1],numtag(it[1],it[4]),it[2]))
                    if it[3] is not None: MAP.append((it[3],k,ci,it[1]))
                else:
                    if cur_v: parts.append('<p class="c">%s</p>'%it[1])
                    else: parts.append('<p>%s</p>'%it[1])
            if cur_v: parts.append('</div>')
            lab=c['t']; m=re.match(r'^(?:Capítulo|Salmo)\s+(.*)$',lab)
            e={'t':lab,'n':(m.group(1) if m else lab),'h':''.join(parts)}
            if c['k']: e['k']=c['k']
            out.append(e)
            first_o=c['o'] if c['o'] is not None else next((i[2] if i[0] in('sec','sub','c') else i[3] for i in c['items'] if (i[2] if i[0] in('sec','sub','c') else i[3]) is not None),None)
            if first_o is not None: MAP.append((first_o,k,ci,None))
        return out
    cat=[]; bv={}
    for k,(name,ab) in enumerate(BOOKS):
        chs=build_book(k)
        bv[k]=put('data/b%02d.json'%k,json.dumps({'id':k,'name':name,'ch':chs},ensure_ascii=False,separators=(',',':')))
        cat.append({'id':k,'name':name,'ab':ab,'ch':[{'t':c['t'],'n':c['n']} for c in chs]})
    MAP.sort(key=lambda m:m[0])
    import bisect
    MO=[m[0] for m in MAP]
    def bible_route(N):
        i=bisect.bisect_right(MO,N)-1
        if i<0: return '#/'
        _,b,c,v=MAP[i]
        # el destino cae dentro de un capitulo posterior al de la entrada? usar la entrada
        return '#/r/%d/%d'%(b,c)+('/'+v if v else '')
    # ------------------------------------------------------------ Documentos enlazados
    def sanitize(b):
        b=re.sub(r' title="[^"]*"','',b)
        def st(m):
            s=';'.join(x for x in m.group(1).split(';') if x.strip() and not x.strip().startswith('color'))
            return ' style="%s"'%s if s else ''
        b=re.sub(r' style="([^"]*)"',st,b)
        b=re.sub(r'<span>(.*?)</span>',r'\1',b,flags=re.S)
        return b
    def rew_factory(doc):
        stats={'ok':0,'drop':0}
        def rew(m):
            href=m.group(1); rest=m.group(2); inner=m.group(3)
            if href.startswith('#o'): new='#/d/%s/%s'%(doc,href[2:])
            else:
                f,i=href.rsplit('.html#o',1); f=unquote(f)
                if f=='Biblia': new=bible_route(int(i))
                elif f in DOCS: new='#/d/%s/%s'%(f,i)
                else: new=None
            if new is None: stats['drop']+=1; return inner
            stats['ok']+=1
            cls=re.search(r'class="([^"]*)"',rest); cl=cls.group(1).replace('xdoc','').strip() if cls else ''
            return '<a href="%s"%s>%s</a>'%(new,' class="%s"'%cl if cl else '',inner)
        return rew,stats
    meta={}
    for doc in DOCS:
        h=open(SRC+'/%s.html'%doc,encoding='utf-8').read()
        body=h[h.index('<body>')+6:h.index('</body>')]
        body=body[body.index('</h1>')+5:]
        paras=re.findall(r'<p([^>]*)>(.*?)</p>',body,flags=re.S)
        rew,stats=rew_factory(doc)
        chunks=[];cur=[];size=0;starts=[];curstart=None
        title=None
        for a,b in paras:
            o=doff(a)
            if 'class="blank"' in a and 'id=' not in a: continue
            if title is None:
                t=txt(re.sub(r'<[^>]+>','',b))
                if t and len(t)>2 and 'Sagrada Escritura' not in t and t!='Libros': title=t[:60]
            b=re.sub(r'<a ([^>]*?)href="([^"]+)"([^>]*)>(.*?)</a>',lambda m:rew(type('M',(),{'group':lambda s,i,m=m:[None,m.group(2),m.group(1)+m.group(3),m.group(4)][i]})()),b,flags=re.S)
            b=re.sub(r'<a class="obj[^"]*"[^>]*>(.*?)</a>',r'\1',b,flags=re.S)
            b=sanitize(b)
            a2=re.sub(r' class="cell"','',a); a2=re.sub(r'class="cell ','class="',a2); a2=re.sub(r' class="cell\s+',' class="',a2)
            p='<p%s>%s</p>'%(a2,b) if not b.strip()=='' else '<p%s></p>'%a2
            if o is not None and size>=CHUNK:
                chunks.append(''.join(cur)); starts.append(curstart); cur=[];size=0;curstart=None
            if o is not None and curstart is None: curstart=o
            cur.append(p); size+=len(p)
        chunks.append(''.join(cur)); starts.append(curstart if curstart is not None else 0)
        starts[0]=0
        ids={}; dh=hashlib.md5()
        for k,c in enumerate(chunks):
            dh.update(c.encode()); put('docs/%s/%d.html'%(doc,k),c)
            for m in re.finditer(r'id="o(\d+)"',c): ids[int(m.group(1))]=k
        def rule(N): return max(0,bisect.bisect_right(starts,N)-1)
        exc={N:k for N,k in ids.items() if rule(N)!=k}
        meta[doc]={'title':title or doc,'starts':starts,'x':exc,'v':dh.hexdigest()[:8],'kb':sum(len(c.encode()) for c in chunks)//1024}
        REPORT[doc]=dict(stats); log('  %s: %d trozos, %d KB, enlaces %s'%(doc,len(chunks),meta[doc]['kb'],stats))
    CAT={'books':cat,'sections':[{'name':n,'books':list(r)} for n,r in SECT],'docs':meta,'bv':bv}
    catjson=json.dumps(CAT,ensure_ascii=False,separators=(',',':'))
    put('catalog.json',catjson)

    # ---- index.html, sw.js, manifest e iconos
    core=['data/b%02d.json?v=%s'%(k,bv[k]) for k in range(73)]
    core+=['docs/Comentarios/%d.html?v=%s'%(k,meta['Comentarios']['v']) for k in range(len(meta['Comentarios']['starts']))]
    tpl=open(os.path.join(plantillas,'index.tpl.html'),encoding='utf-8').read()
    put('index.html',tpl.replace('/*CATALOG*/',catjson))
    build_id=hashlib.md5((tpl+catjson+''.join(bv.values())).encode()).hexdigest()[:10]
    sw=open(os.path.join(plantillas,'sw.tpl.js'),encoding='utf-8').read()
    sw=sw.replace('/*BUILD*/',build_id).replace('/*CORE*/',','.join("'%s'"%u for u in core)).replace('/*DOCV*/',json.dumps({d:meta[d]['v'] for d in meta}))
    put('sw.js',sw)
    for f in ('manifest.webmanifest','icon-192.png','icon-512.png'):
        put(f,open(os.path.join(plantillas,f),'rb').read())
    # ---- borrar de data/ y docs/ lo que ya no se genera
    borrados=0
    for base in ('data','docs'):
        for root,_,files in os.walk(os.path.join(OUT,base)):
            for fn in files:
                rel=os.path.relpath(os.path.join(root,fn),OUT).replace(os.sep,'/')
                if rel not in WRITTEN: os.remove(os.path.join(root,fn)); borrados+=1
    stats_files['borrados']=borrados
    return dict(files=stats_files,report=REPORT,catalog=CAT,build_id=build_id)
