from . import config
from .filestore import FileStore
from .models import PAID, REJECTED, RC, VC, BookstoreError
from .users import today

ORDERS = "orders.txt"
ORDER_ITEMS = "order_items.txt"
BROWSE_LOG = "browse_log.txt"


class Cart:
    def __init__(self):
        self.items = {}

    def addItem(self, book, quantity=1):
        if quantity <= 0:
            raise BookstoreError("Quantity must be above 0.")
        if book.bookId in self.items:
            self.items[book.bookId][1] += quantity
        else:
            self.items[book.bookId] = [book, quantity]

    def removeItem(self, bookId):
        self.items.pop(int(bookId), None)

    def getSubtotal(self):
        return round(sum(b.price * q for b, q in self.items.values()), 2)

    def isEmpty(self):
        return not self.items

    def clear(self):
        self.items = {}


class PromotionManager:
    def __init__(self, users):
        self.users = users

    def evaluatePromotion(self, userId):
        u = self.users.getUser(userId)
        if u is None or u.type != RC:
            return u.type if u else None
        count, spent = self.users.getPurchaseStats(userId)
        if count > config.PURCHASE_COUNT_LIMIT or spent > config.SPEND_LIMIT:
            self.users.setType(userId, VC)
            return VC
        return RC

    def discountFor(self, user):
        return user.getDiscount()

    def demote(self, userId):
        self.users.demoteToRC(userId)


class CheckoutResult:
    def __init__(self, status, total, balance, orderId, promotedTo=None, suspended=False):
        self.status = status
        self.total = total
        self.balance = balance
        self.orderId = orderId
        self.promotedTo = promotedTo
        self.suspended = suspended


class OrderManager:
    def __init__(self, users, catalog, promotions):
        self.users = users
        self.catalog = catalog
        self.promotions = promotions

    def computePrice(self, user, cart):
        subtotal = cart.getSubtotal()
        discount = round(subtotal * self.promotions.discountFor(user), 2)
        return subtotal, discount, round(subtotal - discount, 2)

    def recordOrder(self, user, cart, pricing, result):
        oid = FileStore.nextId(ORDERS)
        FileStore.appendLine(ORDERS, [oid, user.userId, today(), pricing[0], pricing[1], pricing[2], result])
        for book, qty in cart.items.values():
            FileStore.appendLine(ORDER_ITEMS, [oid, book.bookId, qty, book.price])
        return oid

    def checkout(self, user, cart):
        user = self.users.getUser(user.userId)
        if user is None or user.type not in (RC, VC):
            raise BookstoreError("Only registered customers can buy books.")
        if not user.isActive():
            raise BookstoreError("This account is suspended.")
        if cart.isEmpty():
            raise BookstoreError("The cart is empty.")
        for bookId in list(cart.items):
            if self.catalog.getBook(bookId) is None:
                cart.removeItem(bookId)
                raise BookstoreError("A book in your cart is no longer in the store. It was removed, check the cart.")
        pricing = self.computePrice(user, cart)
        total = pricing[2]
        if not user.account.canAfford(total):
            user.account.applyFine()
            oid = self.recordOrder(user, cart, pricing, REJECTED)
            suspended = False
            if user.account.isNegative():
                user.status = "SUSPENDED"
                suspended = True
            self.users.updateUser(user)
            return CheckoutResult("FINED", total, user.account.balance, oid, suspended=suspended)
        user.account.charge(total)
        self.users.updateUser(user)
        oid = self.recordOrder(user, cart, pricing, PAID)
        for book, qty in cart.items.values():
            self.catalog.incrementPurchase(book.bookId, qty)
        self.users.recordPurchase(user.userId, total)
        before = user.type
        after = self.promotions.evaluatePromotion(user.userId)
        cart.clear()
        fresh = self.users.getUser(user.userId)
        return CheckoutResult("PAID", total, fresh.account.balance, oid,
                              promotedTo=after if after != before else None)

    def hasPurchased(self, userId, bookId):
        paid = {r[0] for r in FileStore.readLines(ORDERS) if r[1] == str(userId) and r[6] == PAID}
        for item in FileStore.readLines(ORDER_ITEMS):
            if item[0] in paid and item[1] == str(bookId):
                return True
        return False

    def history(self, userId):
        out = []
        rows = [r for r in FileStore.readLines(ORDERS) if r[1] == str(userId) and r[6] == PAID]
        for r in reversed(rows):
            for item in FileStore.readLines(ORDER_ITEMS):
                if item[0] == r[0]:
                    b = self.catalog.getBook(item[1])
                    if b:
                        out.append((b.bookId, b.category))
        for log in FileStore.readLines(BROWSE_LOG):
            if log[1] == str(userId):
                b = self.catalog.getBook(log[2])
                if b:
                    out.append((b.bookId, b.category))
        return out

    def orderRows(self, userId):
        rows = [r for r in FileStore.readLines(ORDERS) if r[1] == str(userId)]
        result = []
        for r in reversed(rows):
            titles = []
            for item in FileStore.readLines(ORDER_ITEMS):
                if item[0] == r[0]:
                    b = self.catalog.getBook(item[1])
                    titles.append(f"{b.title if b else 'Removed book'} x{item[2]}")
            result.append({"orderId": r[0], "date": r[2], "total": float(r[5]), "result": r[6],
                           "items": ", ".join(titles)})
        return result
