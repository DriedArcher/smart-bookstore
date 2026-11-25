import re
from datetime import datetime
from . import config
from .filestore import FileStore
from .models import (ACTIVE, SUSPENDED, RC, VC, SU, BookstoreError, Visitor, newUserOfType)

USERS = "users.txt"
DEPOSITS = "deposits.txt"
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


class UserManager:
    def _build(self, row):
        row = list(row) + [""] * (10 - len(row))
        return newUserOfType(row[2], userId=row[0], username=row[1], status=row[3],
                             warningCount=row[4], purchaseCount=row[5], totalSpent=row[6],
                             balance=row[7] or 0, faceLabel=row[8], voiceLabel=row[9])

    def loadUsers(self):
        return [self._build(r) for r in FileStore.readLines(USERS)]

    def getUser(self, userId):
        userId = int(userId)
        if userId == 0:
            return Visitor()
        for u in self.loadUsers():
            if u.userId == userId:
                return u
        return None

    def findByName(self, name):
        for u in self.loadUsers():
            if u.username.lower() == str(name).strip().lower():
                return u
        return None

    def nameExists(self, name):
        return self.findByName(name) is not None

    def hasSuperUser(self):
        return any(u.type == SU for u in self.loadUsers())

    def createUser(self, name, userType=RC, balance=None):
        uid = FileStore.nextId(USERS)
        if balance is None:
            balance = config.STARTING_BALANCE if userType in (RC, VC) else 0
        FileStore.appendLine(USERS, [uid, name, userType, ACTIVE, 0, 0, 0, balance, f"face{uid}", f"voice{uid}"])
        return self.getUser(uid)

    def updateUser(self, user):
        FileStore.replaceLine(USERS, user.userId, user.toRow())

    def deleteUser(self, userId):
        FileStore.deleteLine(USERS, userId)

    def setType(self, userId, userType):
        u = self.getUser(userId)
        u.type = userType
        row = u.toRow()
        row[2] = userType
        FileStore.replaceLine(USERS, userId, row)

    def demoteToRC(self, userId):
        u = self.getUser(userId)
        if u is None or u.type != VC:
            return
        row = u.toRow()
        row[2] = RC
        row[5] = 0
        row[6] = 0
        FileStore.replaceLine(USERS, userId, row)

    def suspend(self, userId):
        u = self.getUser(userId)
        u.status = SUSPENDED
        self.updateUser(u)

    def addWarning(self, userId):
        u = self.getUser(userId)
        u.warningCount += 1
        self.updateUser(u)
        return u.warningCount

    def recordPurchase(self, userId, total):
        u = self.getUser(userId)
        u.purchaseCount += 1
        u.totalSpent = round(u.totalSpent + total, 2)
        self.updateUser(u)

    def getPurchaseStats(self, userId):
        u = self.getUser(userId)
        return u.purchaseCount, u.totalSpent

    def _logDeposit(self, userId, suId, amount):
        FileStore.appendLine(DEPOSITS, [FileStore.nextId(DEPOSITS), userId, suId, amount, today()])

    def topUp(self, userId, amount):
        u = self.getUser(userId)
        if u is None or not u.account:
            raise BookstoreError("Only customers have an account.")
        if not u.isActive():
            raise BookstoreError("This account is suspended. Ask the super user to reopen it.")
        u.account.deposit(amount)
        self.updateUser(u)
        self._logDeposit(userId, 0, round(float(amount), 2))
        return u.account.balance

    def reopenAccount(self, suId, userId, amount):
        su = self.getUser(suId)
        if su is None or su.type != SU:
            raise BookstoreError("Only the super user can reopen accounts.")
        u = self.getUser(userId)
        if u is None or not u.account:
            raise BookstoreError("No such customer account.")
        if u.status != SUSPENDED:
            raise BookstoreError("This account is not suspended.")
        u.account.deposit(amount)
        self._logDeposit(userId, suId, round(float(amount), 2))
        if u.account.balance > 0:
            u.status = ACTIVE
            self.updateUser(u)
            return True
        self.updateUser(u)
        raise BookstoreError("Balance is still not positive, the account stays suspended.")

    def suspendedUsers(self):
        return [u for u in self.loadUsers() if u.status == SUSPENDED]


class AuthManager:
    def __init__(self, users, face, voice):
        self.users = users
        self.face = face
        self.voice = voice

    def isSuspended(self, user):
        if user.status == SUSPENDED:
            return True
        return bool(user.account and user.account.isNegative())

    def login(self, sampleType, sample):
        if sampleType == "face":
            rec = self.face
            if rec.detectFace(sample) is None:
                raise BookstoreError("No face found. Look at the camera and try again.")
        elif sampleType == "voice":
            rec = self.voice
        else:
            raise BookstoreError("Unknown login method.")
        result = rec.classify(sample)
        if result is None:
            raise BookstoreError("Not recognized. No trained profile matches the sample.")
        userId, conf = result
        if conf < rec.minConfidence():
            raise BookstoreError("Not recognized.")
        user = self.users.getUser(userId)
        if user is None or user.type == "VS":
            raise BookstoreError("Not recognized.")
        if self.isSuspended(user):
            raise BookstoreError("Your account is suspended. Please contact the super user to reopen it.")
        return user

    def registerUser(self, name, faceImages=None, voiceClips=None, userType=RC):
        name = str(name).strip()
        if not NAME_RE.match(name):
            raise BookstoreError("Username must be 3 to 20 letters, digits, dot, dash or underscore.")
        if self.users.nameExists(name):
            raise BookstoreError("That username is already used.")
        if userType == SU and self.users.hasSuperUser():
            raise BookstoreError("A super user already exists.")
        if not faceImages and not voiceClips:
            raise BookstoreError("Provide face pictures and/or voice clips.")
        user = self.users.createUser(name, userType)
        try:
            if faceImages:
                if not self.face.train(faceImages, user.userId):
                    raise BookstoreError(
                        f"Not enough usable face pictures (need {config.MIN_FACE_CROPS} with a clear face).")
            if voiceClips:
                if not self.voice.train(voiceClips, user.userId):
                    raise BookstoreError("Voice clips were too short or silent. Record again.")
        except Exception:
            self.users.deleteUser(user.userId)
            self.face.deleteUser(user.userId)
            self.voice.deleteUser(user.userId)
            raise
        return user
