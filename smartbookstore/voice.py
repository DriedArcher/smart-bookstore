import numpy as np
from scipy import signal
from scipy.fft import dct
from scipy.io import wavfile
from . import config


def loadWav(path):
    rate, data = wavfile.read(path)
    data = data.astype(np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = np.abs(data).max()
    if peak > 0:
        data = data / peak
    if rate != config.VOICE_RATE:
        g = np.gcd(rate, config.VOICE_RATE)
        data = signal.resample_poly(data, config.VOICE_RATE // g, rate // g).astype(np.float32)
    return data


def recordClip(seconds=3.0):
    import sounddevice as sd
    n = int(seconds * config.VOICE_RATE)
    clip = sd.rec(n, samplerate=config.VOICE_RATE, channels=1, dtype="float32")
    sd.wait()
    return clip[:, 0].copy()


def trimSilence(audio, frame=400):
    if len(audio) < frame * 2:
        return audio
    n = len(audio) // frame
    energy = np.array([np.sqrt(np.mean(audio[i * frame:(i + 1) * frame] ** 2)) for i in range(n)])
    keep = np.where(energy > energy.max() * 0.1)[0]
    if len(keep) == 0 or energy.max() < 1e-4:
        return audio[:0]
    return audio[keep[0] * frame:(keep[-1] + 1) * frame]


def melFilterbank(nMels, nFft, rate):
    def hz2mel(h):
        return 2595 * np.log10(1 + h / 700)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595) - 1)

    pts = mel2hz(np.linspace(hz2mel(0), hz2mel(rate / 2), nMels + 2))
    bins = np.floor((nFft + 1) * pts / rate).astype(int)
    fb = np.zeros((nMels, nFft // 2 + 1))
    for m in range(1, nMels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        for k in range(l, c):
            fb[m - 1, k] = (k - l) / max(c - l, 1)
        for k in range(c, r):
            fb[m - 1, k] = (r - k) / max(r - c, 1)
    return fb


def mfcc(audio, rate=None, nMfcc=20, nFft=512, hop=160, nMels=40):
    rate = rate or config.VOICE_RATE
    audio = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])
    if len(audio) < nFft:
        audio = np.pad(audio, (0, nFft - len(audio)))
    n = 1 + (len(audio) - nFft) // hop
    idx = np.arange(nFft)[None, :] + hop * np.arange(n)[:, None]
    frames = audio[idx] * np.hamming(nFft)
    power = (np.abs(np.fft.rfft(frames, nFft)) ** 2) / nFft
    mel = np.log(power @ melFilterbank(nMels, nFft, rate).T + 1e-10)
    return dct(mel, type=2, axis=1, norm="ortho")[:, :nMfcc]


def windowFeatures(audio, windowSec=1.0, hopSec=0.5):
    audio = trimSilence(np.asarray(audio, dtype=np.float32))
    w = int(windowSec * config.VOICE_RATE)
    h = int(hopSec * config.VOICE_RATE)
    if len(audio) < w // 2:
        return []
    feats = []
    starts = list(range(0, max(len(audio) - w, 0) + 1, h)) or [0]
    for s in starts:
        seg = audio[s:s + w]
        if len(seg) < w // 2:
            continue
        m = mfcc(seg)
        feats.append(np.concatenate([m.mean(axis=0), m.std(axis=0)]))
    return feats


class VoiceRecognizer:
    def __init__(self):
        self.vectors = np.zeros((0, 40))
        self.labels = np.zeros((0,), dtype=int)
        self.mean = None
        self.std = None
        self.loadModel()

    def modelPath(self):
        return config.DATA / "models" / "voice.npz"

    def loadModel(self):
        p = self.modelPath()
        if p.exists():
            z = np.load(p)
            self.vectors = z["vectors"]
            self.labels = z["labels"]
        else:
            self.vectors = np.zeros((0, 40))
            self.labels = np.zeros((0,), dtype=int)
        self._fit()

    def _fit(self):
        if len(self.vectors):
            self.mean = self.vectors.mean(axis=0)
            self.std = self.vectors.std(axis=0) + 1e-6
        else:
            self.mean = None
            self.std = None

    def _save(self):
        self.modelPath().parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.modelPath(), vectors=self.vectors, labels=self.labels)

    def train(self, clips, userId):
        feats = []
        for c in clips:
            feats.extend(windowFeatures(c))
        if len(feats) < config.VOICE_MIN_VECTORS:
            return False
        keep = self.labels != int(userId)
        self.vectors = np.vstack([self.vectors[keep], np.array(feats)])
        self.labels = np.concatenate([self.labels[keep], np.full(len(feats), int(userId))])
        self._fit()
        self._save()
        return True

    def deleteUser(self, userId):
        keep = self.labels != int(userId)
        self.vectors = self.vectors[keep]
        self.labels = self.labels[keep]
        self._fit()
        self._save()

    def _norm(self, v):
        v = (v - self.mean) / self.std
        return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)

    def classify(self, clip):
        if self.mean is None or len(self.vectors) == 0:
            return None
        feats = windowFeatures(clip)
        if not feats:
            return None
        q = self._norm(np.array(feats))
        ref = self._norm(self.vectors)
        sims = q @ ref.T
        users = sorted(set(self.labels.tolist()))
        scores = {}
        for u in users:
            s = sims[:, self.labels == u]
            k = min(3, s.shape[1])
            scores[u] = float(np.sort(s, axis=1)[:, -k:].mean(axis=1).mean())
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, score = ranked[0]
        if len(ranked) > 1 and score - ranked[1][1] < config.VOICE_MIN_MARGIN:
            return (best, 0.0)
        return (best, score)

    def minConfidence(self):
        return config.VOICE_MIN_SIMILARITY
