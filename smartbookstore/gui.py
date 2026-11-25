import html
import sys
import traceback
import cv2
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)
from .models import BookstoreError

SYNC = False
_ACTIVE = []

STYLE = """
QWidget { font-size: 14px; color: #1d2433; }
QMainWindow, QStackedWidget > QWidget { background: #f4f6fa; }
QFrame#nav { background: #1f3a63; }
QFrame#nav QLabel { color: white; }
QFrame#nav QPushButton { background: transparent; color: #dbe6f7; border: none; padding: 8px 14px; font-weight: 600; }
QFrame#nav QPushButton:hover { background: #2c4d80; }
QFrame#nav QPushButton:checked { background: #3a6ab0; color: white; }
QFrame#card { background: white; border: 1px solid #d5dbe6; border-radius: 10px; }
QPushButton { background: #2f5fa7; color: white; border: none; border-radius: 6px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: #3a70c2; }
QPushButton:disabled { background: #a9b4c6; }
QPushButton[flat="true"] { background: #e6ebf3; color: #1d2433; }
QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QTableWidget, QTextBrowser, QListWidget {
    background: white; border: 1px solid #c9d1de; border-radius: 6px; padding: 4px; }
QHeaderView::section { background: #e6ebf3; border: none; padding: 6px; font-weight: 700; }
QLabel#h1 { font-size: 22px; font-weight: 800; }
QLabel#h2 { font-size: 16px; font-weight: 700; }
QLabel#muted { color: #5b667a; }
QLabel#bad { color: #b3261e; font-weight: 600; }
QLabel#good { color: #1b7a3a; font-weight: 600; }
QLabel#banner { background: #fff4d6; border: 1px solid #e3c36a; border-radius: 6px; padding: 8px; }
"""


class Worker(QThread):
    ok = Signal(object)
    bad = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.ok.emit(self.fn())
        except BookstoreError as e:
            self.bad.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.bad.emit(f"Unexpected error: {e}")


def runAsync(owner, fn, onOk, onBad=None):
    def fail(msg):
        if onBad:
            onBad(msg)
        else:
            QMessageBox.warning(owner, "Smart Bookstore", msg)

    if SYNC:
        try:
            result = fn()
        except BookstoreError as e:
            fail(str(e))
            return
        onOk(result)
        return
    w = Worker(fn)
    _ACTIVE.append(w)
    QApplication.setOverrideCursor(Qt.WaitCursor)

    def done(r):
        QApplication.restoreOverrideCursor()
        onOk(r)

    def bad(m):
        QApplication.restoreOverrideCursor()
        fail(m)

    w.ok.connect(done)
    w.bad.connect(bad)
    w.finished.connect(lambda: _ACTIVE.remove(w) if w in _ACTIVE else None)
    w.start()


def guard(owner, fn):
    try:
        return fn()
    except BookstoreError as e:
        QMessageBox.warning(owner, "Smart Bookstore", str(e))
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(owner, "Smart Bookstore", f"Unexpected error: {e}")
    return None


def money(x):
    return f"${float(x):.2f}"


def stars(n):
    n = int(round(n))
    return "★" * n + "☆" * (5 - n)


