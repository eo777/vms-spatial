"""Import the two poetry controls named by Timm (2016) from local source files.

No text is downloaded or bundled implicitly. Source hashes and normalization
travel with the output in a sidecar provenance file.
"""
import argparse,hashlib,html,json,re
from pathlib import Path

SOURCES={
 'towneley_creation':dict(title='Towneley Plays: The Creation',language='Middle English',
   cited_url='http://name.umdl.umich.edu/Towneley',mirror_url='https://blocksclass.com/libr/TownleyPlays.htm',
   edition='England and Pollard 1897; UVA/OTA electronic transcription',
   scope='The Creatio only, not all Towneley plays',
   rights_note='The electronic-source header restricts commercial use. Text is not bundled or relicensed as toolkit code.'),
 'aeneid':dict(title='Aeneid',language='Latin',
   cited_url='https://sacred-texts.com/cla/virgil/aen/index.htm',
   mirror_url='https://spiritmaji.com/sacredtext/cla/virgil/aen/aenl{01..12}.htm',
   scope='All twelve Latin books; source HTML breaks, not reconstructed canonical metrical numbering',
   edition='Archived Sacred Texts Latin edition')}
NORMALIZATION='Lowercase alphabetic tokens; ampersand expands to and; editorial brackets removed while supplied letters retained; hyphens separate tokens; one-letter positions retained.'

def normalize(text):
    return re.findall(r'[^\W\d_]+',text.replace('[','').replace(']','').replace('&',' and ').lower())

def creation(text):
    if '<' in text:
        text=re.sub(r'<BR\s*/?>|</(?:P|DIV|H[1-6])>', '\n',text,flags=re.I)
        text=html.unescape(re.sub(r'<[^>]+>','',text))
    # The title is a section boundary, never a word to score.
    if 'The Creatio' in text:text=text.split('The Creatio',1)[1]
    text=text.split('The Killing of Abel',1)[0]
    out=[]
    for row in text.splitlines():
        m=re.match(r'^\s*(\d+):\s*(.*)$',row)
        if not m:continue
        s=re.sub(r' (Cherubim|Lucifer|Angelus (?:Malus|Bonus) [12]|Demon [12]|God|Adam|Eue)\s*$','',m[2])
        out.append(dict(book='creation',line=int(m[1]),words=normalize(s)))
    if [r['line'] for r in out]!=list(range(1,268)):raise ValueError('Creation source must contain each numbered line 1..267 exactly once')
    return out

def aeneid_book(text,book):
    parts=re.split(r'</H1>',text,flags=re.I)
    if len(parts)<2:raise ValueError('Expected the archived Aeneid HTML with an H1 heading')
    body=re.split(r'<HR\b|<BLOCKQUOTE\b',parts[1],flags=re.I)[0]
    body=' '.join(body.splitlines())
    body=re.sub(r'<FONT SIZE=2>.*?</FONT>','',body,flags=re.I|re.S)
    body=re.sub(r'<BR\s*/?>|</P>','\n',body,flags=re.I)
    body=html.unescape(re.sub(r'<[^>]+>','',body))
    words=[normalize(s) for s in body.splitlines() if normalize(s)]
    if not words:raise ValueError('No verse lines parsed')
    return [dict(book=str(book),line=i,words=w) for i,w in enumerate(words,1)]

def import_source(name,source_dir):
    root=Path(source_dir);paths=[];rows=[]
    if name=='towneley_creation':
        paths=[next((p for p in (root/'towneley.html',root/'towneley-creation-web-extract.txt') if p.is_file()),None)]
        if paths[0] is None:raise FileNotFoundError('Need towneley.html or towneley-creation-web-extract.txt')
        rows=creation(paths[0].read_text(encoding='utf8'))
    elif name=='aeneid':
        for k in range(1,13):
            p=root/f'aeneid-{k:02}.html';paths.append(p);rows+=aeneid_book(p.read_text(encoding='cp1252'),k)
    else:raise ValueError('Unknown poetry source')
    provenance=dict(SOURCES[name],normalization=NORMALIZATION,paper='https://arxiv.org/abs/1601.07435',
                    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                    source_lines=len(rows),words=sum(len(r['words']) for r in rows))
    return rows,provenance

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('name',choices=list(SOURCES));p.add_argument('--source-dir',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();rows,provenance=import_source(a.name,a.source_dir)
    payload=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf8');dest=Path(a.out);dest.write_bytes(payload)
    provenance['normalized_sha256']=hashlib.sha256(payload).hexdigest();dest.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    print(json.dumps(provenance,indent=2))
if __name__=='__main__':main()
