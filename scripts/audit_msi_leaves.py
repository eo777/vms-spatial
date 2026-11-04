"""Audit f1r/f8r leaf boundaries against independent, ruler-bearing MSI photos.

No copied-text scores or page placements are refitted. All working coordinates
are upright (raw camera image rotated 90 degrees clockwise).
"""
from pathlib import Path
import sys,json,gzip,hashlib
import numpy as np,cv2,tifffile
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d

TK=Path(__file__).resolve().parents[1]
ROOT=TK.parents[1]
sys.path.insert(0,str(TK))
from vmsspatial import images
from vmsspatial.bundle import load_bundle

PILOT=ROOT/'research/bifolium_drift_20261030/msi_pilot'
WEB=PILOT.parent/'chain_search/copy_windows/lexical_pilot/spatial_weights/msi_pilot'
WORK=PILOT/'geometry'
NAMES={'f1r':'Voynich_1r+MB450RB_001_F.tif','f8r':'Voynich_08r+MB450RB_001_F.tif'}
CROPS={'f1r':(130,880,4630,7300),'f8r':(130,1480,4650,7940)}

def project(H,pts):
    return cv2.perspectiveTransform(np.float64(pts).reshape(-1,1,2),H)[:,0]

def intensity(a):
    lo,hi=np.percentile(a,[2,98]);return np.uint8(np.clip((a.astype('float32')-lo)/(hi-lo),0,1)*255)

def ruler(profile):
    s=(profile-np.percentile(profile,10))/(np.percentile(profile,95)-np.percentile(profile,10))
    peaks,_=find_peaks(s,distance=20,prominence=.4)
    assert len(peaks)>30 and np.all((np.diff(peaks)>25)&(np.diff(peaks)<33))
    fit=np.polyfit(np.arange(len(peaks)),peaks,1);res=peaks-np.polyval(fit,np.arange(len(peaks)))
    return dict(px_per_mm=float(fit[0]),ticks=len(peaks),positions_px=peaks.tolist(),rms_px=float(np.sqrt(np.mean(res**2))))

def edge_trace(a,axis,positions,search,skip=()):
    out=[]
    for at in positions:
        if any(lo<=at<=hi for lo,hi in skip):continue
        lo,hi=search
        patch=a[lo:hi,int(at)-20:int(at)+21] if axis=='y' else a[int(at)-20:int(at)+21,lo:hi]
        prof=np.median(patch,axis=1 if axis=='y' else 0).astype(float)
        grad=np.abs(np.gradient(gaussian_filter1d(prof,2)))
        i=int(np.argmax(grad[8:-8]))+8
        out.append([float(at),float(lo+i),float(grad[i])])
    return out

def measure_edges(a,f):
    if f=='f1r':
        return dict(top=edge_trace(a,'y',np.arange(350,4451,150),(810,1030),[(1700,2350)]),
            bottom=edge_trace(a,'y',np.arange(350,4401,150),(7070,7370),[(700,1950)]),
            fold=edge_trace(a,'x',np.arange(1300,7001,250),(70,220)),
            outer=edge_trace(a,'x',np.arange(1400,6901,250),(4420,4700)))
    return dict(top=edge_trace(a,'y',np.arange(400,4401,150),(1370,1640),[(3100,4000)]),
        bottom=edge_trace(a,'y',np.arange(450,4351,150),(7840,8070)),
        fold=edge_trace(a,'x',np.arange(1900,7501,250),(50,220)),
        outer=edge_trace(a,'x',np.arange(1800,7501,250),(4500,4780),[(2600,3300),(6000,6650)]))

