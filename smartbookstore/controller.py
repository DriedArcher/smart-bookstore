from .catalog import BookCatalog
from .chat import ChatService, FinanceReport, MoodAdvisor, Recommender
from .face import FaceRecognizer
from .filestore import FileStore
from .llm import LLMClient
from .models import BookstoreError, SU, Visitor
from .moderation import CommentManager, OrderListManager, TabooList, WarningManager
from .orders import Cart, OrderManager, PromotionManager
from .rag import RAGEngine
from .users import AuthManager, UserManager
from .voice import VoiceRecognizer


class Session:
    def __init__(self):
        self.user = Visitor()
        self.cart = Cart()


class SystemController:
    def __init__(self, face=None, voice=None, llm=None):
        FileStore.ensureDirs()
        self.users = UserManager()
        self.catalog = BookCatalog()
        self.face = face or FaceRecognizer()
        self.voice = voice or VoiceRecognizer()
        self.llm = llm or LLMClient()
        self.auth = AuthManager(self.users, self.face, self.voice)
        self.promotions = PromotionManager(self.users)
        self.orders = OrderManager(self.users, self.catalog, self.promotions)
        self.taboo = TabooList()
        self.lists = OrderListManager(self.catalog)
        self.warnings = WarningManager(self.users, self.promotions)
        self.comments = CommentManager(self.users, self.catalog, self.orders, self.taboo, self.warnings, self.lists)
        self.recommender = Recommender(self.catalog, self.orders)
        self.finance = FinanceReport(self.users, self.catalog)
        self.rag = RAGEngine(self.catalog)
        self.mood = MoodAdvisor(self.catalog, self.llm, self.recommender)
        self.chatService = ChatService(self.users, self.catalog, self.orders, self.rag, self.llm,
                                       self.finance, self.mood)
        self.session = Session()

    @property
    def user(self):
        return self.session.user

    def refreshUser(self):
        if self.session.user.userId != 0:
            fresh = self.users.getUser(self.session.user.userId)
            self.session.user = fresh if fresh is not None else Visitor()
        return self.session.user

    def require(self, feature):
        if not self.session.user.canAccess(feature):
            raise BookstoreError("You do not have access to that.")

    def needsSetup(self):
        return not self.users.hasSuperUser()

    def login(self, sampleType, sample):
        user = self.auth.login(sampleType, sample)
        self.session = Session()
        self.session.user = user
        return user

    def register(self, name, faceImages=None, voiceClips=None, userType="RC"):
        if userType == SU:
            if not self.needsSetup():
                raise BookstoreError("A super user already exists.")
        else:
            self.require("register")
        return self.auth.registerUser(name, faceImages, voiceClips, userType)

    def logout(self):
        self.session = Session()

    def topThree(self):
        return self.recommender.topThree(self.refreshUser())

    def browse(self, category="", author="", yearFrom=None, yearTo=None, sortBy="title"):
        self.require("browse")
        return self.catalog.browse(category, author, yearFrom, yearTo, sortBy)

    def search(self, text):
        self.require("search")
        return self.catalog.searchKeyword(text)

    def searchImage(self, picture):
        self.require("search")
        return self.catalog.searchImage(picture)

    def openBook(self, bookId):
        self.require("browse")
        book = self.catalog.getBook(bookId)
        if book is None:
            raise BookstoreError("No such book.")
        self.catalog.logView(self.session.user.userId, bookId)
        return self.catalog.getBook(bookId), self.comments.commentsFor(bookId)

    def addToCart(self, bookId, quantity=1):
        self.require("cart")
        book = self.catalog.getBook(bookId)
        if book is None:
            raise BookstoreError("No such book.")
        self.session.cart.addItem(book, quantity)

    def removeFromCart(self, bookId):
        self.session.cart.removeItem(bookId)

    def cartPricing(self):
        return self.orders.computePrice(self.refreshUser(), self.session.cart)

    def checkout(self):
        self.require("purchase")
        result = self.orders.checkout(self.session.user, self.session.cart)
        self.refreshUser()
        if result.suspended:
            self.logout()
        return result

    def topUp(self, amount):
        self.require("account")
        bal = self.users.topUp(self.session.user.userId, amount)
        self.refreshUser()
        return bal

    def orderHistory(self):
        self.require("history")
        return self.orders.orderRows(self.session.user.userId)

    def postComment(self, bookId, stars, text):
        self.require("comment")
        result = self.comments.postComment(self.session.user, bookId, stars, text)
        self.refreshUser()
        if self.session.user.userId != 0 and self.auth.isSuspended(self.session.user):
            self.logout()
        return result

    def chat(self, text):
        self.require("chat")
        return self.chatService.handleQuery(self.refreshUser(), text)

    def addBook(self, **fields):
        self.require("admin")
        return self.catalog.addBook(**fields)

    def tabooWords(self):
        self.require("admin")
        return self.taboo.words()

    def addTaboo(self, word):
        self.require("admin")
        self.taboo.add(word)

    def removeTaboo(self, word):
        self.require("admin")
        self.taboo.remove(word)

    def customers(self):
        self.require("admin")
        return [u for u in self.users.loadUsers() if u.account]

    def reopen(self, userId, amount):
        self.require("admin")
        return self.users.reopenAccount(self.session.user.userId, userId, amount)

    def bookLists(self):
        self.require("admin")
        return self.catalog.lists()

    def financeReport(self):
        self.require("admin")
        return self.finance.generate()
