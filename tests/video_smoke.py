"""Real YOLO check: supply a local driving video; also checks blank/corrupt inputs."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_analysis import analyze_video, VideoError

p=argparse.ArgumentParser()
p.add_argument('video',type=Path)
p.add_argument('--model',type=Path,default=Path('models/yolo26n.pt'))
a=p.parse_args()
import cv2
import numpy as np
with tempfile.TemporaryDirectory() as temp:
    folder=Path(temp)
    result=analyze_video(a.video,folder,a.model)
    assert result['status']=='completed', result
    assert result['detections']
    for name in ['detected.jpg','original.jpg']:
        assert cv2.imread(str(folder/name)) is not None
    blank=folder/'blank.mp4'
    writer=cv2.VideoWriter(str(blank),cv2.VideoWriter_fourcc(*'mp4v'),10,(320,240))
    for _ in range(10):writer.write(np.zeros((240,320,3),np.uint8))
    writer.release()
    empty=analyze_video(blank,folder,a.model)
    assert empty['status']=='no_detection'
    corrupt=folder/'corrupt.mp4';corrupt.write_bytes(b'not a video')
    try:analyze_video(corrupt,folder,a.model)
    except VideoError:pass
    else:raise AssertionError('Corrupt video accepted')
    print(json.dumps({'passed':True,'real_video':result,'blank_status':empty['status'],'corrupt_rejected':True},ensure_ascii=False))
