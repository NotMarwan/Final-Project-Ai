import copy
import hashlib
import pytest
from bench.calibrate import calibrate, validate, scale

def dataset():
    rows=[]
    for i,(split,label,score) in enumerate([('calibration',0,.99),('calibration',1,.01),('test',0,.9),('test',1,.1)]):
        rows.append(dict(clip_id=str(i),source_sha256=hashlib.sha256(str(i).encode()).hexdigest(),split=split,label=label,score=score,label_source='publisher'))
    return {'model_sha256':'a'*64,'observations':rows}

def test_temperature_learns_only_from_calibration_split():
    original=dataset(); changed=copy.deepcopy(original)
    for row in changed['observations'][2:]: row['label']=1-row['label']
    assert calibrate(original)['temperature']==calibrate(changed)['temperature']
    assert calibrate(original)['temperature']>1

def test_duplicate_source_is_rejected_across_splits():
    data=dataset();data['observations'][2]['source_sha256']=data['observations'][0]['source_sha256']
    with pytest.raises(ValueError,match='leak'):validate(data)

@pytest.mark.parametrize('score',[float('nan'),float('inf'),-1,2,True])
def test_invalid_measurements_rejected(score):
    data=dataset();data['observations'][0]['score']=score
    with pytest.raises(ValueError,match='finite'):validate(data)

def test_pseudo_labels_cannot_establish_test_truth():
    data=dataset();data['observations'][0]['label_source']='model'
    with pytest.raises(ValueError,match='truth'):validate(data)

def test_candidate_does_not_claim_runtime_calibration():
    result=calibrate(dataset())
    assert result['status']=='candidate-not-runtime-validated'
    assert result['held_out_after']['count']==2
    assert 0<=scale(0, .05)<=1 and 0<=scale(1,.05)<=1
