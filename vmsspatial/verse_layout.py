"""Independent verse pages: no manuscript frames, wrapping or justification.

Every source record remains one physical line. Horizontal units are character
advances; coordinates in the output are arbitrary page units, not scan pixels.
Random dispersion is attached to slots, never to a word's spelling.
"""
from dataclasses import dataclass, asdict
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class VerseLayout:
    char_width: float = 8.0
    word_height: float = 14.0
    line_pitch: float = 20.0
    word_gap: float = 1.0          # character advances
    margin_chars: float = 6.0
    margin_lines: float = 2.0
    lines_per_page: int = 48
    left_jitter: float = 0.0       # bounded +/- character advances per line
    gap_jitter: float = 0.0        # bounded relative change of each word gap
    line_jitter: float = 0.0       # bounded +/- fractions of line pitch
    line_scale_jitter: float = 0.0 # bounded relative change of character width
    page_width_chars: float = None # None expands canvas; fixed width fails, never wraps
    seed: int = 20261030

    def validate(self):
        for name in ['char_width','word_height','line_pitch','word_gap']:
            value=getattr(self,name)
            if not math.isfinite(value) or value<=0:raise ValueError(name+' must be positive and finite')
        for name in ['margin_chars','margin_lines','left_jitter','gap_jitter','line_jitter','line_scale_jitter']:
            value=getattr(self,name)
            if not math.isfinite(value) or value<0:raise ValueError(name+' must be nonnegative and finite')
        if isinstance(self.lines_per_page,bool) or not isinstance(self.lines_per_page,int) or self.lines_per_page<1:raise ValueError('lines_per_page must be a positive integer')
        if self.gap_jitter>=1 or self.line_scale_jitter>=1:raise ValueError('gap and scale jitter must be below 1')
        if self.left_jitter>self.margin_chars:raise ValueError('left jitter would cross the page edge')
        if self.line_jitter>self.margin_lines:raise ValueError('line jitter would cross the page top')
        if self.word_height>self.line_pitch*(1-2*self.line_jitter):raise ValueError('line dispersion would allow overlapping rows')
        if self.page_width_chars is not None and (not math.isfinite(self.page_width_chars) or self.page_width_chars<=2*self.margin_chars):raise ValueError('fixed page width must exceed both margins')
        if isinstance(self.seed,bool) or not isinstance(self.seed,int) or self.seed<0:raise ValueError('seed must be a nonnegative integer')


