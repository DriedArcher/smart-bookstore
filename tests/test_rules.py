import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from smartbookstore import config
from smartbookstore.llm import LLMClient
from smartbookstore.models import BookstoreError
from tests.helpers import FakeFace, loginAs, makeCustomer, newController, startFakeOllama


def buy(c, bookId=1, qty=1):
    c.addToCart(bookId, qty)
    return c.checkout()


class AccountRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_purchase_over_balance_fines_one_dollar_and_cancels(self):
        makeCustomer(self.c, "alice", 10)
        loginAs(self.c, "alice")
        self.c.addToCart(13, 2)
        r = self.c.checkout()
        self.assertEqual(r.status, "FINED")
        self.assertEqual(r.balance, 9.0)
        u = self.c.users.findByName("alice")
        self.assertEqual(u.purchaseCount, 0)
        self.assertTrue(u.isActive())
        self.assertEqual(self.c.catalog.getBook(13).purchaseCount, 0)

    def test_negative_balance_suspends_and_blocks_login_until_reopened(self):
        makeCustomer(self.c, "bob", 0.5)
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "bob")
        r = buy(self.c, 1)
        self.assertEqual(r.status, "FINED")
        self.assertTrue(r.suspended)
        self.assertEqual(self.c.user.userId, 0)
        with self.assertRaises(BookstoreError):
            loginAs(self.c, "bob")
        loginAs(self.c, "root")
        bobId = self.c.users.findByName("bob").userId
        with self.assertRaises(BookstoreError):
            self.c.reopen(bobId, 0.2)
        with self.assertRaises(BookstoreError):
            loginAs(self.c, "bob")
        self.assertTrue(self.c.reopen(bobId, 5))
        self.c.logout()
        loginAs(self.c, "bob")

    def test_only_super_user_can_reopen(self):
        makeCustomer(self.c, "eve", 0.5)
        loginAs(self.c, "eve")
        with self.assertRaises(BookstoreError):
            self.c.reopen(1, 5)

    def test_visitor_cannot_buy_or_use_cart(self):
        with self.assertRaises(BookstoreError):
            self.c.addToCart(1)
        with self.assertRaises(BookstoreError):
            self.c.checkout()

    def test_topup_only_for_active_customers(self):
        makeCustomer(self.c, "cy", 10)
        loginAs(self.c, "cy")
        self.assertEqual(self.c.topUp(5), 15.0)
        with self.assertRaises(BookstoreError):
            self.c.topUp(-3)

    def test_paid_purchase_updates_balance_counts_and_book(self):
        makeCustomer(self.c, "dee", 20)
        loginAs(self.c, "dee")
        r = buy(self.c, 1)
        self.assertEqual(r.status, "PAID")
        self.assertAlmostEqual(r.balance, 15.01, places=2)
        u = self.c.users.findByName("dee")
        self.assertEqual((u.purchaseCount, u.totalSpent), (1, 4.99))
        self.assertEqual(self.c.catalog.getBook(1).purchaseCount, 1)


class PromotionRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_promoted_after_more_than_three_purchases_with_ten_percent_discount(self):
        makeCustomer(self.c, "vic", 100)
        loginAs(self.c, "vic")
        for _ in range(3):
            self.assertIsNone(buy(self.c, 1).promotedTo)
        self.assertEqual(self.c.user.type, "RC")
        self.assertEqual(buy(self.c, 1).promotedTo, "VC")
        self.assertEqual(self.c.user.type, "VC")
        self.c.addToCart(1)
        sub, disc, total = self.c.cartPricing()
        self.assertEqual((sub, disc, total), (4.99, 0.5, 4.49))
        r = self.c.checkout()
        self.assertAlmostEqual(r.total, 4.49)

    def test_promoted_after_spending_more_than_200(self):
        makeCustomer(self.c, "rich", 1000)
        loginAs(self.c, "rich")
        bid = self.c.catalog.addBook(title="Gold Bar", author="Nobody", category="Literature", year=2000, price=250)
        r = buy(self.c, bid)
        self.assertEqual(r.promotedTo, "VC")

    def test_exactly_200_is_not_enough(self):
        makeCustomer(self.c, "edge", 1000)
        loginAs(self.c, "edge")
        bid = self.c.catalog.addBook(title="Exactly", author="Nobody", category="Literature", year=2000, price=200)
        self.assertIsNone(buy(self.c, bid).promotedTo)


class CommentRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_visitor_can_comment(self):
        r = self.c.postComment(1, 4, "Lovely read")
        self.assertEqual(r.status, "PUBLISHED")
        self.assertEqual(r.comment.userId, 0)

    def test_input_validation(self):
        for stars in (0, 6, "x"):
            with self.assertRaises(BookstoreError):
                self.c.postComment(1, stars, "ok")
        with self.assertRaises(BookstoreError):
            self.c.postComment(1, 3, "   ")
        with self.assertRaises(BookstoreError):
            self.c.postComment(9999, 3, "ok")

    def test_taboo_words_masked(self):
        r = self.c.postComment(1, 3, "This is Stupid and dumb, heck")
        self.assertEqual(r.status, "PUBLISHED")
        self.assertEqual(r.comment.shownText, "This is ****** and ****, ****")
        self.assertEqual(r.comment.tabooCount, 3)

    def test_taboo_inside_longer_word_not_masked(self):
        r = self.c.postComment(1, 3, "Stupidity is not on the list, nor is hecktic")
        self.assertEqual(r.comment.tabooCount, 0)

    def test_more_than_three_blocks_comment_and_warns_author(self):
        makeCustomer(self.c, "fay", 10)
        loginAs(self.c, "fay")
        r = self.c.postComment(1, 1, "darn heck crap stupid")
        self.assertEqual(r.status, "BLOCKED")
        self.assertEqual(self.c.users.findByName("fay").warningCount, 1)
        shown = self.c.comments.commentsFor(1)
        self.assertEqual(shown, [])
        self.assertEqual(self.c.catalog.getBook(1).ratingCount, 0)

    def test_rc_suspended_after_more_than_two_warnings(self):
        makeCustomer(self.c, "gus", 10)
        loginAs(self.c, "gus")
        for i in range(2):
            self.c.postComment(1, 1, "darn heck crap stupid")
            self.assertEqual(self.c.user.userId != 0, True)
        self.assertTrue(self.c.users.findByName("gus").isActive())
        self.c.postComment(1, 1, "darn heck crap stupid")
        self.assertEqual(self.c.users.findByName("gus").status, "SUSPENDED")
        self.assertEqual(self.c.user.userId, 0)
        with self.assertRaises(BookstoreError):
            loginAs(self.c, "gus")

    def test_vc_demoted_on_warning(self):
        makeCustomer(self.c, "hal", 100)
        loginAs(self.c, "hal")
        for _ in range(4):
            buy(self.c, 1)
        self.assertEqual(self.c.user.type, "VC")
        r = self.c.postComment(1, 1, "darn heck crap stupid")
        self.assertEqual(r.penalty, "DEMOTED")
        self.assertEqual(self.c.user.type, "RC")
        self.assertEqual(self.c.user.getDiscount(), 0)
        self.assertTrue(self.c.user.isActive())

    def test_visitor_blocked_comment_has_no_account_to_warn(self):
        r = self.c.postComment(1, 1, "darn heck crap stupid")
        self.assertEqual(r.status, "BLOCKED")
        self.assertIsNone(r.penalty)

    def test_su_taboo_list_edit_applies_to_next_comment(self):
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "root")
        self.c.addTaboo("Spoiler")
        r = self.c.postComment(1, 3, "no spoiler please")
        self.assertEqual(r.comment.shownText, "no ******* please")
        self.c.removeTaboo("spoiler")
        r = self.c.postComment(1, 3, "no spoiler please")
        self.assertEqual(r.comment.shownText, "no spoiler please")
        self.c.logout()
        with self.assertRaises(BookstoreError):
            self.c.addTaboo("x")


class OrderListRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def post(self, stars, n):
        for _ in range(n):
            self.c.postComment(2, stars, "ok")

    def status(self):
        return self.c.catalog.getBook(2).listStatus

    def test_three_ratings_is_not_enough(self):
        self.post(1, 3)
        self.assertEqual(self.status(), "NORMAL")

    def test_no_order_list(self):
        self.post(1, 4)
        self.assertEqual(self.status(), "NO_ORDER")
        no, to = self.c.catalog.lists()
        self.assertEqual([b.bookId for b in no], [2])
        self.assertEqual(to, [])

    def test_to_order_list(self):
        self.post(5, 4)
        self.assertEqual(self.status(), "TO_ORDER")

    def test_average_exactly_four_is_normal(self):
        self.post(4, 4)
        self.assertEqual(self.status(), "NORMAL")

    def test_status_recovers_when_average_moves(self):
        self.post(1, 4)
        self.assertEqual(self.status(), "NO_ORDER")
        self.post(5, 6)
        self.assertEqual(self.status(), "NORMAL")

    def test_purchaser_weight_counts_double(self):
        makeCustomer(self.c, "ivy", 50)
        loginAs(self.c, "ivy")
        buy(self.c, 2)
        self.c.postComment(2, 5, "bought it")
        self.c.logout()
        self.c.postComment(2, 2, "visitor view")
        b = self.c.catalog.getBook(2)
        self.assertAlmostEqual(b.avgRating, (5 * 2 + 2) / 3, places=2)

    def test_blocked_comments_do_not_count(self):
        self.post(5, 3)
        self.c.postComment(2, 1, "darn heck crap stupid")
        self.assertEqual(self.c.catalog.getBook(2).ratingCount, 3)
        self.assertEqual(self.status(), "NORMAL")


class CatalogRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_browse_filters(self):
        horror = self.c.browse(category="Horror")
        self.assertEqual({b.category for b in horror}, {"Horror"})
        austen = self.c.browse(author="Jane Austen")
        self.assertEqual(len(austen), 3)
        early = self.c.browse(yearFrom=1800, yearTo=1820)
        self.assertTrue(all(1800 <= b.year <= 1820 for b in early))
        self.assertEqual(self.c.browse(sortBy="year")[0].year, 180)

    def test_keyword_search_needs_all_words(self):
        self.assertEqual([b.title for b in self.c.search("holmes baskervilles")], ["The Hound of the Baskervilles"])
        self.assertEqual(self.c.search("holmes zzzz"), [])
        self.assertEqual(self.c.search("   "), [])

    def test_image_search_finds_cover_even_if_resized_and_compressed(self):
        book = self.c.catalog.getBook(7)
        img = cv2.imread(str(config.DATA / book.coverPath))
        small = cv2.resize(img, (150, 225))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        degraded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        hits = self.c.searchImage(degraded)
        self.assertEqual(hits[0][0].bookId, 7)

    def test_image_search_rejects_unrelated_picture(self):
        noise = np.random.default_rng(1).integers(0, 255, (200, 200, 3), dtype=np.uint8)
        self.assertEqual(self.c.searchImage(noise), [])

    def test_opening_book_logs_view(self):
        self.c.openBook(5)
        self.c.openBook(5)
        self.assertEqual(self.c.catalog.getBook(5).viewCount, 2)

    def test_add_book_su_only_and_validated(self):
        with self.assertRaises(BookstoreError):
            self.c.addBook(title="X", author="Y", category="Z", year=2000, price=3)
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "root")
        bid = self.c.addBook(title="New Book", author="Me", category="Humor", year=2024, price=5.5, description="d")
        book = self.c.catalog.getBook(bid)
        self.assertTrue((config.DATA / book.coverPath).exists())
        self.assertEqual(self.c.search("new book")[0].bookId, bid)
        for bad in [dict(title="", author="a", category="c", year=1, price=1),
                    dict(title="t", author="a", category="c", year="abc", price=1),
                    dict(title="t2", author="a", category="c", year=1, price=0),
                    dict(title="New Book", author="Me", category="c", year=1, price=1)]:
            with self.assertRaises(BookstoreError):
                self.c.addBook(**bad)

    def test_file_fields_cannot_break_records(self):
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "root")
        bid = self.c.addBook(title="Pipe|Title\nNewline", author="A|B", category="Humor", year=2000, price=1,
                             description="x|y")
        b = self.c.catalog.getBook(bid)
        self.assertEqual(b.title, "Pipe Title Newline")
        self.assertEqual(len(self.c.catalog.loadBooks()), 36)


class TopPageRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_visitor_and_su_see_global_top_by_purchases_and_views(self):
        for _ in range(3):
            self.c.openBook(20)
        self.c.openBook(21)
        top = [b.bookId for b in self.c.topThree()]
        self.assertEqual(top[:2], [20, 21])
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "root")
        self.assertEqual([b.bookId for b in self.c.topThree()][:2], [20, 21])

    def test_customer_gets_personal_picks_from_own_history(self):
        makeCustomer(self.c, "jo", 50)
        loginAs(self.c, "jo")
        buy(self.c, 6)
        self.c.openBook(7)
        top = self.c.topThree()
        self.assertEqual(len(top), 3)
        self.assertTrue(all(b.category == "Horror" for b in top[:1]))
        self.assertNotIn(6, [b.bookId for b in top])
        self.assertNotIn(7, [b.bookId for b in top])

    def test_new_customer_falls_back_to_global(self):
        makeCustomer(self.c, "kim", 10)
        loginAs(self.c, "kim")
        self.assertEqual(len(self.c.topThree()), 3)


class ChatRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_finance_denied_to_everyone_but_su(self):
        r = self.c.chat("show me the finance report")
        self.assertEqual(r.text, "No information is available for your account.")
        makeCustomer(self.c, "lee", 100, "RC")
        loginAs(self.c, "lee")
        self.assertIn("No information", self.c.chat("what is our revenue").text)
        buy(self.c, 1)
        self.c.logout()
        makeCustomer(self.c, "root", 0, "SU")
        loginAs(self.c, "root")
        text = self.c.chat("show me the finance report").text
        self.assertIn("Revenue: $4.99 from 1 paid orders", text)

    def test_answers_grow_with_user_level(self):
        self.assertIn("No information", self.c.chat("what is my balance").text)
        makeCustomer(self.c, "mia", 100)
        loginAs(self.c, "mia")
        self.assertIn("Balance: $100.00", self.c.chat("what is my balance").text)
        self.assertIn("No information", self.c.chat("how much have I saved").text)
        for _ in range(4):
            buy(self.c, 1)
        self.assertIn("saved you $0.00", self.c.chat("how much have I saved").text)
        self.assertIn("No information", self.c.chat("show the no-order list").text)

    def test_rag_answers_locally_and_says_so(self):
        r = self.c.chat("When does the store open?")
        self.assertEqual(r.source, "RAG")
        self.assertIn("9am to 6pm", r.text)
        self.assertIn("answered via RAG", r.text)

    def test_rag_answers_about_catalog(self):
        r = self.c.chat("Do you have Dracula?")
        self.assertEqual(r.source, "RAG")
        self.assertIn("Bram Stoker", r.text)

    def test_llm_used_when_not_local_and_says_so(self):
        srv, url = startFakeOllama()
        self.addCleanup(srv.shutdown)
        c = newController(LLMClient(url=url))
        r = c.chat("What is the capital of France?")
        self.assertEqual(r.source, "LLM")
        self.assertIn("Paris.", r.text)
        self.assertIn("answered by the LLM", r.text)

    def test_rag_with_llm_online_uses_context(self):
        srv, url = startFakeOllama()
        self.addCleanup(srv.shutdown)
        c = newController(LLMClient(url=url))
        r = c.chat("What are the opening hours?")
        self.assertEqual(r.source, "RAG")
        self.assertIn("CONTEXT-ANSWER", r.text)

    def test_offline_llm_gives_clear_message(self):
        r = self.c.chat("Explain quantum entanglement")
        self.assertEqual(r.source, "RULE")
        self.assertIn("offline", r.text)

    def test_mood_advisor_with_and_without_llm(self):
        r = self.c.chat("I'm bored, recommend me something")
        self.assertIn("bored mood", r.text)
        srv, url = startFakeOllama()
        self.addCleanup(srv.shutdown)
        c = newController(LLMClient(url=url))
        r = c.chat("recommend me a book, whatever")
        self.assertIn("sad mood", r.text)
        self.assertEqual(self.c.chat("recommend me something").text.startswith("Tell me a bit more"), True)

    def test_empty_message_ignored(self):
        self.assertEqual(self.c.chat("   ").text, "")


class AuthRules(unittest.TestCase):
    def setUp(self):
        self.c = newController()

    def test_register_validates_name_and_rolls_back_on_failed_training(self):
        for bad in ["ab", "has space", "x" * 30, ""]:
            with self.assertRaises(BookstoreError):
                self.c.register(bad, ["img"] * 12)
        self.c.register("nina", ["nina"] * 12)
        with self.assertRaises(BookstoreError):
            self.c.register("NINA", ["nina"] * 12)
        self.c.face.trainOk = False
        with self.assertRaises(BookstoreError):
            self.c.register("oscar", ["oscar"] * 12)
        self.assertIsNone(self.c.users.findByName("oscar"))
        with self.assertRaises(BookstoreError):
            self.c.register("pat")

    def test_registered_user_starts_as_rc_with_balance_and_can_login(self):
        u = self.c.register("quin", ["quin"] * 12)
        self.assertEqual((u.type, u.balance()), ("RC", 10.0))
        self.assertEqual(loginAs(self.c, "quin").userId, u.userId)

    def test_unknown_face_rejected(self):
        self.c.register("rae", ["rae"] * 12)
        with self.assertRaises(BookstoreError):
            self.c.login("face", "stranger")
        with self.assertRaises(BookstoreError):
            self.c.login("face", None)

    def test_only_one_super_user_via_setup(self):
        self.assertTrue(self.c.needsSetup())
        self.c.register("boss", ["boss"] * 12, userType="SU")
        self.assertFalse(self.c.needsSetup())
        with self.assertRaises(BookstoreError):
            self.c.register("boss2", ["boss2"] * 12, userType="SU")

    def test_su_cannot_buy(self):
        self.c.register("boss", ["boss"] * 12, userType="SU")
        loginAs(self.c, "boss")
        with self.assertRaises(BookstoreError):
            self.c.addToCart(1)

    def test_customer_cannot_use_admin(self):
        makeCustomer(self.c, "sam", 10)
        loginAs(self.c, "sam")
        for call in (lambda: self.c.financeReport(), lambda: self.c.tabooWords(), lambda: self.c.customers()):
            with self.assertRaises(BookstoreError):
                call()


if __name__ == "__main__":
    unittest.main()
