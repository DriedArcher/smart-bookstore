import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from smartbookstore import config, gui, seed
from smartbookstore.controller import SystemController
from smartbookstore.llm import LLMClient
from tests.helpers import FakeFace, FakeVoice

app = QApplication.instance() or QApplication([])
app.setStyleSheet(gui.STYLE)
gui.SYNC = True


def solid(path, code):
    cv2.imwrite(path, np.full((40, 40, 3), code, dtype=np.uint8))
    return path


class GuiFlow(unittest.TestCase):
    def setUp(self):
        self.msgs = []
        for kind in ("information", "warning", "critical"):
            setattr(QMessageBox, kind, staticmethod(lambda parent, title, text, k=kind: self.msgs.append((k, text))))
        self.files = []
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (self.files.pop(0) if self.files else "", ""))
        QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: (self.files, ""))
        d = tempfile.mkdtemp(prefix="bsgui_")
        config.set_data_dir(d)
        seed.seedIfEmpty()
        self.tmp = tempfile.mkdtemp(prefix="bsimg_")
        self.c = SystemController(face=FakeFace(), voice=FakeVoice(), llm=LLMClient(url="http://127.0.0.1:9"))
        self.win = gui.MainWindow(self.c)

    def enroll(self, name, code, userType):
        dlg = gui.EnrollDialog(self.win, userType)
        dlg.name.setText(name)
        self.files = [solid(os.path.join(self.tmp, f"{name}{i}.png"), code) for i in range(12)]
        dlg.addFaceFiles()
        self.assertEqual(len(dlg.faces), 12)
        dlg.submit()
        dlg.done(0)
        self.files = []

    def signIn(self, code):
        self.files = [solid(os.path.join(self.tmp, f"login{code}.png"), code)]
        self.win.pages["login"].faceFile()

    def test_first_run_goes_to_setup_then_full_customer_journey(self):
        self.assertEqual(self.win.current, "login")
        self.assertFalse(self.win.pages["login"].banner.isHidden())
        self.enroll("boss", 50, "SU")
        self.assertFalse(self.c.needsSetup())
        self.enroll("alex", 120, "RC")
        self.assertEqual(self.c.users.findByName("alex").balance(), 10.0)

        self.signIn(50)
        self.assertEqual(self.win.current, "home")
        self.assertEqual(self.c.user.type, "SU")
        self.assertFalse(self.win.buttons["admin"].isHidden())
        self.assertTrue(self.win.buttons["cart"].isHidden())
        admin = self.win.pages["admin"]
        self.win.go("admin")
        admin.fTitle.setText("GUI Book")
        admin.fAuthor.setText("Tester")
        admin.fCategory.setEditText("Humor")
        admin.fYear.setText("2020")
        admin.fPrice.setText("1.50")
        admin.addBook()
        self.assertIn(("information", "Book added."), self.msgs)
        admin.tabooInput.setText("grr")
        admin.addTaboo()
        self.assertIn("grr", self.c.tabooWords())
        self.win.toggleAuth()
        self.assertEqual(self.win.current, "home")
        self.assertTrue(self.win.buttons["admin"].isHidden())

        self.signIn(120)
        self.assertEqual(self.c.user.username, "alex")
        self.assertFalse(self.win.buttons["cart"].isHidden())
        self.assertTrue(self.win.buttons["admin"].isHidden())
        browse = self.win.pages["browse"]
        self.win.go("browse")
        browse.keywords.setText("dracula")
        browse.search()
        self.assertEqual(browse.table.rowCount(), 1)
        browse.table.selectRow(0)
        browse.openSelected()
        self.assertEqual(self.win.current, "book")
        book = self.win.pages["book"]
        book.addToCart()
        self.assertEqual(self.win.buttons["cart"].text(), "Cart (1)")
        book.text.setText("Great and also grr grr grr grr")
        book.post()
        self.assertTrue(any("blocked" in t.lower() for _, t in self.msgs))
        book.text.setText("Spooky and grr")
        book.post()
        self.assertIn("Spooky and ***", book.comments.toPlainText())

        self.win.go("cart")
        cart = self.win.pages["cart"]
        self.assertTrue(cart.checkoutBtn.isEnabled())
        cart.checkout()
        self.assertTrue(any("Order placed" in t for _, t in self.msgs))
        self.assertAlmostEqual(self.c.user.balance(), 5.51, places=2)

        self.win.go("account")
        self.assertEqual(self.win.pages["account"].table.rowCount(), 1)
        self.win.pages["account"].amount.setValue(20)
        self.win.pages["account"].topUp()
        self.assertAlmostEqual(self.c.user.balance(), 25.51, places=2)

        home = self.win.pages["home"]
        self.win.go("home")
        home.input.setText("when is the store open")
        home.send()
        self.assertIn("answered via RAG", home.log.toPlainText())
        home.input.setText("what is the revenue")
        home.send()
        self.assertIn("No information is available", home.log.toPlainText())

    def test_overdraft_suspends_and_returns_to_login(self):
        self.enroll("boss", 50, "SU")
        self.enroll("poor", 90, "RC")
        u = self.c.users.findByName("poor")
        u.account.balance = 0.5
        self.c.users.updateUser(u)
        self.signIn(90)
        self.c.addToCart(1)
        self.win.go("cart")
        self.win.pages["cart"].checkout()
        self.assertEqual(self.win.current, "login")
        self.assertEqual(self.c.user.userId, 0)
        self.msgs.clear()
        self.signIn(90)
        self.assertTrue(any("suspended" in t.lower() for _, t in self.msgs))
        self.signIn(50)
        self.win.go("admin")
        admin = self.win.pages["admin"]
        admin.users.selectRow([i for i in range(admin.users.rowCount()) if admin.users.item(i, 0).text() == "poor"][0])
        admin.deposit.setValue(10)
        admin.reopen()
        self.assertTrue(self.c.users.findByName("poor").isActive())

    def test_visitor_sees_limited_menu(self):
        self.enroll("boss", 50, "SU")
        self.win.go("home")
        for k in ("cart", "account", "admin"):
            self.assertTrue(self.win.buttons[k].isHidden())
        self.win.go("admin")
        self.assertEqual(self.win.current, "login")


if __name__ == "__main__":
    unittest.main()
