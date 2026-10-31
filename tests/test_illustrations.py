import numpy as np
import pytest
from vmsspatial.frames import FrameError
from vmsspatial.illustrations import image_overlay,overlay_svg

pytest.importorskip('PIL')                    # the images extra


def test_overlay_keeps_local_registration_resize_and_original_boxes():
    image=np.full((100,180,3),245,dtype=np.uint8)
    rec=dict(folio='f1r',source='beinecke',ok=True,image_id='example',matrix=[[2,0,10],[0,2,5],[0,0,1]],
             lines={'4':{'dx':3,'dy':-2}},residual_px=.5,flags=[])
    word=dict(id=1,label='<test>',box=[10,10,30,20],line=4,role='target')
    crop,data=image_overlay('f1r',[word],warp='recorded',image=image,registration=rec,pad=0,max_width=20)
    assert data['warp']=='recorded'
    assert crop.size==(20,10)
    assert data['crop_origin']==[33,23]
    assert data['words'][0]['polygon']==[[0.,0.],[20.,0.],[20.,10.],[0.,10.]]
    assert word['box']==data['words'][0]['box']==[10,10,30,20]
    svg=overlay_svg(crop,data,labels=True)
    assert 'data:image/jpeg;base64,' in svg and '&lt;test&gt;' in svg
    with pytest.raises(ValueError,match='different folio'):
        image_overlay('f2r',[word],warp='recorded',image=image,registration=rec)
    with pytest.raises(ValueError,match='Missing local'):
        image_overlay('f1r',[dict(word,line=9)],warp='recorded',image=image,registration=rec)
    with pytest.raises(ValueError,match='positive area'):
        image_overlay('f1r',[dict(word,box=[10,10,9,20])],warp='recorded',image=image,registration=rec)
    with pytest.raises(ValueError,match='unique'):
        image_overlay('f1r',[word,word],warp='recorded',image=image,registration=rec)


def test_overlay_refuses_boxes_whose_warp_state_is_unstated_or_flat():
    image=np.full((100,180,3),245,dtype=np.uint8)
    rec=dict(folio='f1r',source='beinecke',ok=True,image_id='example',matrix=[[2,0,10],[0,2,5],[0,0,1]],lines={'4':{'dx':3,'dy':-2}},residual_px=.5,flags=[])
    word=dict(id=1,label='x',box=[10,10,30,20],line=4,role='target')
    with pytest.raises(FrameError,match='say which warp state'):
        image_overlay('f1r',[word],image=image,registration=rec)
    with pytest.raises(FrameError,match='do not sit on the photograph'):
        image_overlay('f1r',[word],warp='flat',image=image,registration=rec)
