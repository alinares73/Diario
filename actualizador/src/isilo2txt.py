#!/usr/bin/env python3
"""
isilo2txt.py - Extrae el texto de un ebook iSilo 3.x/4.x (.pdb, type SDoc / creator SilX).

Reimplementacion del descompresor interno de iSilo.exe obtenida por ingenieria
inversa del binario. El algoritmo es DEFLATE (RFC 1951) con tres variaciones:
  - No hay cabeceras de bloque (ni BFINAL ni BTYPE): un unico bloque dinamico.
  - La definicion de los arboles Huffman vive en un rango de bytes del registro
    distinto del de los datos comprimidos, con su propio flujo de bits.
  - El flujo de bits se lee en palabras de 32 bits BIG-ENDIAN, y dentro de cada
    palabra los bits se consumen del menos significativo al mas significativo.
Los codigos de longitud/distancia son identicos a los de RFC 1951.

Uso:  python isilo2txt.py libro.pdb [salida.txt]
"""
import struct, sys, os

_LB = [11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227]
LEN_BASE = {s: _LB[i] for i, s in enumerate(range(0x109, 0x11d))}
DIST_BASE = [0,0,0,0,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,
             1025,1537,2049,3073,4097,6145,8193,12289,16385,24577]
CLORDER = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]


class Bits:
    """Lector de bits: palabras de 32 bits big-endian, bits LSB-first."""
    def __init__(self, data, byte_off, ndwords):
        self.d = data; self.p = byte_off; self.n = ndwords
        self.mask = 0; self.val = 0; self.err = 0

    def bit(self):
        if self.mask == 0:
            if self.n == 0 or self.p + 4 > len(self.d):
                self.err = 1; return 0
            self.val = struct.unpack('>I', self.d[self.p:self.p + 4])[0]
            self.p += 4; self.n -= 1; self.mask = 1
        m = self.mask
        self.mask = (self.mask << 1) & 0xffffffff
        return 1 if (self.val & m) else 0

    def bits(self, k):
        v = 0
        for i in range(k):
            if self.bit(): v |= 1 << i
        return v


class Tree:
    """Arbol binario explicito, como el que construye iSilo (max 16 niveles)."""
    def __init__(self, n):
        self.n = n; self.L = [0] * (n + 2); self.R = [0] * (n + 2)

    def build(self, lengths):
        n = self.n
        self.L = [0] * (2 * n + 4); self.R = [0] * (2 * n + 4)
        nxt = 1; code = 0
        for ln in range(1, 17):
            for sym in range(n):
                if lengths[sym] == ln:
                    node = 0; bp = ln
                    while True:
                        bp -= 1
                        if bp == 0: break
                        if node > n: return False
                        arr = self.R if (code >> bp) & 1 else self.L
                        if arr[node] == 0:
                            arr[node] = nxt; nxt += 1
                        node = arr[node]
                    leaf = sym + 1 + n
                    if code & 1: self.R[node] = leaf
                    else: self.L[node] = leaf
                    code += 1
            code <<= 1
        return True

    def decode(self, br):
        node = 0
        for _ in range(16):
            v = self.R[node] if br.bit() else self.L[node]
            if v > self.n: return v - self.n - 1
            node = v
        return None


def build_trees(rec, dw_off, dw_len):
    br = Bits(rec, dw_off * 4, dw_len)
    hlit = br.bits(5) + 0x101
    hdist = br.bits(5) + 1
    hclen = br.bits(4) + 4
    if not (hlit < 0x11f and hdist < 0x1f and hclen < 0x14):
        raise ValueError("cabecera de arboles invalida")
    cl = [0] * 19
    for i in range(hclen):
        cl[CLORDER[i]] = br.bits(3)
    clt = Tree(0x13)
    if not clt.build(cl): raise ValueError("arbol de longitudes invalido")

    def read_lengths(count, total):
        out = []; prev = 0
        while len(out) < count:
            sym = clt.decode(br)
            if sym is None: raise ValueError("fallo al decodificar longitudes")
            if sym < 16: out.append(sym); prev = sym
            elif sym == 16: out += [prev] * (br.bits(2) + 3)
            elif sym == 17: out += [0] * (br.bits(3) + 3)
            elif sym == 18: out += [0] * (br.bits(7) + 11)
            else: raise ValueError("simbolo %d inesperado" % sym)
        return (out + [0] * total)[:total]

    lt = Tree(0x11e); lt.build(read_lengths(hlit, 0x11e))
    dt = Tree(0x1e);  dt.build(read_lengths(hdist, 0x1e))
    return lt, dt


def inflate(rec, dw_off, dw_len, lt, dt, maxout=0x1000):
    br = Bits(rec, dw_off * 4, dw_len)
    out = bytearray()
    while br.err == 0:
        sym = lt.decode(br)
        if sym is None: break
        if sym < 0x100:
            if len(out) >= maxout: break
            out.append(sym); continue
        if sym == 0x100: break
        if sym < 0x109: ln = sym - 0xfe
        elif sym < 0x11d: ln = br.bits((sym - 0x105) >> 2) + LEN_BASE[sym]
        elif sym == 0x11d: ln = 0x102
        else: break
        dc = dt.decode(br)
        if dc is None or dc > 0x1c: break
        dist = dc + 1 if dc < 4 else br.bits((dc - 2) >> 1) + DIST_BASE[dc]
        if dist > len(out) or dist == 0: break
        if maxout - len(out) < ln: ln = maxout - len(out)
        src = len(out) - dist
        for i in range(ln): out.append(out[src + i])
        if len(out) >= maxout: break
    return bytes(out)


class NotISilo(ValueError):
    """El fichero no es un ebook iSilo 3.x/4.x."""


def read_records(path):
    d = open(path, 'rb').read()
    if len(d) < 78:
        raise NotISilo("%s: fichero demasiado corto" % os.path.basename(path))
    if d[60:64] != b'SDoc' or d[64:68] != b'SilX':
        raise NotISilo("no es un iSilo 3.x/4.x (type=%s creator=%s)"
                       % (d[60:64].decode('latin1'), d[64:68].decode('latin1')))
    num = struct.unpack('>H', d[76:78])[0]
    offs = [struct.unpack('>I', d[78 + 8 * i:82 + 8 * i])[0] for i in range(num)]
    ends = offs[1:] + [len(d)]
    return [d[offs[i]:ends[i]] for i in range(num)]


def decompress_record(rec):
    hdrsz = rec[0]; section = rec[1]
    ndw = len(rec) // 4
    base = hdrsz + rec[hdrsz]
    o = []; p = base
    while p + 2 <= len(rec):
        v = struct.unpack('>H', rec[p:p + 2])[0]
        o.append(v); p += 2
        if v >= ndw: break
    if len(o) < 2: return section, b''
    lt, dt = build_trees(rec, o[0], o[1] - o[0])
    out = bytearray()
    for k in range(1, len(o) - 1):
        a, b = o[k], o[k + 1]
        if a >= b or b > ndw: break
        out += inflate(rec, a, b - a, lt, dt)
    return section, bytes(out)


def extract_text(path):
    chunks = []
    for rec in read_records(path):
        if len(rec) < 8 or rec[0] < 4: continue
        if rec[1] != 0x00: continue            # seccion 0 = "Text"
        try:
            _, out = decompress_record(rec)
        except Exception:
            continue
        chunks.append(out)
    raw = b''.join(chunks)
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode('latin-1', 'replace')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.txt'
    txt = extract_text(src)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(txt)
    print("%s -> %s  (%d caracteres, %d parrafos)"
          % (os.path.basename(src), os.path.basename(dst), len(txt), txt.count('\n') + 1))
