"""Local vehicle-frame extraction; this does not detect collisions or assign fault."""
from pathlib import Path
import math
import time


class VideoError(Exception):
    pass


def analyze_video(source, output, model_path, progress=lambda value: None):
    import cv2
    from ultralytics import YOLO

    if not Path(model_path).is_file():
        raise VideoError('모델 파일이 없습니다. 실행 안내에 따라 모델을 준비해 주세요.')
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise VideoError('영상을 읽지 못했습니다. H.264 MP4로 변환해 다시 시도해 주세요.')
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not all(math.isfinite(v) and v > 0 for v in (fps, frames, width, height)):
            raise VideoError('영상의 길이·크기 정보를 확인하지 못했습니다.')
        if frames / fps > 120 or width * height > 3840 * 2160:
            raise VideoError('2분 이하, 4K 이하의 짧은 영상으로 다시 시도해 주세요.')
        model = YOLO(str(model_path))
        # Resolve labels rather than assuming custom-model class IDs are COCO IDs.
        classes = [i for i, name in model.names.items() if name in ('car', 'motorcycle', 'bus', 'truck')]
        if not classes:
            raise VideoError('차량 분류가 있는 COCO 탐지 모델이 필요합니다.')
        stride = max(1, round(fps / 2))
        started = time.monotonic()
        for index in range(int(frames)):
            if time.monotonic() - started > 180:
                raise VideoError('처리 시간이 초과됐습니다. 더 짧은 영상으로 시도해 주세요.')
            ok = cap.grab()
            if not ok:
                raise VideoError('영상 중간을 읽지 못했습니다. 파일을 확인해 주세요.')
            if index % stride:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                raise VideoError('영상 프레임을 읽지 못했습니다.')
            progress(min(99, round((index + 1) / frames * 100)))
            result = model.predict(frame, classes=classes, conf=0.5, imgsz=640,
                                   device='cpu', verbose=False)[0]
            if not len(result.boxes):
                continue
            output = Path(output)
            if not cv2.imwrite(str(output / 'original.jpg'), frame):
                raise VideoError('사진 저장에 실패했습니다.')
            if not cv2.imwrite(str(output / 'detected.jpg'), result.plot()):
                raise VideoError('인식 결과 사진 저장에 실패했습니다.')
            detections = [dict(label=model.names[int(box.cls.item())],
                               confidence=round(float(box.conf.item()), 4),
                               xyxy=[round(float(x), 1) for x in box.xyxy[0].tolist()])
                          for box in result.boxes]
            return dict(status='completed', progress=100, timestamp_seconds=round(index / fps, 3),
                        frame_index=index, detections=detections, model=Path(model_path).name,
                        sample_interval_seconds=round(stride / fps, 3),
                        message='약 0.5초 간격으로 검사한 프레임 중 처음 차량이 감지된 장면입니다. 사고 순간 판정이 아닙니다.')
        return dict(status='no_detection', progress=100, detections=[],
                    message='검사한 프레임에서 기준 점수 0.5 이상의 차량을 찾지 못했습니다. 차량이 없다는 뜻은 아닙니다.')
    finally:
        cap.release()
