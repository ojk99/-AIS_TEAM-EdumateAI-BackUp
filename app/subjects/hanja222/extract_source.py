"""공식 HWP 표의 셀 좌표를 보존해 배정급수를 추출한다. pip install olefile"""
import pathlib,struct,zlib,json,re,unicodedata
import olefile

def clean(data):
 units=list(struct.unpack('<'+'H'*(len(data)//2),data));out=[];i=0
 while i<len(units):
  c=units[i]
  if c in [1,2,3,4,5,6,7,8,9,11,12,14,15,16,17,18,19,20,21,22,23]:i+=8
  else:out.append(c);i+=1
 return struct.pack('<'+'H'*len(out),*out).decode('utf-16le',errors='replace')
def cells(path):
 o=olefile.OleFileIO(path);result=[]
 for name in o.listdir():
  if name[0]!='BodyText':continue
  b=zlib.decompress(o.openstream(name).read(),-15);i=0;cell=None
  while i<len(b):
   v=struct.unpack_from('<I',b,i)[0];i+=4;t=v&1023;n=v>>20
   if n==4095:n=struct.unpack_from('<I',b,i)[0];i+=4
   d=b[i:i+n];i+=n
   if t==72 and len(d)>=16:
    cell={'col':struct.unpack_from('<H',d,8)[0],'row':struct.unpack_from('<H',d,10)[0],'text':''};result.append(cell)
   elif t==67 and cell is not None:cell['text']+=clean(d)
 return result
if __name__=='__main__':
 records=[]
 for p in pathlib.Path('/tmp/hanja-source').rglob('*.hwp'):
  low='5~' in p.name
  for c in cells(p):
   col=c['col'];row=c['row']
   if not 1<=col<=(5 if low else 4) or row<(1 if low else 2):continue
   grade=(10-col) if low else (5-col)
   for char in c['text']:
    if '\u3400'<=char<='\u9fff' or '\uf900'<=char<='\ufaff' or ord(char)>=0x20000:
     records.append({'character':char,'normalized':unicodedata.normalize('NFKC',char),'grade':grade})
 print({g:sum(r['grade']==g for r in records) for g in range(1,10)})
 pathlib.Path('hanja/data/characters.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf8')
