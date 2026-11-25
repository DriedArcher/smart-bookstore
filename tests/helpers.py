import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from smartbookstore import config, seed
from smartbookstore.controller import SystemController
from smartbookstore.llm import LLMClient


def _key(sample):
    if hasattr(sample, "shape"):
        return int(sample.flat[0])
    return sample


class FakeFace:
    def __init__(self):
        self.map = {}
        self.trainOk = True
        self.deleted = []
        self.detector = None

    def detectFace(self, sample):
        if sample is None:
            return None
        return sample

    def train(self, images, userId):
        if not self.trainOk:
            return False
        self.map[_key(images[0])] = userId
        return True

    def deleteUser(self, userId):
        self.deleted.append(userId)

    def classify(self, sample):
        k = _key(sample)
        if k in self.map:
            return (self.map[k], 0.95)
        return (0, 0.0)

    def minConfidence(self):
        return 0.3


class FakeVoice(FakeFace):
    pass


def newController(llm=None):
    d = tempfile.mkdtemp(prefix="bs_")
    config.set_data_dir(d)
    seed.seedIfEmpty()
    c = SystemController(face=FakeFace(), voice=FakeVoice(), llm=llm or LLMClient(url="http://127.0.0.1:9"))
    return c


def makeCustomer(c, name, balance=10.0, userType="RC"):
    u = c.users.createUser(name, userType, balance)
    c.face.map[name] = u.userId
    return u


def loginAs(c, name):
    return c.login("face", name)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n))
        prompt = body.get("prompt", "")
        if "Label the mood" in prompt:
            reply = "sad"
        elif "Answer the question using only this context" in prompt:
            reply = "CONTEXT-ANSWER"
        else:
            reply = "Paris."
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"response": reply}).encode())


def startFakeOllama():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
