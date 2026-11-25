import re
from . import config
from .filestore import FileStore
from .models import PAID, REJECTED, RC, VC, SU

ORDERS = "orders.txt"
ORDER_ITEMS = "order_items.txt"

MOODS = {
    "happy": ["happy", "great", "excited", "cheerful", "joy", "good mood"],
    "sad": ["sad", "down", "lonely", "depressed", "blue", "cry"],
    "stressed": ["stressed", "anxious", "overwhelmed", "tired", "burned out", "burnt out", "exhausted", "worried"],
    "bored": ["bored", "boring", "nothing to do"],
    "curious": ["curious", "learn", "wonder", "smart", "understand"],
    "romantic": ["romantic", "love", "romance", "date night"],
    "scared": ["scary", "spooky", "creepy", "halloween", "horror", "thrill"],
}
MOOD_CATEGORIES = {
    "happy": ["Humor", "Adventure"],
    "sad": ["Poetry", "Literature", "Romance"],
    "stressed": ["Humor", "Adventure"],
    "bored": ["Mystery", "Adventure", "Science Fiction"],
    "curious": ["Science", "History", "Science Fiction", "Philosophy"],
    "romantic": ["Romance", "Poetry"],
    "scared": ["Horror", "Mystery"],
}
REQUIRED_LEVEL = {"general": 1, "store": 1, "mood": 1, "account": 2, "savings": 3, "booklists": 4, "finance": 4}
DENIED = "No information is available for your account."


class Recommender:
    def __init__(self, catalog, orders):
        self.catalog = catalog
        self.orders = orders

    def topThree(self, user):
        if user.type in (RC, VC):
            return self.personalTop(user, 3)
        return self.globalTop(3)

    def globalTop(self, n):
        return self.catalog.topByActivity(n)

    def personalTop(self, user, n):
        hist = self.orders.history(user.userId)
        if not hist:
            return self.globalTop(n)
        counts = {}
        for _, cat in hist:
            counts[cat] = counts.get(cat, 0) + 1
        favorites = [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:2]]
        seen = {b for b, _ in hist}
        picks = [b for b in self.catalog.booksInCategories(favorites)
                 if b.bookId not in seen and b.listStatus != "NO_ORDER"]
        result = picks[:n]
        if len(result) < n:
            have = {b.bookId for b in result}
            for b in self.globalTop(n + len(have) + len(seen)):
                if b.bookId not in have and b.bookId not in seen and len(result) < n:
                    result.append(b)
                    have.add(b.bookId)
        return result


class FinanceReport:
    def __init__(self, users, catalog):
        self.users = users
        self.catalog = catalog

    def data(self):
        orders = FileStore.readLines(ORDERS)
        items = FileStore.readLines(ORDER_ITEMS)
        paid = [o for o in orders if o[6] == PAID]
        fined = [o for o in orders if o[6] == REJECTED]
        paidIds = {o[0] for o in paid}
        byCat = {}
        for it in items:
            if it[0] in paidIds:
                b = self.catalog.getBook(it[1])
                if b:
                    byCat[b.category] = round(byCat.get(b.category, 0) + float(it[3]) * int(it[2]), 2)
        revenue = round(sum(float(o[5]) for o in paid), 2)
        discounts = round(sum(float(o[4]) for o in paid), 2)
        users = self.users.loadUsers()
        best = max(self.catalog.loadBooks(), key=lambda b: (b.purchaseCount, b.title), default=None)
        return {
            "revenue": revenue, "paidOrders": len(paid), "discounts": discounts,
            "fines": round(len(fined) * config.FINE, 2), "byCategory": byCat,
            "customers": sum(1 for u in users if u.type == RC), "vips": sum(1 for u in users if u.type == VC),
            "suspended": sum(1 for u in users if u.status == "SUSPENDED"),
            "best": best if best and best.purchaseCount > 0 else None,
        }

    def generate(self):
        d = self.data()
        lines = [f"Revenue: ${d['revenue']:.2f} from {d['paidOrders']} paid orders",
                 f"VIP discounts given: ${d['discounts']:.2f}",
                 f"Fines collected: ${d['fines']:.2f}",
                 f"Customers: {d['customers']} regular, {d['vips']} VIP, {d['suspended']} suspended"]
        if d["byCategory"]:
            cats = ", ".join(f"{c} ${v:.2f}" for c, v in sorted(d["byCategory"].items(), key=lambda kv: -kv[1]))
            lines.append("Revenue by category: " + cats)
        if d["best"]:
            lines.append(f"Best seller: {d['best'].title} ({d['best'].purchaseCount} sold)")
        return "\n".join(lines)


