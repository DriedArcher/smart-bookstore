import re
import shutil
from pathlib import Path
import cv2
import numpy as np
from . import config
from .covers import makeCover
from .filestore import FileStore
from .models import NORMAL, NO_ORDER, TO_ORDER, Book, BookstoreError
from .ratings import loadComments, weightedAverage
from .users import now

BOOKS = "books.txt"
BROWSE_LOG = "browse_log.txt"


class ImageSearcher:
    def __init__(self):
        self.cache = {}

    def extractFeatures(self, image):
        small = cv2.resize(image, (64, 64))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
        hist = hist / (hist.sum() + 1e-9)
        thumb = cv2.resize(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (16, 16)).astype(np.float32).flatten()
        thumb = thumb - thumb.mean()
        thumb = thumb / (np.linalg.norm(thumb) + 1e-9)
        hist = hist / (np.linalg.norm(hist) + 1e-9)
        return np.concatenate([hist, thumb]) / np.sqrt(2)

    def _coverVector(self, path):
        p = Path(path)
        if not p.is_absolute():
            p = config.DATA / p
        if not p.exists():
            return None
        key = (str(p), p.stat().st_mtime)
        if key not in self.cache:
            img = cv2.imread(str(p))
            self.cache[key] = None if img is None else self.extractFeatures(img)
        return self.cache[key]

    def indexCover(self, bookId, coverPath):
        return self._coverVector(coverPath)

    def findSimilar(self, picture, books):
        if isinstance(picture, (str, Path)):
            picture = cv2.imread(str(picture))
        if picture is None:
            raise BookstoreError("Could not read that image.")
        q = self.extractFeatures(picture)
        scored = []
        for b in books:
            v = self._coverVector(b.coverPath)
            if v is None:
                continue
            s = float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v) + 1e-9))
            if s >= config.IMAGE_SIM_CUTOFF:
                scored.append((b, s))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored


class BookCatalog:
    def __init__(self):
        self.images = ImageSearcher()

    def loadBooks(self):
        books = [Book.fromRow(r) for r in FileStore.readLines(BOOKS)]
        byBook = {}
        for c in loadComments():
            if not c.blocked:
                byBook.setdefault(c.bookId, []).append((c.stars, c.weight))
        for b in books:
            r = byBook.get(b.bookId, [])
            b.ratingCount = len(r)
            b.avgRating = round(weightedAverage(r), 2)
        return books

    def coverFile(self, book):
        p = Path(book.coverPath)
        return p if p.is_absolute() else config.DATA / p

    def getBook(self, bookId):
        for b in self.loadBooks():
            if b.bookId == int(bookId):
                return b
        return None

    def saveBook(self, book):
        FileStore.replaceLine(BOOKS, book.bookId, book.toRow())

    def categories(self):
        return sorted({b.category for b in self.loadBooks()})

    def authors(self):
        return sorted({b.author for b in self.loadBooks()})

    def addBook(self, title, author, category, year, price, cover=None, text=None, description="",
                allowDuplicate=False):
        title, author, category = str(title).strip(), str(author).strip(), str(category).strip()
        if not title or not author or not category:
            raise BookstoreError("Title, author and category are required.")
        try:
            year = int(year)
            price = round(float(price), 2)
        except (TypeError, ValueError):
            raise BookstoreError("Year and price must be numbers.")
        if price <= 0:
            raise BookstoreError("Price must be above 0.")
        if not allowDuplicate:
            for b in self.loadBooks():
                if b.title.lower() == title.lower() and b.author.lower() == author.lower():
                    raise BookstoreError("This book already exists.")
        bookId = FileStore.nextId(BOOKS)
        folder = config.DATA / "books"
        folder.mkdir(parents=True, exist_ok=True)
        coverDest = folder / f"{bookId}_cover.png"
        if cover and Path(cover).exists():
            img = cv2.imread(str(cover))
            if img is None:
                raise BookstoreError("The cover file is not a readable image.")
            cv2.imwrite(str(coverDest), img)
        else:
            makeCover(title, author, coverDest)
        textDest = ""
        if text and Path(text).exists():
            textDest = f"books/{bookId}_text.txt"
            shutil.copy(text, config.DATA / textDest)
        book = Book(bookId, title, author, category, year, price, f"books/{bookId}_cover.png",
                    textDest, NORMAL, 0, 0, description)
        FileStore.appendLine(BOOKS, book.toRow())
        return bookId

    def browse(self, category="", author="", yearFrom=None, yearTo=None, sortBy="title"):
        out = []
        for b in self.loadBooks():
            if category and b.category != category:
                continue
            if author and b.author != author:
                continue
            if yearFrom is not None and b.year < yearFrom:
                continue
            if yearTo is not None and b.year > yearTo:
                continue
            out.append(b)
        keys = {"title": lambda b: b.title.lower(), "year": lambda b: b.year,
                "rating": lambda b: (-b.avgRating, b.title.lower()), "price": lambda b: b.price,
                "author": lambda b: b.author.lower()}
        return sorted(out, key=keys.get(sortBy, keys["title"]))

    def searchKeyword(self, text):
        words = [w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if w]
        if not words:
            return []
        scored = []
        for b in self.loadBooks():
            hay = " ".join([b.title, b.author, b.category, b.description]).lower()
            if all(w in hay for w in words):
                titleHits = sum(1 for w in words if w in b.title.lower())
                scored.append((b, titleHits + b.avgRating / 10))
        scored.sort(key=lambda t: (-t[1], t[0].title.lower()))
        return [b for b, _ in scored]

    def searchImage(self, picture):
        books = self.loadBooks()
        return self.images.findSimilar(picture, books)

    def booksInCategories(self, categories):
        cats = set(categories)
        out = [b for b in self.loadBooks() if b.category in cats]
        return sorted(out, key=lambda b: (-b.avgRating, b.title.lower()))

    def topByActivity(self, n):
        books = self.loadBooks()
        books.sort(key=lambda b: (-(b.purchaseCount + b.viewCount), -b.avgRating, b.title.lower()))
        return books[:n]

    def setListStatus(self, bookId, status):
        b = self.getBook(bookId)
        if b is not None and b.listStatus != status:
            b.listStatus = status
            self.saveBook(b)

    def logView(self, userId, bookId):
        b = self.getBook(bookId)
        if b is None:
            return
        FileStore.appendLine(BROWSE_LOG, [FileStore.nextId(BROWSE_LOG), userId or "", bookId, now()])
        b.viewCount += 1
        self.saveBook(b)

    def incrementPurchase(self, bookId, quantity):
        b = self.getBook(bookId)
        b.purchaseCount += quantity
        self.saveBook(b)

    def lists(self):
        books = self.loadBooks()
        return ([b for b in books if b.listStatus == NO_ORDER],
                [b for b in books if b.listStatus == TO_ORDER])
