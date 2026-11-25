import re
from . import config
from .filestore import FileStore
from .models import NORMAL, NO_ORDER, TO_ORDER, RC, VC, Comment, BookstoreError
from .ratings import loadComments, publishedRatings, weightedAverage
from .users import now

TABOO = "taboo.txt"
COMMENTS = "comments.txt"
WARNINGS = "warnings.txt"
WORD_RE = re.compile(r"[A-Za-z0-9']+")


class TabooList:
    def load(self):
        return {r[0].strip().lower() for r in FileStore.readLines(TABOO) if r and r[0].strip()}

    def words(self):
        return sorted(self.load())

    def add(self, word):
        w = str(word).strip().lower()
        if not w or not WORD_RE.fullmatch(w):
            raise BookstoreError("Enter a single word.")
        if w not in self.load():
            FileStore.appendLine(TABOO, [w])

    def remove(self, word):
        FileStore.writeLines(TABOO, [[w] for w in self.words() if w != str(word).strip().lower()])

    def contains(self, word):
        return str(word).lower() in self.load()

    def filterText(self, text):
        taboo = self.load()
        count = 0

        def repl(m):
            nonlocal count
            if m.group(0).lower() in taboo:
                count += 1
                return "*" * len(m.group(0))
            return m.group(0)

        shown = WORD_RE.sub(repl, text)
        return shown, count


class OrderListManager:
    def __init__(self, catalog):
        self.catalog = catalog

    def refreshLists(self, bookId):
        ratings = publishedRatings(bookId)
        status = NORMAL
        if len(ratings) > config.MIN_RATINGS:
            avg = weightedAverage(ratings)
            if avg < config.LOW_AVG:
                status = NO_ORDER
            elif avg > config.HIGH_AVG:
                status = TO_ORDER
        self.catalog.setListStatus(bookId, status)
        return status


class WarningManager:
    def __init__(self, users, promotions):
        self.users = users
        self.promotions = promotions

    def issueWarning(self, userId, commentId):
        u = self.users.getUser(userId)
        if u is None or u.type not in (RC, VC):
            return None
        FileStore.appendLine(WARNINGS, [FileStore.nextId(WARNINGS), userId, commentId, now()])
        count = self.users.addWarning(userId)
        return self.applyPenalty(userId, count)

    def applyPenalty(self, userId, count):
        u = self.users.getUser(userId)
        if u.type == VC:
            self.promotions.demote(userId)
            return "DEMOTED"
        if u.type == RC and count > config.MAX_WARNINGS:
            self.users.suspend(userId)
            return "SUSPENDED"
        return "WARNED"


class PostResult:
    def __init__(self, status, comment, penalty=None):
        self.status = status
        self.comment = comment
        self.penalty = penalty


class CommentManager:
    def __init__(self, users, catalog, orders, taboo, warnings, lists):
        self.users = users
        self.catalog = catalog
        self.orders = orders
        self.taboo = taboo
        self.warnings = warnings
        self.lists = lists

    def computeWeight(self, user, bookId):
        if user.type in (RC, VC) and self.orders.hasPurchased(user.userId, bookId):
            return config.PURCHASER_WEIGHT
        return 1

    def postComment(self, user, bookId, stars, text):
        try:
            stars = int(stars)
        except (TypeError, ValueError):
            raise BookstoreError("Stars must be a number from 1 to 5.")
        if stars < 1 or stars > 5:
            raise BookstoreError("Stars must be from 1 to 5.")
        text = str(text).strip()
        if not text:
            raise BookstoreError("The comment is empty.")
        if self.catalog.getBook(bookId) is None:
            raise BookstoreError("No such book.")
        weight = self.computeWeight(user, bookId)
        shown, count = self.taboo.filterText(text)
        blocked = count > config.MAX_TABOO
        cid = FileStore.nextId(COMMENTS)
        comment = Comment(cid, user.userId, bookId, stars, text, shown, count, blocked, weight, now(),
                          user.username)
        FileStore.appendLine(COMMENTS, comment.toRow())
        if blocked:
            penalty = self.warnings.issueWarning(user.userId, cid)
            return PostResult("BLOCKED", comment, penalty)
        self.lists.refreshLists(bookId)
        return PostResult("PUBLISHED", comment)

    def commentsFor(self, bookId):
        names = {u.userId: u.username for u in self.users.loadUsers()}
        out = []
        for c in loadComments(bookId):
            if c.blocked:
                continue
            c.username = names.get(c.userId, "Visitor")
            out.append(c)
        return list(reversed(out))
