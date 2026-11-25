from . import config
from .covers import makeCover
from .filestore import FileStore
from .models import Book

BOOKS = [
    ("Pride and Prejudice", "Jane Austen", "Literature", 1813, 4.99, "Elizabeth Bennet and Mr. Darcy navigate pride, class and first impressions in Regency England."),
    ("Great Expectations", "Charles Dickens", "Literature", 1861, 5.49, "An orphan named Pip rises in society and learns what really matters."),
    ("Jane Eyre", "Charlotte Brontë", "Literature", 1847, 5.29, "A strong-willed governess finds love and mystery at Thornfield Hall."),
    ("Moby-Dick", "Herman Melville", "Literature", 1851, 6.99, "Captain Ahab's obsessive hunt for a white whale across the sea."),
    ("The Picture of Dorian Gray", "Oscar Wilde", "Literature", 1890, 3.99, "A young man's portrait ages while he stays young and drifts into vice."),
    ("Frankenstein", "Mary Shelley", "Horror", 1818, 3.99, "A scientist builds a living creature and cannot face what he has made."),
    ("Dracula", "Bram Stoker", "Horror", 1897, 4.49, "A group of friends races to stop an ancient vampire from reaching London."),
    ("Strange Case of Dr Jekyll and Mr Hyde", "Robert Louis Stevenson", "Horror", 1886, 2.99, "A respectable doctor discovers a potion that splits his personality in two."),
    ("The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "Mystery", 1892, 4.29, "Twelve short cases solved by the sharp-eyed detective of Baker Street."),
    ("The Hound of the Baskervilles", "Arthur Conan Doyle", "Mystery", 1902, 3.99, "Holmes investigates a family curse and a spectral hound on the moors."),
    ("The Moonstone", "Wilkie Collins", "Mystery", 1868, 4.79, "A stolen diamond sets off one of the first detective novels in English."),
    ("Treasure Island", "Robert Louis Stevenson", "Adventure", 1883, 3.79, "A boy finds a treasure map and sails with pirates to find the loot."),
    ("The Count of Monte Cristo", "Alexandre Dumas", "Adventure", 1844, 7.49, "A wrongly imprisoned sailor escapes and plans an elaborate revenge."),
    ("Around the World in Eighty Days", "Jules Verne", "Adventure", 1872, 3.49, "Phileas Fogg bets he can circle the globe in eighty days."),
    ("The Call of the Wild", "Jack London", "Adventure", 1903, 2.99, "A sled dog returns to his wild instincts in the Yukon gold rush."),
    ("The Jungle Book", "Rudyard Kipling", "Adventure", 1894, 3.29, "Mowgli grows up among wolves, a bear and a panther in the Indian jungle."),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", "Adventure", 1865, 2.99, "Alice follows a white rabbit into a strange world with its own logic."),
    ("Emma", "Jane Austen", "Romance", 1815, 4.79, "A confident young woman plays matchmaker and misreads her own heart."),
    ("Wuthering Heights", "Emily Brontë", "Romance", 1847, 4.59, "A stormy, destructive love story on the Yorkshire moors."),
    ("Persuasion", "Jane Austen", "Romance", 1817, 4.19, "Anne Elliot gets a second chance with the man she once turned down."),
    ("On the Origin of Species", "Charles Darwin", "Science", 1859, 6.49, "Darwin lays out the evidence for evolution by natural selection."),
    ("Relativity: The Special and General Theory", "Albert Einstein", "Science", 1916, 4.99, "Einstein explains his theories of relativity for a general reader."),
    ("The Time Machine", "H. G. Wells", "Science Fiction", 1895, 2.99, "An inventor travels far into the future and finds a divided humanity."),
    ("The War of the Worlds", "H. G. Wells", "Science Fiction", 1898, 3.49, "Martians invade Victorian England with machines no one can stop."),
    ("Twenty Thousand Leagues Under the Sea", "Jules Verne", "Science Fiction", 1870, 4.99, "Captain Nemo takes his captives on a tour of the ocean in the Nautilus."),
    ("Narrative of the Life of Frederick Douglass", "Frederick Douglass", "History", 1845, 3.99, "Douglass tells how he escaped slavery and became a leading voice for abolition."),
    ("The Autobiography of Benjamin Franklin", "Benjamin Franklin", "History", 1791, 3.99, "Franklin recounts his rise from a printer's apprentice to statesman and inventor."),
    ("Meditations", "Marcus Aurelius", "Philosophy", 180, 3.49, "Private notes from a Roman emperor on duty, calm and accepting what you cannot control."),
    ("The Prince", "Niccolò Machiavelli", "Philosophy", 1532, 2.99, "A short, blunt guide to winning and keeping political power."),
    ("Walden", "Henry David Thoreau", "Philosophy", 1854, 4.29, "Two years of simple living in a cabin by a pond, and what it taught him."),
    ("Leaves of Grass", "Walt Whitman", "Poetry", 1855, 4.49, "A sweeping collection celebrating the self, nature and democracy."),
    ("The Raven and Other Poems", "Edgar Allan Poe", "Poetry", 1845, 2.99, "Dark, musical poems about loss, grief and obsession."),
    ("The Importance of Being Earnest", "Oscar Wilde", "Humor", 1895, 2.99, "Two men invent fake identities and a comedy of mistaken names follows."),
    ("Three Men in a Boat", "Jerome K. Jerome", "Humor", 1889, 3.29, "Three friends and a dog take a disastrous boating holiday on the Thames."),
    ("The Adventures of Tom Sawyer", "Mark Twain", "Humor", 1876, 3.79, "A mischievous boy gets into trouble along the Mississippi."),
]

TABOO = ["darn", "heck", "crap", "stupid", "idiot", "jerk", "dumb", "sucks", "garbage", "loser"]

KB = {
    "store_info.txt": """Opening hours: The Smart Bookstore is open Monday to Friday from 9am to 6pm and on Saturday from 10am to 4pm. The store is closed on Sunday.

About the store: The Smart Bookstore is a small bookstore that sells classic public-domain books. It has an AI assistant, face and voice login, and a rating system where buyers' reviews count for more.

Browsing: Anyone can browse books by category, author or year, search by keywords, or search by uploading a picture of a cover.

Contact: For account problems such as a suspended account, ask the super user. The super user is the only person who can reopen a suspended account.""",
    "policies.txt": """Accounts: Registered customers keep a prepaid money balance in their account. New accounts start with a balance of $10.00. Customers can add money to an active account from the Account page.

Fines and suspension: If a purchase costs more than the account balance, the purchase is cancelled and a $1 fine is taken from the account. An account with a negative balance is suspended and cannot log in. Only the super user can reopen it, by depositing money so the balance is positive.

VIP customers: A registered customer who makes more than 3 purchases or pays more than $200 in total is promoted to VIP. VIP customers get a 10% discount on every purchase.

Comments and ratings: Anyone can rate a book from 1 to 5 stars and leave a comment. Comments from people who bought the book count double in the average rating.

Taboo words: Words on the taboo list are replaced with stars in comments. A comment with more than 3 taboo words is blocked and its author gets one warning. A registered customer with more than 2 warnings is suspended. A VIP customer who gets a warning is demoted to a regular customer and loses the discount.

Order lists: A book with more than 3 ratings and an average below 2 goes on the no-order list. A book with more than 3 ratings and an average above 4 goes on the to-order list.

Login: Registered customers, VIP customers and the super user log in with a face picture or a voice sample. Visitors do not need to log in but cannot buy books.""",
    "team.txt": """Team: The Smart Bookstore was built by a five-person student team for a software engineering course project. Edit this file to add the team members' names and roles.

Technology: The app is a local desktop program. Data is stored in text files. The chat assistant uses a free local language model through Ollama, and answers questions about the store from these local files first.""",
}


def seedIfEmpty():
    FileStore.ensureDirs()
    if not FileStore.readLines("books.txt"):
        for i, (title, author, cat, year, price, desc) in enumerate(BOOKS, start=1):
            rel = f"books/{i}_cover.png"
            makeCover(title, author, config.DATA / rel)
            FileStore.appendLine("books.txt", Book(i, title, author, cat, year, price, rel, "", "NORMAL", 0, 0, desc).toRow())
    if not FileStore.readLines("taboo.txt"):
        for w in TABOO:
            FileStore.appendLine("taboo.txt", [w])
    kb = config.DATA / "kb"
    if not list(kb.glob("*.txt")):
        for name, text in KB.items():
            (kb / name).write_text(text, encoding="utf-8")
