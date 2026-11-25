from . import config


class BookstoreError(Exception):
    pass


VS, RC, VC, SU = "VS", "RC", "VC", "SU"
ACTIVE, SUSPENDED = "ACTIVE", "SUSPENDED"
NORMAL, NO_ORDER, TO_ORDER = "NORMAL", "NO_ORDER", "TO_ORDER"
PAID, REJECTED = "PAID", "REJECTED"


class Account:
    def __init__(self, userId, balance=0.0):
        self.userId = userId
        self.balance = round(float(balance), 2)

    def deposit(self, amount):
        amount = float(amount)
        if amount <= 0:
            raise BookstoreError("Amount must be above 0.")
        self.balance = round(self.balance + amount, 2)
        return self.balance

    def canAfford(self, amount):
        return round(self.balance - float(amount), 2) >= 0

    def charge(self, amount):
        self.balance = round(self.balance - float(amount), 2)
        return self.balance

    def applyFine(self):
        self.balance = round(self.balance - config.FINE, 2)
        return self.balance

    def isNegative(self):
        return self.balance < 0


class User:
    type = VS
    level = 1
    features = frozenset({"login", "register", "browse", "search", "comment", "chat"})

    def __init__(self, userId=0, username="Visitor", status=ACTIVE, warningCount=0,
                 purchaseCount=0, totalSpent=0.0, faceLabel="", voiceLabel="", balance=0.0):
        self.userId = int(userId)
        self.username = username
        self.status = status
        self.warningCount = int(warningCount)
        self.purchaseCount = int(purchaseCount)
        self.totalSpent = round(float(totalSpent), 2)
        self.faceLabel = faceLabel
        self.voiceLabel = voiceLabel
        self.account = None

    def canAccess(self, feature):
        return feature in self.features

    def chatLevel(self):
        return self.level

    def getDiscount(self):
        return 0.0

    def isActive(self):
        return self.status == ACTIVE

    def balance(self):
        return self.account.balance if self.account else 0.0

    def toRow(self):
        return [self.userId, self.username, self.type, self.status, self.warningCount,
                self.purchaseCount, self.totalSpent, self.balance(), self.faceLabel, self.voiceLabel]


class Visitor(User):
    pass


class Customer(User):
    type = RC
    level = 2
    features = User.features | {"purchase", "cart", "history", "account"}

    def __init__(self, *args, balance=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = Account(self.userId, balance)


class VIPCustomer(Customer):
    type = VC
    level = 3

    def getDiscount(self):
        return config.VIP_DISCOUNT


class SuperUser(User):
    type = SU
    level = 4
    features = User.features | {"admin", "history", "account"}


USER_TYPES = {VS: Visitor, RC: Customer, VC: VIPCustomer, SU: SuperUser}


def newUserOfType(userType, **kwargs):
    return USER_TYPES[userType](**kwargs)


class Book:
    def __init__(self, bookId, title, author, category, year, price, coverPath="", textPath="",
                 listStatus=NORMAL, viewCount=0, purchaseCount=0, description=""):
        self.bookId = int(bookId)
        self.title = title
        self.author = author
        self.category = category
        self.year = int(year)
        self.price = round(float(price), 2)
        self.coverPath = coverPath
        self.textPath = textPath
        self.listStatus = listStatus
        self.viewCount = int(viewCount)
        self.purchaseCount = int(purchaseCount)
        self.description = description
        self.avgRating = 0.0
        self.ratingCount = 0

    @classmethod
    def fromRow(cls, row):
        row = list(row) + [""] * (12 - len(row))
        return cls(*row[:12])

    def toRow(self):
        return [self.bookId, self.title, self.author, self.category, self.year, self.price,
                self.coverPath, self.textPath, self.listStatus, self.viewCount,
                self.purchaseCount, self.description]


class Comment:
    def __init__(self, commentId, userId, bookId, stars, rawText, shownText, tabooCount,
                 blocked, weight, postedAt, username=""):
        self.commentId = int(commentId)
        self.userId = int(userId)
        self.bookId = int(bookId)
        self.stars = int(stars)
        self.rawText = rawText
        self.shownText = shownText
        self.tabooCount = int(tabooCount)
        self.blocked = str(blocked) in ("1", "True", "true")
        self.weight = int(weight)
        self.postedAt = postedAt
        self.username = username

    @classmethod
    def fromRow(cls, row):
        return cls(*row[:10])

    def toRow(self):
        return [self.commentId, self.userId, self.bookId, self.stars, self.rawText, self.shownText,
                self.tabooCount, 1 if self.blocked else 0, self.weight, self.postedAt]