def check_text_alignment(f,b,H,scale,raw):
    display=cv2.imread(str(images.image_path(f,'display')),0)
    x0,y0,x1,y1=CROPS[f]
    crop=cv2.resize(raw[y0:y1,x0:x1],(2000,round((y1-y0)/scale)),interpolation=cv2.INTER_AREA)
    lo,hi=np.percentile(crop,[1,99])
    msi=np.uint8(np.clip((crop.astype('float32')-lo)/(hi-lo),0,1)*255)
    sift=cv2.SIFT_create(nfeatures=12000)
    k1,d1=sift.detectAndCompute(display,None);k2,d2=sift.detectAndCompute(msi,None)
    pairs=[m for m,n in cv2.BFMatcher().knnMatch(d1,d2,k=2) if m.distance<.72*n.distance]
    p=np.float32([k1[m.queryIdx].pt for m in pairs]);q=np.float32([k2[m.trainIdx].pt for m in pairs])
    direct,mask=cv2.findHomography(p,q,cv2.RANSAC,4)
    assert direct is not None and mask.sum()>30
    recorded=images.Mapping(images.display_transform(f)).to_frame(p)
    reg=images.registration(f,'beinecke');errors=[];raw_vectors=[]
    boxes=[]
    for line in b['lines']:
        if line['page']==f:
            boxes.extend((b['geometry'][i],line['locus']) for i in range(line['start'],line['end']) if b['geometry'][i])
    crop=CROPS[f]
    for r,t,ok in zip(recorded,q,mask[:,0]):
        if not ok:continue
        locus=next((l for rect,l in boxes if rect[0]<=r[0]<=rect[2] and rect[1]<=r[1]<=rect[3]),None)
        if locus is None:continue
        pred=project(H,images.Mapping(reg,locus).to_image([r]))[0]
        measured=np.array(t)*scale+[crop[0],crop[1]]
        errors.append(float(np.linalg.norm(pred-measured)));raw_vectors.append([*pred,*measured])
    return dict(method='Independent display-to-MSI feature correspondences inside recorded word boxes; compare their locations with the existing display/Beinecke/MSI chain, using saved line shifts.',
        matched_text_features=len(errors),median_raw_px=float(np.median(errors)),p95_raw_px=float(np.percentile(errors,95)),
        feature_vectors_msi=raw_vectors)

def physical_summary(r,reg):
    B=np.array(r['word_polygons_msi']).reshape(-1,2);bounds=np.r_[B.min(0),B.max(0)]
    xc,yc=(bounds[:2]+bounds[2:])/2;ppm=r['ruler']['px_per_mm']
    edges={k:float(np.interp(xc if k in ['top','bottom'] else yc,np.array(a)[:,0],np.array(a)[:,1])) for k,a in r['measured_edges'].items()}
    margins=dict(top=(bounds[1]-edges['top'])/ppm,bottom=(edges['bottom']-bounds[3])/ppm,
                 inner=(bounds[0]-edges['fold'])/ppm,outer=(edges['outer']-bounds[2])/ppm)
    dims=dict(visible_width=(edges['outer']-edges['fold'])/ppm,height=(edges['bottom']-edges['top'])/ppm,
              text_width=(bounds[2]-bounds[0])/ppm,text_height=(bounds[3]-bounds[1])/ppm)
    assert abs(dims['height']-dims['text_height']-margins['top']-margins['bottom'])<1e-8
    assert abs(dims['visible_width']-dims['text_width']-margins['inner']-margins['outer'])<1e-8
    old=r['toolkit_before'];t=old['text'];old_margins=dict(top=(t[1]-old['top'])/old['mm'],bottom=(old['bottom']-t[3])/old['mm'],
        inner=(t[0]-old['fold'])/old['mm'],outer=old['visible_width_mm']-(t[2]-old['fold'])/old['mm'])
    H=np.array(r['yale_to_msi'])@np.array(reg['matrix'])
    origin=np.array([[1/ppm,0,-edges['fold']/ppm],[0,1/ppm,-edges['top']/ppm],[0,0,1]])
    c=project(np.linalg.inv(H),[[xc,yc]])[0]
    basis=project(H,[c,c+[1,0],c+[0,1]])
    local=[ppm/np.linalg.norm(basis[i]-basis[0]) for i in [1,2]]
    anchors=project(np.linalg.inv(H),[[edges['fold'],yc],[edges['outer'],yc],[xc,edges['top']],[xc,edges['bottom']]])
    return dict(text_bounds_msi=bounds.tolist(),edge_intercepts_msi=edges,dimensions_mm=dims,margins_mm=margins,
        existing_margins_mm=old_margins,margin_change_mm={k:margins[k]-old_margins[k] for k in margins},
        recorded_to_upright_msi_global=H.tolist(),recorded_to_msi_mm_global=(origin@H).tolist(),
        local_recorded_px_per_mm_xy=local,recorded_edge_anchor_points=anchors.tolist(),
        note='Projected visible leaf dimensions, not an unfolded or surface-distance measurement. Edge intercepts at the centre of the complete located text envelope. Inner edge is the visible gutter proxy; concealed parchment is not measured. Global matrix is for page anchors; apply saved per-line image shifts before the Yale-to-MSI matrix for words.')

