import shutil
import cv2
import numpy as np
from . import config


class FaceRecognizer:
    def __init__(self, backend=None):
        self.backend = backend or config.FACE_BACKEND
        self.detector = cv2.CascadeClassifier(str(config.ASSETS / "haarcascade_frontalface_default.xml"))
        self.model = None
        self.loadModel()

    def faceDir(self):
        return config.DATA / "faces"

    def modelPath(self):
        name = "face_yolo" if self.backend == "yolo" else "face_lbph.yml"
        return config.DATA / "models" / name

    def detectFace(self, image):
        if image is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        boxes = self.detector.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(boxes) == 0:
            return None
        x, y, w, h = max(boxes, key=lambda b: b[2] * b[3])
        crop = gray[y:y + h, x:x + w]
        crop = cv2.resize(crop, (config.FACE_SIZE, config.FACE_SIZE))
        return cv2.equalizeHist(crop)

    def train(self, images, userId):
        crops = []
        for img in images:
            c = self.detectFace(img)
            if c is not None:
                crops.append(c)
        if len(crops) < config.MIN_FACE_CROPS:
            return False
        d = self.faceDir() / str(userId)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for i, c in enumerate(crops):
            cv2.imwrite(str(d / f"{i:03d}.png"), c)
        self.retrainAll()
        return True

    def deleteUser(self, userId):
        d = self.faceDir() / str(userId)
        if d.exists():
            shutil.rmtree(d)
        self.retrainAll()

    def _dataset(self):
        images, labels = [], []
        if not self.faceDir().exists():
            return images, labels
        for d in sorted(self.faceDir().iterdir()):
            if not d.is_dir() or not d.name.isdigit():
                continue
            for f in sorted(d.glob("*.png")):
                img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    images.append(img)
                    labels.append(int(d.name))
        return images, labels

    def retrainAll(self):
        images, labels = self._dataset()
        if not images:
            self.model = None
            p = self.modelPath()
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
            return
        if self.backend == "yolo":
            self._trainYolo(images, labels)
        else:
            self._trainLbph(images, labels)

    def _trainLbph(self, images, labels):
        rec = cv2.face.LBPHFaceRecognizer_create(radius=2, neighbors=8, grid_x=8, grid_y=8)
        rec.train(images, np.array(labels, dtype=np.int32))
        self.modelPath().parent.mkdir(parents=True, exist_ok=True)
        rec.write(str(self.modelPath()))
        self.model = rec

    def _trainYolo(self, images, labels):
        from ultralytics import YOLO
        root = config.DATA / "models" / "face_ds"
        if root.exists():
            shutil.rmtree(root)
        rng = np.random.default_rng(0)
        for split in ("train", "val"):
            for img, lab in zip(images, labels):
                d = root / split / str(lab)
                d.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(d / f"{len(list(d.glob('*.png'))):03d}.png"), img)
            d = root / split / "unknown"
            d.mkdir(parents=True, exist_ok=True)
            for i in range(max(20, len(images) // 2)):
                noise = rng.integers(0, 255, (config.FACE_SIZE, config.FACE_SIZE), dtype=np.uint8)
                cv2.imwrite(str(d / f"{i:03d}.png"), noise)
        out = config.DATA / "models" / "face_yolo"
        out.mkdir(parents=True, exist_ok=True)
        model = YOLO("yolov8n-cls.pt")
        model.train(data=str(root), epochs=25, imgsz=64, batch=16, project=str(out), name="run",
                    exist_ok=True, verbose=False, plots=False, workers=0, device="cpu")
        best = out / "run" / "weights" / "best.pt"
        shutil.copy(best, out / "best.pt")
        self.model = YOLO(str(out / "best.pt"))

    def loadModel(self):
        p = self.modelPath()
        self.model = None
        try:
            if self.backend == "yolo":
                w = p / "best.pt"
                if w.exists():
                    from ultralytics import YOLO
                    self.model = YOLO(str(w))
            elif p.exists():
                rec = cv2.face.LBPHFaceRecognizer_create()
                rec.read(str(p))
                self.model = rec
        except Exception:
            self.model = None

    def classify(self, image):
        crop = self.detectFace(image)
        if crop is None or self.model is None:
            return None
        if self.backend == "yolo":
            res = self.model.predict(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR), imgsz=64, verbose=False)[0]
            name = res.names[int(res.probs.top1)]
            if not name.isdigit():
                return (0, 0.0)
            return (int(name), float(res.probs.top1conf))
        label, dist = self.model.predict(crop)
        return (int(label), max(0.0, 1.0 - dist / config.FACE_DIST_SCALE))

    def minConfidence(self):
        if self.backend == "yolo":
            return config.YOLO_MIN_CONFIDENCE
        return 1.0 - config.FACE_MAX_DISTANCE / config.FACE_DIST_SCALE