def typeset_independent(verses, config=None):
    """Make a standard spatial bundle without loading any manuscript data.

    Required records: {book, line, words}. Optional indent_chars and
    space_before_lines preserve measured indentation / stanza gaps. Optional
    source_page on every record preserves supplied page breaks (never guessed).
    Without source_page, pages have at most lines_per_page records and books
    always start a new page. Long lines widen an automatic canvas; a fixed
    canvas rejects them. The word stream and every line remain unchanged.
    """
    cfg=config or VerseLayout();cfg.validate()
    if not isinstance(verses,list) or not verses:raise ValueError('Expected nonempty verse records')
    explicit=any('source_page' in r for r in verses)
    if explicit and not all('source_page' in r for r in verses):raise ValueError('source_page must be supplied for every record or none')
    for r in verses:
        if not all(k in r for k in ['book','line','words']) or not isinstance(r['words'],list) or not r['words']:raise ValueError('Malformed verse record')
        if any(not isinstance(w,str) or not w or any(c.isspace() for c in w) for w in r['words']):raise ValueError('Words must be nonempty strings without whitespace')
        for name in ['indent_chars','space_before_lines']:
            value=r.get(name,0)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError(name+' must be nonnegative and finite')
    rng=np.random.default_rng(cfg.seed);words=[];geometry=[];lines=[];source_ids=[];books=[];pages=[]
    page=-1;in_page=0;yrow=0.;previous=None;seen=set();seen_books=set();previous_book=None
    for vi,r in enumerate(verses):
        book=str(r['book']);key=(book,str(r['source_page'])) if explicit else book
        if book!=previous_book:
            if book in seen_books:raise ValueError('A book must occupy contiguous records')
            seen_books.add(book);previous_book=book
        new=page<0 or key!=previous or (not explicit and in_page>=cfg.lines_per_page)
        if new:
            if explicit and key in seen:raise ValueError('A source page must occupy contiguous records')
            seen.add(key);page+=1;in_page=0;yrow=0.
            pages.append(dict(page=f'verse:{page+1}',book=book,source_page=r.get('source_page'),width=0.,height=0.,start_line=len(lines),end_line=len(lines)))
        previous=key;yrow+=r.get('space_before_lines',0)
        # Consume the same RNG draws even when amplitudes are zero, so variants
        # share corresponding slot-level random values and shuffles replay exactly.
        left=rng.uniform(-1,1);vertical=rng.uniform(-1,1);scale=rng.uniform(-1,1)
        cw=cfg.char_width*(1+cfg.line_scale_jitter*scale)
        x=cfg.char_width*(cfg.margin_chars+r.get('indent_chars',0)+cfg.left_jitter*left)
        y=cfg.line_pitch*(cfg.margin_lines+yrow+cfg.line_jitter*vertical)
        start=len(words)
        for wi,w in enumerate(r['words']):
            g=[float(x),float(y),float(x+len(w)*cw),float(y+cfg.word_height)]
            geometry.append(g);words.append(w);source_ids.append(vi);books.append(book)
            x=g[2]
            if wi<len(r['words'])-1:x+=cfg.char_width*cfg.word_gap*(1+cfg.gap_jitter*rng.uniform(-1,1))
        extent=x+cfg.char_width*cfg.margin_chars
        if cfg.page_width_chars is not None and extent>cfg.page_width_chars*cfg.char_width+1e-9:
            raise ValueError(f'Book {book}, source line {r["line"]} exceeds fixed page width; increase width, never wrap')
        lines.append(dict(page=pages[-1]['page'],locus=f'{book}:{r["line"]}',bifolium=pages[-1]['page'],
            start=start,end=len(words),source_verse=vi,source_line=r['line'],book=book,
            character_width=float(cw),indent_chars=r.get('indent_chars',0),space_before_lines=r.get('space_before_lines',0),overflow=False))
        pages[-1]['width']=max(pages[-1]['width'],extent);pages[-1]['height']=max(pages[-1]['height'],y+cfg.word_height+cfg.margin_lines*cfg.line_pitch)
        pages[-1]['end_line']=len(lines);in_page+=1;yrow+=1
    # One common canvas width per text, preserving ragged line endings. No glyph
    # or word is stretched to fill it. Explicit fixed width remains literal.
    width=cfg.page_width_chars*cfg.char_width if cfg.page_width_chars else max(p['width'] for p in pages)
    for p in pages:p['width']=float(width)
    maxerr=0.
    for r in lines:
        for i in range(r['start'],r['end']):
            g=geometry[i];maxerr=max(maxerr,abs((g[2]-g[0])/(len(words[i])*r['character_width'])-1))
        assert words[r['start']:r['end']]==verses[r['source_verse']]['words']
    return dict(schema=2,window=100,words=words,geometry=geometry,lines=lines,book=books,source_verse=source_ids,
        components={w:list(w) for w in set(words)},component_mode='letters; letter pairs',geometry_kind='synthetic',mode='independent_verse',
        layout_config=asdict(cfg),page_layout=pages,source_sha256=hashlib.sha256(json.dumps(verses,separators=(',',':')).encode()).hexdigest(),
        geometry_provenance=dict(kind='independent synthetic verse pages',units='arbitrary page units',manuscript_frames_used=False,
            historical_page_reconstruction=False,explicit_source_pages=explicit,bifolium_field='synthetic page grouping only; no inferred binding'),
        audit=dict(source_tokens=len(words),source_verses=len(verses),physical_rows=len(lines),source_verses_split_across_rows=0,
            pages=len(pages),overflow_rows=0,no_box=0,max_character_width_ratio_error=float(maxerr)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--out',required=True)
    for name,field in VerseLayout.__dataclass_fields__.items():
        p.add_argument('--'+name.replace('_','-'),type=int if name in ['seed','lines_per_page'] else float,default=field.default)
    a=p.parse_args();config=VerseLayout(**{n:getattr(a,n) for n in VerseLayout.__dataclass_fields__})
    bundle=typeset_independent(json.loads(Path(a.source).read_text(encoding='utf8')),config)
    from vmsspatial.bundle import validate_bundle,save_bundle
    validate_bundle(bundle);save_bundle(bundle,a.out);print(json.dumps(bundle['audit'],indent=2))

if __name__=='__main__':main()