def export(records):
    capture=json.loads((PILOT/'captures.json').read_text());pages={}
    warp_path=TK/'data/manuscript/page_warp.json.gz'
    warp_product=json.loads(gzip.decompress(warp_path.read_bytes()))
    for f,r in records.items():
        summary=physical_summary(r,images.registration(f))
        r['summary']=summary
        align=r['text_alignment'];ppm=r['ruler']['px_per_mm']
        pages[f]={k:v for k,v in r.items() if k not in ['word_polygons_msi','token_indices','text_alignment']}
        pages[f]['text_alignment']={k:v for k,v in align.items() if k!='feature_vectors_msi'}
        pages[f]['text_alignment'].update(median_mm=align['median_raw_px']/ppm,p95_mm=align['p95_raw_px']/ppm)
        pages[f]['source']={k:capture[f+'_450'][k] for k in ['name','drive_id','sha256','bytes']}
        pages[f]['word_count']=len(r['token_indices'])
        w=warp_product['pages'][f]
        pages[f]['existing_warp']={k:w[k] for k in ['fitted','baseline','n_lines','n_points','H_px','expected_gutter','quality']}
        pages[f]['existing_warp'].update(product_version=warp_product['version'],product_sha256=hashlib.sha256(warp_path.read_bytes()).hexdigest(),
            note='Existing shared text-line curvature estimate, not a new MSI warp fit or verified binding distortion. quality.gutter_side names the stronger-curvature side, not a detected physical gutter. Only vertical word positions are corrected; horizontal compression is not recovered.')
        # Compact evidence figure. Green = measured MSI boundaries; orange = saved
        # Yale boundaries carried through the text registration; cyan = word boxes.
        image=cv2.imread(str(WORK/(f+'_old_overlay.jpg')))
        image=cv2.copyMakeBorder(image,125,15,0,0,cv2.BORDER_CONSTANT,value=(250,250,250))
        lines=[f+' | MSI leaf-edge / toolkit alignment audit',
               'Green: visible MSI edge   Orange: transferred toolkit edge   Cyan: recorded boxes',
               'Projected leaf: %.1f x %.1f mm | text margins T/B: %.1f / %.1f mm'%(summary['dimensions_mm']['visible_width'],summary['dimensions_mm']['height'],summary['margins_mm']['top'],summary['margins_mm']['bottom']),
               'Orange/green differences include scan distortion. Gutter remains a visible-edge proxy.']
        for j,t in enumerate(lines):cv2.putText(image,t,(20,29+j*27),cv2.FONT_HERSHEY_SIMPLEX,.63 if j else .8,(45,55,60),1 if j else 2,cv2.LINE_AA)
        cv2.imwrite(str(WEB/(f+'_geometry.jpg')),image,[cv2.IMWRITE_JPEG_QUALITY,88])
    product=dict(version='2026.11.03.1',date_local='2026-11-03',purpose='Independent MSI page-size and margin audit; does not replace the canonical leaves product or refit copy-chain placements.',
        frame='upright MSI pixels and ruler-calibrated projected mm; raw TIFF rotated 90 degrees clockwise',
        checked_box_coordinates='recorded (as drawn), not flat/dewarped; mapped with existing per-line image shifts and the Yale-to-MSI homography',
        scope=['f1r','f8r'],ruler_scale='f1r: 107 one-mm marks on vertical ruler; f8r: 48 marks on upper horizontal ruler, checked against lower ruler. Orthogonal axis assumes square pixels and a near-parallel capture plane.',
        limits=['Both MSI and reference pages remain curved. The external ruler calibrates photographic projection, not surface distance along parchment. A global homography cannot flatten a nonplanar leaf. Different page holding and the concealed gutter prevent an exact full-leaf physical size.',
                'Page edges are sampled curves; quoted margins use their values at the text-envelope centre. Excluded clamp/shadow regions are recorded in the audit script.',
                'Matched-feature residuals assess text registration, not every word-box boundary or the dewarping model.',
                'No independent MSI verso captures were used. Do not force f1v/f8v or other pages to these recto sizes.',
                'Canonical leaves, registrations, flat coordinates and saved copy placements are unchanged. The current scalar paper mapping cannot exactly represent the measured projective mapping.'],
        credit='The Lazarus Project and The Chester F. Carlson Center for Imaging Science at Rochester Institute of Technology. Beinecke Rare Book & Manuscript Library MS 408, f1r and f8r. Visible reference images: Yale University.',
        pages=pages)
    target=TK/'data/manuscript/msi_leaf_audit.json.gz'
    with target.open('wb') as file:
        with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as z:z.write(json.dumps(product,separators=(',',':')).encode())
    # A tiny browser data file; the comprehensive product is in the toolkit.
    (WEB/'geometry.json').write_text(json.dumps({f:dict(summary=p['summary'],text_alignment=p['text_alignment'],ruler=p['ruler']['px_per_mm'],existing_warp=p['existing_warp']) for f,p in pages.items()},indent=2))
    print('wrote',target,'bytes',target.stat().st_size,flush=True)