class MoodAdvisor:
    def __init__(self, catalog, llm, recommender):
        self.catalog = catalog
        self.llm = llm
        self.recommender = recommender

    def detectMood(self, text):
        t = text.lower()
        if self.llm is not None and self.llm.isOnline():
            label = self.llm.ask("Label the mood of this message with exactly one word from: " +
                                 ", ".join(MOODS) + ". Message: " + text).strip().lower()
            label = re.sub(r"[^a-z]", "", label)
            if label in MOODS:
                return label
        for mood, words in MOODS.items():
            if any(w in t for w in words):
                return mood
        return None

    def suggest(self, user, text):
        mood = self.detectMood(text)
        if mood is None:
            return "Tell me a bit more about how you feel or what you want to read."
        books = self.catalog.booksInCategories(MOOD_CATEGORIES[mood])
        books = [b for b in books if b.listStatus != "NO_ORDER"]
        if not books:
            books = self.recommender.globalTop(3)
        lines = [f"For a {mood} mood, try:"]
        for b in books[:3]:
            rating = f", rated {b.avgRating:.1f}/5" if b.ratingCount else ""
            first = b.description.split(".")[0].strip()
            lines.append(f"- {b.title} by {b.author} ({b.category}{rating}). {first}." if first else
                         f"- {b.title} by {b.author} ({b.category}{rating}).")
        return "\n".join(lines)


class ChatReply:
    def __init__(self, text, source):
        self.text = text
        self.source = source


class ChatService:
    def __init__(self, users, catalog, orders, rag, llm, finance, mood):
        self.users = users
        self.catalog = catalog
        self.orders = orders
        self.rag = rag
        self.llm = llm
        self.finance = finance
        self.mood = mood

    def classifyIntent(self, text):
        t = text.lower()
        has = lambda ws: any(w in t for w in ws)
        if has(["revenue", "profit", "finance", "financial", "sales report", "income", "earnings"]):
            return "finance"
        if has(["no-order", "to-order", "order list", "no order list", "to order list"]):
            return "booklists"
        if has(["i saved", "my savings", "how much have i saved", "vip savings", "discount i got"]):
            return "savings"
        if has(["my balance", "my orders", "my account", "my warnings", "my purchases", "my status"]):
            return "account"
        if has(["i feel", "i'm feeling", "im feeling", "mood", "stressed", "bored", "sad ", "recommend me", "suggest a book",
                "something to read", "i want something"]):
            return "mood"
        return "general"

    def permits(self, level, intent):
        return level >= REQUIRED_LEVEL.get(intent, 1)

    def routeToRagOrLlm(self, text):
        isLocal, passages = self.rag.isLocalQuestion(text)
        if isLocal:
            ans = self.rag.answerFromPassages(text, passages, self.llm)
            return ans + "\n[answered via RAG from local store files]", "RAG"
        if not self.llm.isOnline():
            return "The language model is offline right now, and the local store files have no answer for that.", "RULE"
        return self.llm.ask(text) + "\n[answered by the LLM]", "LLM"

    def accountAnswer(self, user):
        u = self.users.getUser(user.userId)
        return (f"Balance: ${u.balance():.2f}. Purchases: {u.purchaseCount}. Total spent: ${u.totalSpent:.2f}. "
                f"Warnings: {u.warningCount}. Status: {u.status}. Type: {u.type}.")

    def savingsAnswer(self, user):
        total = 0.0
        for o in FileStore.readLines(ORDERS):
            if o[1] == str(user.userId) and o[6] == PAID:
                total += float(o[4])
        return f"Your VIP discounts have saved you ${total:.2f} so far."

    def listsAnswer(self):
        no, to = self.catalog.lists()
        return ("No-order list: " + (", ".join(b.title for b in no) or "none") + "\n" +
                "To-order list: " + (", ".join(b.title for b in to) or "none"))

    def handleQuery(self, user, text):
        text = str(text).strip()
        if not text:
            return ChatReply("", "RULE")
        intent = self.classifyIntent(text)
        if not self.permits(user.chatLevel(), intent):
            return ChatReply(DENIED, "RULE")
        if intent == "finance":
            return ChatReply(self.finance.generate(), "RULE")
        if intent == "booklists":
            return ChatReply(self.listsAnswer(), "RULE")
        if intent == "account":
            return ChatReply(self.accountAnswer(user), "RULE")
        if intent == "savings":
            return ChatReply(self.savingsAnswer(user), "RULE")
        if intent == "mood":
            return ChatReply(self.mood.suggest(user, text), "RULE")
        answer, source = self.routeToRagOrLlm(text)
        return ChatReply(answer, source)
