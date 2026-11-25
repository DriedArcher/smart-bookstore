from .filestore import FileStore
from .models import Comment

COMMENTS = "comments.txt"


def loadComments(bookId=None):
    out = []
    for row in FileStore.readLines(COMMENTS):
        if len(row) < 10:
            continue
        c = Comment.fromRow(row)
        if bookId is None or c.bookId == int(bookId):
            out.append(c)
    return out


def publishedRatings(bookId):
    return [(c.stars, c.weight) for c in loadComments(bookId) if not c.blocked]


def weightedAverage(ratings):
    if not ratings:
        return 0.0
    top = sum(s * w for s, w in ratings)
    bottom = sum(w for _, w in ratings)
    return top / bottom