def old_quad(p):
    t=p['scan']['text_px'];cx=(t[0]+t[2])/2;cy=(t[1]+t[3])/2;s=p['scan']
    def intersect(vertical,horizontal):
        a,b=s[vertical],s[horizontal]
        return np.linalg.solve([[1,-a['slope']],[-b['slope'],1]],[a['at']-a['slope']*cy,b['at']-b['slope']*cx]).tolist()
    return [intersect('fold','top'),intersect('outer','top'),intersect('outer','bottom'),intersect('fold','bottom')]

def main():
    WORK.mkdir(exist_ok=True)
    leaves=json.loads(gzip.decompress((TK/'data/manuscript/leaves.json.gz').read_bytes()))
    refs=json.loads((WEB/'references.json').read_text())
    b=load_bundle('sensitivity',pages='all',order='bifolia',warp='recorded');records={}
    for f in ['f1r','f8r']:
        a=np.rot90(tifffile.imread(PILOT/'temporary'/NAMES[f]),3)
        rr=ruler(np.median(a[100:3200,4800:4900],axis=1)) if f=='f1r' else ruler(np.median(a[1310:1320,3100:4500],axis=0))
        rr['offset']=100 if f=='f1r' else 3100
        if f=='f8r':
            rr['bottom_check']=ruler(np.median(a[8130:8145,2400:5500],axis=0))
        edges=measure_edges(a,f)
        x0,y0,x1,y1=CROPS[f];s=(x1-x0)/2000
        H=np.array([[s,0,x0],[0,s,y0],[0,0,1]])@np.array(refs[f]['recto_to_msi'])
        alignment=check_text_alignment(f,b,H,s,a)
        quad=project(H,old_quad(leaves['pages'][f]));polys=[];inds=[]
        reg=images.registration(f,'beinecke')
        for line in b['lines']:
            if line['page']!=f:continue
            mapping=images.Mapping(reg,line['locus'])
            for i in range(line['start'],line['end']):
                q=b['geometry'][i]
                if q is None:continue
                x,y,X,Y=q;poly=project(H,mapping.to_image([[x,y],[X,y],[X,Y],[x,Y]]));polys.append(poly);inds.append(i)
        preview=cv2.cvtColor(intensity(a),cv2.COLOR_GRAY2BGR)
        cv2.polylines(preview,[np.int32(quad)],True,(0,130,255),20)
        for poly in polys:cv2.polylines(preview,[np.int32(poly)],True,(220,180,0),4)
        for name,pts in edges.items():
            coords=[[x,y] if name in ['top','bottom'] else [y,x] for x,y,_ in pts]
            for q in coords:cv2.circle(preview,tuple(np.int32(q)),10,(100,255,40),-1)
            cv2.polylines(preview,[np.int32(coords)],False,(100,255,40),7)
        preview=cv2.resize(preview,(1226,1635),interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(WORK/(f+'_old_overlay.jpg')),preview,[cv2.IMWRITE_JPEG_QUALITY,94])
        records[f]=dict(ruler=rr,text_alignment=alignment,measured_edges=edges,yale_to_msi=H.tolist(),old_edges_msi=quad.tolist(),toolkit_before=leaves['pages'][f],
            token_indices=inds,word_polygons_msi=np.array(polys).tolist())
        print(f,rr['px_per_mm'],rr['ticks'],'old quad',quad.round(1).tolist(),flush=True)
        print(f,'measured edge medians',{k:round(np.median(np.array(v)[:,1]),2) for k,v in edges.items()},flush=True)
        print(f,'text alignment',alignment['matched_text_features'],alignment['median_raw_px']/rr['px_per_mm'],alignment['p95_raw_px']/rr['px_per_mm'],flush=True)
    (WORK/'measurements.json').write_text(json.dumps(records,indent=2))
    export(records)

if __name__=='__main__':main()
