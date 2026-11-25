import math
import re
from . import config

STOP = set("""a an the is are was were be been am do does did have has had i you he she it we they me my your our their
what when where who whom which why how can could would should will shall may might to of in on at for from by with about
into over under again further then once here there all any both each few more most other some such no nor not only own same
so than too very and or but if as until while this that these those please tell us""".split())


def keywords(text):
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and len(w) > 1]


def stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


class RAGEngine:
    def __init__(self, catalog=None):
        self.catalog = catalog

    def loadDocs(self):
        passages = []
        kb = config.DATA / "kb"
        if kb.exists():
            for f in sorted(kb.glob("*.txt")):
                text = f.read_text(encoding="utf-8")
                for para in re.split(r"\n\s*\n", text):
                    para = para.strip()
                    if para:
                        passages.append((f.name, para))
        if self.catalog is not None:
            for b in self.catalog.loadBooks():
                passages.append(("catalog", f"{b.title} by {b.author}. Category: {b.category}. Published {b.year}. "
                                            f"Price ${b.price:.2f}. {b.description}"))
        return passages

    def _tokens(self, text):
        return {stem(w) for w in keywords(text)}

    def isLocalQuestion(self, text):
        q = self._tokens(text)
        if not q:
            return False, []
        docs = self.loadDocs()
        toks = [self._tokens(p) for _, p in docs]
        n = len(docs)
        df = {}
        for t in toks:
            for w in t:
                df[w] = df.get(w, 0) + 1
        idf = {w: math.log((n + 1) / (df.get(w, 0) + 0.5)) + 1 for w in q}
        total = sum(idf.values())
        scored = []
        for (name, para), t in zip(docs, toks):
            hit = sum(idf[w] for w in q if w in t)
            scored.append((hit / total, name, para))
        scored.sort(key=lambda s: -s[0])
        if not scored or scored[0][0] < config.RAG_CUTOFF:
            return False, []
        return True, [(n_, p) for s, n_, p in scored[:3] if s >= config.RAG_CUTOFF * 0.6]

    def answerFromPassages(self, text, passages, llm):
        if llm is not None and llm.isOnline():
            context = "\n".join(p for _, p in passages)
            return llm.ask("Answer the question using only this context. Be brief.\nContext:\n" + context +
                           "\nQuestion: " + text)
        return passages[0][1]