def bgrPixmap(img, w, h):
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    hh, ww = rgb.shape[:2]
    qimg = QImage(rgb.data, ww, hh, ww * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def coverPixmap(controller, book, w, h):
    p = controller.catalog.coverFile(book)
    pix = QPixmap(str(p)) if p.exists() else QPixmap()
    if pix.isNull():
        pix = QPixmap(w, h)
        pix.fill(Qt.lightGray)
    return pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def label(text="", name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def makeTable(headers, stretch=0):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.Stretch)
    return t


def fillTable(t, rows, ids=None):
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            item = QTableWidgetItem(str(v))
            if j == 0 and ids is not None:
                item.setData(Qt.UserRole, ids[i])
            t.setItem(i, j, item)


def selectedId(t):
    r = t.currentRow()
    if r < 0:
        return None
    return t.item(r, 0).data(Qt.UserRole)


def secondary(btn):
    btn.setProperty("flat", True)
    return btn


class CameraWidget(QLabel):
    def __init__(self, detector=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(360, 270)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#20242e;color:#cfd6e4;border-radius:8px;")
        self.setText("Camera off")
        self.cap = None
        self.frame = None
        self.detector = detector
        self.boxes = []
        self.n = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self):
        if self.cap is not None:
            return True
        try:
            cap = cv2.VideoCapture(0)
            opened = cap.isOpened()
        except Exception:
            opened = False
        if not opened:
            self.setText("No camera found.\nUse 'image file' instead.")
            return False
        self.cap = cap
        self.timer.start(66)
        return True

    def stop(self):
        self.timer.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.frame = None
        self.setText("Camera off")

    def tick(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            return
        self.frame = frame
        self.n += 1
        if self.detector is not None and self.n % 4 == 0:
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (0, 0), fx=0.5, fy=0.5)
            self.boxes = [(x * 2, y * 2, w * 2, h * 2)
                          for x, y, w, h in self.detector.detectMultiScale(small, 1.1, 5, minSize=(40, 40))]
        view = frame.copy()
        for x, y, w, h in self.boxes:
            cv2.rectangle(view, (x, y), (x + w, y + h), (80, 220, 80), 2)
        self.setPixmap(bgrPixmap(view, self.width(), self.height()))


def readImageFile(path):
    img = cv2.imread(path)
    if img is None:
        raise BookstoreError(f"Could not read image: {path}")
    return img


def readAudioFile(path):
    from .voice import loadWav
    try:
        return loadWav(path)
    except Exception:
        raise BookstoreError("Could not read that audio file. Use a .wav file.")


def recordVoice(seconds=3.0):
    try:
        from .voice import recordClip
        return recordClip(seconds)
    except Exception:
        raise BookstoreError("No microphone available. Use an audio file instead.")


class EnrollDialog(QDialog):
    def __init__(self, win, userType="RC"):
        super().__init__(win)
        self.win = win
        self.c = win.c
        self.userType = userType
        self.faces = []
        self.clips = []
        self.ticks = 0
        self.setWindowTitle("Create super user" if userType == "SU" else "Register")
        self.setMinimumWidth(760)
        root = QVBoxLayout(self)
        root.addWidget(label("Create the super user (store owner)" if userType == "SU" else "Create your account",
                             "h1"))
        root.addWidget(label("Log in later with your face and/or voice. Provide at least one.", "muted"))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("3-20 letters, digits, dot, dash, underscore")
        form.addRow("Username", self.name)
        root.addLayout(form)
        cols = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(label("Face", "h2"))
        self.cam = CameraWidget(self.c.face.detector)
        left.addWidget(self.cam)
        row = QHBoxLayout()
        self.btnCapture = QPushButton("Capture face (hold still)")
        self.btnCapture.clicked.connect(self.captureFace)
        btnFiles = secondary(QPushButton("Add image files..."))
        btnFiles.clicked.connect(self.addFaceFiles)
        row.addWidget(self.btnCapture)
        row.addWidget(btnFiles)
        left.addLayout(row)
        self.faceLabel = label("0 face images (need 10+ with a clear face)", "muted")
        left.addWidget(self.faceLabel)
        cols.addLayout(left)
        right = QVBoxLayout()
        right.addWidget(label("Voice (optional if you give a face)", "h2"))
        right.addWidget(label("Record 3 short clips. Say a sentence naturally each time.", "muted", True))
        self.btnRecord = QPushButton("Record voice (3 clips x 3 s)")
        self.btnRecord.clicked.connect(self.recordClips)
        btnAudio = secondary(QPushButton("Add audio files (.wav)..."))
        btnAudio.clicked.connect(self.addAudioFiles)
        right.addWidget(self.btnRecord)
        right.addWidget(btnAudio)
        self.voiceLabel = label("0 voice clips", "muted")
        right.addWidget(self.voiceLabel)
        right.addStretch()
        cols.addLayout(right)
        root.addLayout(cols)
        self.status = label("", "muted", True)
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btnCancel = secondary(QPushButton("Cancel"))
        self.btnCancel.clicked.connect(self.reject)
        self.btnRegister = QPushButton("Create account")
        self.btnRegister.clicked.connect(self.submit)
        bottom.addWidget(self.btnCancel)
        bottom.addWidget(self.btnRegister)
        root.addLayout(bottom)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.grabFrame)
        self.cam.start()

    def done(self, r):
        self.timer.stop()
        self.cam.stop()
        super().done(r)

    def updateLabels(self):
        self.faceLabel.setText(f"{len(self.faces)} face images (need 10+ with a clear face)")
        self.voiceLabel.setText(f"{len(self.clips)} voice clips")

    def captureFace(self):
        if not self.cam.start():
            self.status.setText("No camera. Add image files instead.")
            return
        self.ticks = 0
        self.faces = []
        self.btnCapture.setEnabled(False)
        self.status.setText("Capturing... look at the camera and move your head slightly.")
        self.timer.start(150)

    def grabFrame(self):
        self.ticks += 1
        f = self.cam.frame
        if f is not None and self.c.face.detectFace(f) is not None:
            self.faces.append(f.copy())
        self.updateLabels()
        if len(self.faces) >= 14 or self.ticks >= 80:
            self.timer.stop()
            self.btnCapture.setEnabled(True)
            self.status.setText("Capture finished." if len(self.faces) >= 10 else
                                "Not enough clear faces. Improve the light and try again.")

    def addFaceFiles(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose face images", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        for p in paths:
            img = cv2.imread(p)
            if img is not None:
                self.faces.append(img)
        self.updateLabels()

    def recordClips(self):
        self.btnRecord.setEnabled(False)
        self.status.setText("Recording 3 clips. Speak now...")

        def work():
            import time
            out = []
            for _ in range(3):
                out.append(recordVoice(3.0))
                time.sleep(0.3)
            return out

        def ok(clips):
            self.clips = clips
            self.btnRecord.setEnabled(True)
            self.status.setText("Voice recorded.")
            self.updateLabels()

        def bad(msg):
            self.btnRecord.setEnabled(True)
            self.status.setText(msg)

        runAsync(self, work, ok, bad)

    def addAudioFiles(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose voice clips", "", "Audio (*.wav)")
        for p in paths:
            guard(self, lambda p=p: self.clips.append(readAudioFile(p)))
        self.updateLabels()

    def submit(self):
        self.btnRegister.setEnabled(False)
        self.status.setText("Creating your profile (training the recognizer)...")
        name, faces, clips = self.name.text(), list(self.faces), list(self.clips)

        def ok(user):
            self.btnRegister.setEnabled(True)
            QMessageBox.information(self, "Smart Bookstore", f"Account '{user.username}' created. You can log in now.")
            self.accept()

        def bad(msg):
            self.btnRegister.setEnabled(True)
            self.status.setText("")
            QMessageBox.warning(self, "Smart Bookstore", msg)

        runAsync(self, lambda: self.c.register(name, faces or None, clips or None, self.userType), ok, bad)


class LoginPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        root = QHBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        left = QVBoxLayout()
        left.addWidget(label("Sign in", "h1"))
        left.addWidget(label("Registered customers and the super user sign in with a face or voice sample.", "muted", True))
        self.cam = CameraWidget(self.c.face.detector)
        left.addWidget(self.cam)
        self.status = label("", "muted", True)
        left.addWidget(self.status)
        left.addStretch()
        root.addLayout(left)
        right = QVBoxLayout()
        self.banner = label("First run: there is no super user yet. Create one to start managing the store.", "banner", True)
        self.btnSetup = QPushButton("Create super user")
        self.btnSetup.clicked.connect(self.setup)
        right.addWidget(self.banner)
        right.addWidget(self.btnSetup)
        right.addSpacing(10)
        right.addWidget(label("Face", "h2"))
        b1 = QPushButton("Sign in with camera")
        b1.clicked.connect(self.faceCamera)
        b2 = secondary(QPushButton("Sign in with an image file..."))
        b2.clicked.connect(self.faceFile)
        right.addWidget(b1)
        right.addWidget(b2)
        right.addSpacing(10)
        right.addWidget(label("Voice", "h2"))
        b3 = QPushButton("Sign in with voice (record 3 s)")
        b3.clicked.connect(self.voiceMic)
        b4 = secondary(QPushButton("Sign in with an audio file (.wav)..."))
        b4.clicked.connect(self.voiceFile)
        right.addWidget(b3)
        right.addWidget(b4)
        right.addSpacing(10)
        b5 = secondary(QPushButton("Register a new account"))
        b5.clicked.connect(self.register)
        b6 = secondary(QPushButton("Continue as visitor"))
        b6.clicked.connect(lambda: self.win.go("home"))
        right.addWidget(b5)
        right.addWidget(b6)
        right.addStretch()
        root.addLayout(right)

    def refresh(self):
        setup = self.c.needsSetup()
        self.banner.setVisible(setup)
        self.btnSetup.setVisible(setup)
        self.status.setText("")
        self.cam.start()

    def leave(self):
        self.cam.stop()

    def finish(self, user):
        self.win.afterLogin(user)

    def attempt(self, kind, getSample):
        def work():
            return self.c.login(kind, getSample())

        def bad(msg):
            self.status.setText(msg)
            self.status.setObjectName("bad")
            self.status.setStyleSheet("")
            QMessageBox.warning(self, "Smart Bookstore", msg)

        runAsync(self, work, self.finish, bad)

    def faceCamera(self):
        if not self.cam.start() or self.cam.frame is None:
            QMessageBox.information(self, "Smart Bookstore", "Camera not ready. Use an image file instead.")
            return
        frame = self.cam.frame.copy()
        self.attempt("face", lambda: frame)

    def faceFile(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a face image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self.attempt("face", lambda: readImageFile(p))

    def voiceMic(self):
        self.status.setText("Recording... speak now.")
        self.attempt("voice", lambda: recordVoice(3.0))

    def voiceFile(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a voice clip", "", "Audio (*.wav)")
        if p:
            self.attempt("voice", lambda: readAudioFile(p))

    def register(self):
        self.cam.stop()
        EnrollDialog(self.win, "RC").exec()
        self.refresh()

    def setup(self):
        self.cam.stop()
        EnrollDialog(self.win, "SU").exec()
        self.refresh()


class BookCard(QFrame):
    def __init__(self, win, book):
        super().__init__()
        self.setObjectName("card")
        self.win = win
        self.book = book
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        cover = QLabel()
        cover.setAlignment(Qt.AlignCenter)
        cover.setPixmap(coverPixmap(win.c, book, 160, 220))
        lay.addWidget(cover)
        t = label(book.title, "h2", True)
        lay.addWidget(t)
        lay.addWidget(label(book.author, "muted", True))
        rating = f"  {stars(book.avgRating)} ({book.ratingCount})" if book.ratingCount else ""
        lay.addWidget(label(f"{book.category} · {money(book.price)}{rating}"))
        btn = QPushButton("Open")
        btn.clicked.connect(lambda: win.openBook(book.bookId))
        lay.addWidget(btn)


class HomePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        left = QVBoxLayout()
        self.heading = label("", "h1")
        self.sub = label("", "muted", True)
        left.addWidget(self.heading)
        left.addWidget(self.sub)
        self.cards = QHBoxLayout()
        left.addLayout(self.cards)
        self.info = label("", "muted", True)
        left.addWidget(self.info)
        left.addStretch()
        root.addLayout(left, 3)
        chat = QFrame()
        chat.setObjectName("card")
        cl = QVBoxLayout(chat)
        cl.addWidget(label("Chat with the store", "h2"))
        self.log = QTextBrowser()
        cl.addWidget(self.log, 1)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about the store, books, or tell me your mood...")
        self.input.returnPressed.connect(self.send)
        self.btn = QPushButton("Send")
        self.btn.clicked.connect(self.send)
        row.addWidget(self.input, 1)
        row.addWidget(self.btn)
        cl.addLayout(row)
        chat.setMinimumWidth(380)
        root.addWidget(chat, 2)

    def refresh(self):
        while self.cards.count():
            w = self.cards.takeAt(0).widget()
            if w:
                w.deleteLater()
        user = self.c.refreshUser()
        if user.type in ("RC", "VC"):
            self.heading.setText(f"Recommended for you, {user.username}")
            self.sub.setText("Top 3 picks based on what you browsed and bought.")
            self.info.setText(f"Balance {money(user.balance())} · Purchases {user.purchaseCount} · Status {user.status}")
        else:
            self.heading.setText("Most popular right now")
            self.sub.setText("Top 3 books by purchases and views.")
            self.info.setText("Sign in to get personal recommendations." if user.type == "VS" else "Signed in as super user.")
        for b in self.c.topThree():
            self.cards.addWidget(BookCard(self.win, b))
        self.cards.addStretch()

    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.log.append(f"<p><b>You:</b> {html.escape(text)}</p>")
        self.btn.setEnabled(False)

        def ok(reply):
            self.btn.setEnabled(True)
            body = html.escape(reply.text).replace("\n", "<br>")
            self.log.append(f"<p><b>Store:</b> {body}</p>")

        def bad(msg):
            self.btn.setEnabled(True)
            self.log.append(f"<p><b>Store:</b> {html.escape(msg)}</p>")

        runAsync(self, lambda: self.c.chat(text), ok, bad)


class BrowsePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(label("Browse and search", "h1"))
        f = QHBoxLayout()
        self.category = QComboBox()
        self.author = QComboBox()
        self.yearFrom = QLineEdit()
        self.yearFrom.setPlaceholderText("From year")
        self.yearTo = QLineEdit()
        self.yearTo.setPlaceholderText("To year")
        self.sort = QComboBox()
        for name, key in [("Title", "title"), ("Year", "year"), ("Rating", "rating"), ("Price", "price"),
                          ("Author", "author")]:
            self.sort.addItem(name, key)
        for w in (self.category, self.author, self.yearFrom, self.yearTo, self.sort):
            f.addWidget(w)
        go = QPushButton("Filter")
        go.clicked.connect(self.filter)
        f.addWidget(go)
        root.addLayout(f)
        s = QHBoxLayout()
        self.keywords = QLineEdit()
        self.keywords.setPlaceholderText("Search by keywords (title, author, topic)...")
        self.keywords.returnPressed.connect(self.search)
        b = QPushButton("Search")
        b.clicked.connect(self.search)
        pic = secondary(QPushButton("Search by picture..."))
        pic.clicked.connect(self.searchPicture)
        reset = secondary(QPushButton("Reset"))
        reset.clicked.connect(self.reset)
        s.addWidget(self.keywords, 1)
        s.addWidget(b)
        s.addWidget(pic)
        s.addWidget(reset)
        root.addLayout(s)
        self.table = makeTable(["Title", "Author", "Category", "Year", "Price", "Rating", "Match"], 0)
        self.table.cellDoubleClicked.connect(lambda *_: self.openSelected())
        root.addWidget(self.table, 1)
        self.note = label("Double-click a book to open it.", "muted")
        root.addWidget(self.note)

    def refresh(self):
        cats, auths = self.c.catalog.categories(), self.c.catalog.authors()
        cc, ca = self.category.currentText(), self.author.currentText()
        self.category.clear()
        self.category.addItem("All categories", "")
        for x in cats:
            self.category.addItem(x, x)
        self.author.clear()
        self.author.addItem("All authors", "")
        for x in auths:
            self.author.addItem(x, x)
        i = self.category.findText(cc)
        self.category.setCurrentIndex(max(i, 0))
        j = self.author.findText(ca)
        self.author.setCurrentIndex(max(j, 0))
        self.filter()

    def show(self, books, matches=None):
        rows, ids = [], []
        for b in books:
            rating = f"{b.avgRating:.1f} ({b.ratingCount})" if b.ratingCount else "-"
            m = f"{matches[b.bookId] * 100:.0f}%" if matches else ""
            rows.append([b.title, b.author, b.category, b.year, money(b.price), rating, m])
            ids.append(b.bookId)
        fillTable(self.table, rows, ids)
        self.table.setColumnHidden(6, not matches)
        self.note.setText(f"{len(books)} book(s). Double-click a book to open it." if books else "No books found.")

    def filter(self):
        def years(w):
            t = w.text().strip()
            if not t:
                return None
            try:
                return int(t)
            except ValueError:
                raise BookstoreError("Years must be whole numbers.")

        guard(self, lambda: self.show(self.c.browse(self.category.currentData() or "", self.author.currentData() or "",
                                                    years(self.yearFrom), years(self.yearTo), self.sort.currentData())))

    def search(self):
        text = self.keywords.text().strip()
        if not text:
            self.filter()
            return
        guard(self, lambda: self.show(self.c.search(text)))

    def searchPicture(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a cover or figure picture", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not p:
            return

        def go():
            hits = self.c.searchImage(readImageFile(p))
            self.show([b for b, _ in hits], {b.bookId: s for b, s in hits})
            if not hits:
                self.note.setText("No similar cover found.")

        guard(self, go)

    def reset(self):
        self.keywords.clear()
        self.yearFrom.clear()
        self.yearTo.clear()
        self.category.setCurrentIndex(0)
        self.author.setCurrentIndex(0)
        self.filter()

    def openSelected(self):
        bid = selectedId(self.table)
        if bid is not None:
            self.win.openBook(bid)


class BookPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        self.bookId = None
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        left = QVBoxLayout()
        self.cover = QLabel()
        self.cover.setAlignment(Qt.AlignTop)
        left.addWidget(self.cover)
        self.addBtn = QPushButton("Add to cart")
        self.addBtn.clicked.connect(self.addToCart)
        left.addWidget(self.addBtn)
        back = secondary(QPushButton("Back to browse"))
        back.clicked.connect(lambda: self.win.go("browse"))
        left.addWidget(back)
        left.addStretch()
        root.addLayout(left)
        right = QVBoxLayout()
        self.title = label("", "h1", True)
        self.meta = label("", "muted", True)
        self.rating = label("")
        self.status = label("", "banner", True)
        self.desc = label("", wrap=True)
        for w in (self.title, self.meta, self.rating, self.status, self.desc):
            right.addWidget(w)
        right.addWidget(label("Comments", "h2"))
        self.comments = QTextBrowser()
        right.addWidget(self.comments, 1)
        form = QHBoxLayout()
        self.stars = QComboBox()
        for i in range(5, 0, -1):
            self.stars.addItem(f"{stars(i)}  {i}", i)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Write a comment...")
        self.text.returnPressed.connect(self.post)
        post = QPushButton("Post")
        post.clicked.connect(self.post)
        form.addWidget(self.stars)
        form.addWidget(self.text, 1)
        form.addWidget(post)
        right.addLayout(form)
        root.addLayout(right, 1)

    def load(self, bookId):
        self.bookId = bookId
        book, comments = self.c.openBook(bookId)
        self.cover.setPixmap(coverPixmap(self.c, book, 220, 330))
        self.title.setText(book.title)
        self.meta.setText(f"{book.author} · {book.category} · {book.year} · {money(book.price)}")
        self.rating.setText(f"{stars(book.avgRating)}  {book.avgRating:.1f} from {book.ratingCount} rating(s)"
                            if book.ratingCount else "No ratings yet")
        self.desc.setText(book.description)
        user = self.c.user
        flag = {"NO_ORDER": "On the no-order list (average rating below 2).",
                "TO_ORDER": "On the to-order list (average rating above 4)."}.get(book.listStatus, "")
        self.status.setText(flag)
        self.status.setVisible(bool(flag) and user.type == "SU")
        self.addBtn.setVisible(user.canAccess("cart"))
        self.renderComments(comments)
        return book

    def refresh(self):
        if self.bookId is not None:
            guard(self, lambda: self.load(self.bookId))

    def renderComments(self, comments):
        if not comments:
            self.comments.setHtml("<p style='color:#5b667a'>No comments yet. Be the first.</p>")
            return
        parts = []
        for c in comments:
            badge = " <i>(verified buyer)</i>" if c.weight > 1 else ""
            parts.append(f"<p><b>{html.escape(c.username or 'Visitor')}</b>{badge} · {stars(c.stars)} · "
                         f"<span style='color:#5b667a'>{c.postedAt[:10]}</span><br>{html.escape(c.shownText)}</p>")
        self.comments.setHtml("".join(parts))

    def addToCart(self):
        def go():
            self.c.addToCart(self.bookId)
            self.win.updateNav()
            QMessageBox.information(self, "Smart Bookstore", "Added to your cart.")

        guard(self, go)

    def post(self):
        text = self.text.text()

        def go():
            res = self.c.postComment(self.bookId, self.stars.currentData(), text)
            self.text.clear()
            if res.status == "BLOCKED":
                msg = "Your comment was blocked because it has more than 3 taboo words."
                if res.penalty == "SUSPENDED":
                    msg += "\nYou now have more than 2 warnings and your account is suspended."
                elif res.penalty == "DEMOTED":
                    msg += "\nYou received a warning and were demoted to a regular customer (no VIP discount)."
                elif res.penalty == "WARNED":
                    msg += "\nYou received 1 warning."
                QMessageBox.warning(self, "Comment blocked", msg)
            self.win.updateNav()
            if self.c.user.userId == 0 and res.penalty == "SUSPENDED":
                self.win.go("login")
                return
            self.load(self.bookId)

        guard(self, go)


class CartPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(label("Your cart", "h1"))
        self.table = makeTable(["Title", "Qty", "Price"], 0)
        root.addWidget(self.table, 1)
        row = QHBoxLayout()
        rm = secondary(QPushButton("Remove selected"))
        rm.clicked.connect(self.remove)
        row.addWidget(rm)
        row.addStretch()
        box = QVBoxLayout()
        self.sub = label("")
        self.disc = label("")
        self.total = label("", "h2")
        self.bal = label("")
        for w in (self.sub, self.disc, self.total, self.bal):
            box.addWidget(w)
        row.addLayout(box)
        root.addLayout(row)
        self.checkoutBtn = QPushButton("Checkout")
        self.checkoutBtn.clicked.connect(self.checkout)
        root.addWidget(self.checkoutBtn)

    def refresh(self):
        user = self.c.refreshUser()
        cart = self.c.session.cart
        rows = [[b.title, q, money(b.price * q)] for b, q in cart.items.values()]
        fillTable(self.table, rows, list(cart.items.keys()))
        sub, disc, total = self.c.cartPricing()
        self.sub.setText(f"Subtotal: {money(sub)}")
        self.disc.setText(f"VIP discount: -{money(disc)}" if user.type == "VC" else "VIP discount: none")
        self.total.setText(f"Total: {money(total)}")
        short = total > user.balance() and total > 0
        self.bal.setText(f"Account balance: {money(user.balance())}" +
                         ("  (not enough: a $1 fine will apply)" if short else ""))
        self.bal.setObjectName("bad" if short else "")
        self.bal.setStyleSheet("color:#b3261e;font-weight:600;" if short else "")
        self.checkoutBtn.setEnabled(bool(cart.items))

    def remove(self):
        bid = selectedId(self.table)
        if bid is not None:
            self.c.removeFromCart(bid)
            self.win.updateNav()
            self.refresh()

    def checkout(self):
        def go():
            res = self.c.checkout()
            self.win.updateNav()
            if res.status == "PAID":
                msg = f"Order placed. You paid {money(res.total)}. New balance: {money(res.balance)}."
                if res.promotedTo == "VC":
                    msg += "\nYou are now a VIP customer: 10% off every purchase."
                QMessageBox.information(self, "Smart Bookstore", msg)
                self.refresh()
            else:
                msg = f"Not enough money. The order was cancelled and a $1 fine was charged. Balance: {money(res.balance)}."
                if res.suspended:
                    msg += "\nYour balance is negative, so your account is suspended. Ask the super user to reopen it."
                QMessageBox.warning(self, "Smart Bookstore", msg)
                if res.suspended:
                    self.win.go("login")
                else:
                    self.refresh()

        guard(self, go)


class AccountPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(label("My account", "h1"))
        self.info = label("", wrap=True)
        root.addWidget(self.info)
        row = QHBoxLayout()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(1, 1000)
        self.amount.setValue(10)
        self.amount.setPrefix("$ ")
        self.add = QPushButton("Add funds")
        self.add.clicked.connect(self.topUp)
        row.addWidget(self.amount)
        row.addWidget(self.add)
        row.addStretch()
        root.addLayout(row)
        root.addWidget(label("Order history", "h2"))
        self.table = makeTable(["Order", "Date", "Total", "Result", "Items"], 4)
        root.addWidget(self.table, 1)

    def refresh(self):
        u = self.c.refreshUser()
        has = bool(u.account)
        self.add.setVisible(has)
        self.amount.setVisible(has)
        self.table.setVisible(has)
        if not has:
            self.info.setText(f"Signed in as {u.username} ({u.type}). Super users have no shopping account.")
            return
        self.info.setText(
            f"<b>{html.escape(u.username)}</b> · {'VIP customer (10% off)' if u.type == 'VC' else 'Registered customer'}"
            f"<br>Balance: {money(u.balance())} · Status: {u.status}<br>"
            f"Purchases: {u.purchaseCount} · Total spent: {money(u.totalSpent)} · Warnings: {u.warningCount}")
        rows = [[o["orderId"], o["date"], money(o["total"]), "Paid" if o["result"] == "PAID" else "Cancelled (fined)",
                 o["items"]] for o in self.c.orderHistory()]
        fillTable(self.table, rows)

    def topUp(self):
        def go():
            self.c.topUp(self.amount.value())
            self.win.updateNav()
            self.refresh()

        guard(self, go)


class AdminPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.c = win.c
        self.coverPath = ""
        self.textPath = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.addWidget(label("Super user panel", "h1"))
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        add = QWidget()
        form = QFormLayout(add)
        self.fTitle, self.fAuthor, self.fYear, self.fPrice = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.fCategory = QComboBox()
        self.fCategory.setEditable(True)
        self.fDesc = QTextEdit()
        self.fDesc.setFixedHeight(80)
        self.fCover = QPushButton("Choose cover image (optional)...")
        self.fCover.clicked.connect(self.pickCover)
        self.fText = QPushButton("Choose book text file (optional)...")
        self.fText.clicked.connect(self.pickText)
        save = QPushButton("Add book")
        save.clicked.connect(self.addBook)
        for name, w in [("Title", self.fTitle), ("Author", self.fAuthor), ("Category", self.fCategory),
                        ("Year", self.fYear), ("Price ($)", self.fPrice), ("Description", self.fDesc),
                        ("Cover", self.fCover), ("Text", self.fText)]:
            form.addRow(name, w)
        form.addRow("", save)
        tabs.addTab(add, "Add book")

        taboo = QWidget()
        tl = QVBoxLayout(taboo)
        self.tabooList = QListWidget()
        tl.addWidget(self.tabooList, 1)
        row = QHBoxLayout()
        self.tabooInput = QLineEdit()
        self.tabooInput.setPlaceholderText("New taboo word")
        self.tabooInput.returnPressed.connect(self.addTaboo)
        a = QPushButton("Add")
        a.clicked.connect(self.addTaboo)
        r = secondary(QPushButton("Remove selected"))
        r.clicked.connect(self.removeTaboo)
        row.addWidget(self.tabooInput, 1)
        row.addWidget(a)
        row.addWidget(r)
        tl.addLayout(row)
        tabs.addTab(taboo, "Taboo words")

        acc = QWidget()
        al = QVBoxLayout(acc)
        self.users = makeTable(["Username", "Type", "Status", "Balance", "Purchases", "Spent", "Warnings"], 0)
        al.addWidget(self.users, 1)
        row = QHBoxLayout()
        self.deposit = QDoubleSpinBox()
        self.deposit.setRange(0.01, 10000)
        self.deposit.setValue(10)
        self.deposit.setPrefix("$ ")
        reopen = QPushButton("Deposit and reopen selected account")
        reopen.clicked.connect(self.reopen)
        row.addWidget(self.deposit)
        row.addWidget(reopen)
        row.addStretch()
        al.addLayout(row)
        tabs.addTab(acc, "Accounts")

        lists = QWidget()
        ll = QHBoxLayout(lists)
        self.noOrder, self.toOrder = QListWidget(), QListWidget()
        v1, v2 = QVBoxLayout(), QVBoxLayout()
        v1.addWidget(label("No-order list (3+ ratings, average below 2)", "h2"))
        v1.addWidget(self.noOrder)
        v2.addWidget(label("To-order list (3+ ratings, average above 4)", "h2"))
        v2.addWidget(self.toOrder)
        ll.addLayout(v1)
        ll.addLayout(v2)
        tabs.addTab(lists, "Book lists")

        fin = QWidget()
        fl = QVBoxLayout(fin)
        self.report = QTextBrowser()
        fl.addWidget(self.report)
        tabs.addTab(fin, "Finance")

    def refresh(self):
        guard(self, self._refresh)

    def _refresh(self):
        cur = self.fCategory.currentText()
        self.fCategory.clear()
        self.fCategory.addItems(self.c.catalog.categories())
        self.fCategory.setEditText(cur)
        self.tabooList.clear()
        self.tabooList.addItems(self.c.tabooWords())
        cust = self.c.customers()
        fillTable(self.users, [[u.username, u.type, u.status, money(u.balance()), u.purchaseCount,
                                money(u.totalSpent), u.warningCount] for u in cust], [u.userId for u in cust])
        no, to = self.c.bookLists()
        self.noOrder.clear()
        self.noOrder.addItems([f"{b.title} ({b.avgRating:.1f}, {b.ratingCount} ratings)" for b in no])
        self.toOrder.clear()
        self.toOrder.addItems([f"{b.title} ({b.avgRating:.1f}, {b.ratingCount} ratings)" for b in to])
        self.report.setPlainText(self.c.financeReport())

    def pickCover(self):
        p, _ = QFileDialog.getOpenFileName(self, "Cover image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self.coverPath = p
            self.fCover.setText(p.split("/")[-1])

    def pickText(self):
        p, _ = QFileDialog.getOpenFileName(self, "Book text", "", "Text (*.txt)")
        if p:
            self.textPath = p
            self.fText.setText(p.split("/")[-1])

    def addBook(self):
        def go():
            self.c.addBook(title=self.fTitle.text(), author=self.fAuthor.text(), category=self.fCategory.currentText(),
                           year=self.fYear.text(), price=self.fPrice.text(), cover=self.coverPath or None,
                           text=self.textPath or None, description=self.fDesc.toPlainText())
            for w in (self.fTitle, self.fAuthor, self.fYear, self.fPrice):
                w.clear()
            self.fDesc.clear()
            self.coverPath = self.textPath = ""
            self.fCover.setText("Choose cover image (optional)...")
            self.fText.setText("Choose book text file (optional)...")
            QMessageBox.information(self, "Smart Bookstore", "Book added.")
            self._refresh()

        guard(self, go)

    def addTaboo(self):
        def go():
            self.c.addTaboo(self.tabooInput.text())
            self.tabooInput.clear()
            self._refresh()

        guard(self, go)

    def removeTaboo(self):
        item = self.tabooList.currentItem()
        if item:
            guard(self, lambda: (self.c.removeTaboo(item.text()), self._refresh()))

    def reopen(self):
        uid = selectedId(self.users)
        if uid is None:
            QMessageBox.information(self, "Smart Bookstore", "Select a customer first.")
            return

        def go():
            self.c.reopen(uid, self.deposit.value())
            QMessageBox.information(self, "Smart Bookstore", "Account reopened.")
            self._refresh()

        guard(self, go)


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setWindowTitle("Smart Bookstore")
        self.resize(1180, 760)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        nav = QFrame()
        nav.setObjectName("nav")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(12, 4, 12, 4)
        title = label("Smart Bookstore")
        title.setStyleSheet("font-size:18px;font-weight:800;color:white;")
        nl.addWidget(title)
        self.buttons = {}
        for key, text in [("home", "Home"), ("browse", "Browse"), ("cart", "Cart"), ("account", "Account"),
                          ("admin", "Admin")]:
            b = QPushButton(text)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.buttons[key] = b
            nl.addWidget(b)
        nl.addStretch()
        self.who = label("")
        nl.addWidget(self.who)
        self.auth = QPushButton("Sign in")
        self.auth.clicked.connect(self.toggleAuth)
        nl.addWidget(self.auth)
        root.addWidget(nav)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages = {"login": LoginPage(self), "home": HomePage(self), "browse": BrowsePage(self),
                      "book": BookPage(self), "cart": CartPage(self), "account": AccountPage(self),
                      "admin": AdminPage(self)}
        for p in self.pages.values():
            self.stack.addWidget(p)
        self.needs = {"cart": "cart", "account": "account", "admin": "admin"}
        self.current = "home"
        self.go("login" if self.c.needsSetup() else "home")

    def updateNav(self):
        u = self.c.user
        for key, feature in self.needs.items():
            self.buttons[key].setVisible(u.canAccess(feature))
        n = sum(q for _, q in self.c.session.cart.items.values())
        self.buttons["cart"].setText(f"Cart ({n})" if n else "Cart")
        for key, b in self.buttons.items():
            b.setChecked(key == self.current)
        if u.userId == 0:
            self.who.setText("Visitor")
            self.auth.setText("Sign in")
        else:
            extra = f" · {money(u.balance())}" if u.account else ""
            self.who.setText(f"{u.username} ({u.type}){extra}")
            self.auth.setText("Sign out")

    def go(self, name):
        feature = self.needs.get(name)
        if feature and not self.c.user.canAccess(feature):
            name = "login" if self.c.user.userId == 0 else "home"
        if self.current == "login" and name != "login":
            self.pages["login"].leave()
        self.current = name
        self.stack.setCurrentWidget(self.pages[name])
        self.updateNav()
        self.pages[name].refresh()
        self.updateNav()

    def openBook(self, bookId):
        page = self.pages["book"]
        if guard(self, lambda: page.load(bookId)) is None:
            return
        self.current = "book"
        self.stack.setCurrentWidget(page)
        self.pages["login"].leave()
        self.updateNav()

    def afterLogin(self, user):
        self.pages["login"].leave()
        self.go("home")
        QMessageBox.information(self, "Smart Bookstore", f"Welcome, {user.username}!")

    def toggleAuth(self):
        if self.c.user.userId == 0:
            self.go("login")
        else:
            self.c.logout()
            self.go("home")

    def closeEvent(self, event):
        self.pages["login"].leave()
        super().closeEvent(event)


def main():
    from . import seed
    from .controller import SystemController
    seed.seedIfEmpty()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    controller = SystemController()
    win = MainWindow(controller)
    win.show()
    if controller.needsSetup():
        QMessageBox.information(win, "Smart Bookstore",
                                "Welcome! There is no super user yet.\nClick 'Create super user' to set up the store owner's face and/or voice login.")
    sys.exit(app.exec())
