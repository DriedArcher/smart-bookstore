import os
from . import config


class FileStore:
    @staticmethod
    def path(rel):
        return config.DATA / rel

    @staticmethod
    def ensureDirs():
        for d in ["", "books", "faces", "voices", "models", "kb"]:
            (config.DATA / d).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize(text):
        return str(text).replace("|", " ").replace("\r", " ").replace("\n", " ")

    @staticmethod
    def readLines(rel):
        p = config.DATA / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            return []
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip():
                    rows.append(line.split("|"))
        return rows

    @staticmethod
    def writeLines(rel, rows):
        p = config.DATA / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for row in rows:
                f.write("|".join(FileStore.sanitize(x) for x in row) + "\n")
        os.replace(tmp, p)

    @staticmethod
    def appendLine(rel, fields):
        p = config.DATA / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write("|".join(FileStore.sanitize(x) for x in fields) + "\n")

    @staticmethod
    def nextId(rel):
        best = 0
        for row in FileStore.readLines(rel):
            try:
                best = max(best, int(row[0]))
            except ValueError:
                continue
        return best + 1

    @staticmethod
    def replaceLine(rel, key, newFields):
        rows = FileStore.readLines(rel)
        found = False
        for i, row in enumerate(rows):
            if row[0] == str(key):
                rows[i] = [str(x) for x in newFields]
                found = True
        if found:
            FileStore.writeLines(rel, rows)
        return found

    @staticmethod
    def deleteLine(rel, key):
        rows = FileStore.readLines(rel)
        keep = [r for r in rows if r[0] != str(key)]
        FileStore.writeLines(rel, keep)
        return len(keep) != len(rows)
