"""Download the official YOLO26n detector into the ignored models directory."""
from pathlib import Path
from ultralytics import YOLO

root = Path(__file__).resolve().parents[1]
path = root / 'models' / 'yolo26n.pt'
path.parent.mkdir(exist_ok=True)
model = YOLO(str(path))
assert model.names[2] == 'car', 'Expected the official COCO model'
print(f'Model ready: {path}')
