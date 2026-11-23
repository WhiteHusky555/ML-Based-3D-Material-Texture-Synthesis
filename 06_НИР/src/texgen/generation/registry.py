"""Публикация локальной версии и переключение между заданиями."""
import gc
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(os.environ.get("TEXGEN_MODELS", "/models"))


def model_path(root, version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", version):
        raise ValueError("Недопустимое имя версии")
    path = (root / version).resolve()
    if path.parent != root.resolve() or not path.is_dir():
        raise ValueError("Каталог версии недоступен")
    return path


def fingerprint(path):
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_symlink():
            raise ValueError("Символические ссылки в комплекте запрещены")
        if file.is_file():
            with file.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            digest.update(json.dumps([file.relative_to(path).as_posix(), checksum]).encode())
    return digest.hexdigest()


def publish(root, revision, version):
    if revision < 1:
        raise ValueError("Номер публикации должен быть положительным")
    item = dict(revision=revision, version=version, sha256=fingerprint(model_path(root, version)))
    # Неизменяемая публикация: конкурентная запись того же номера не затирает первую.
    target = root / f"publication-{revision}.json"
    with NamedTemporaryFile(dir=root, delete=False, mode="w", encoding="utf8") as stream:
        json.dump(item, stream)
    try:
        try:
            os.link(stream.name, target)
        except FileExistsError:
            if json.loads(target.read_text()) != item:
                raise ValueError("Номер публикации уже занят")
    finally:
        Path(stream.name).unlink()


class Registry:
    def __init__(self, root, loader):
        self.root = root
        self.loader = loader
        self.lock = threading.Lock()
        self.current = None
        self.provider = None
        self.seen = 0
        self.error = None

    def load(self, item):
        path = model_path(self.root, item["version"])
        if fingerprint(path) != item["sha256"]:
            raise ValueError("Изменился состав комплекта")
        return self.loader(path)

    def refresh(self):
        entries = sorted((int(p.stem[12:]), p) for p in self.root.glob("publication-*.json")
                         if p.stem[12:].isdigit())
        for revision, path in reversed(entries):
            if revision <= self.seen:
                break
            self.provider = None
            gc.collect()
            try:
                item = json.loads(path.read_text())
                if item["revision"] != revision:
                    raise ValueError("Номер публикации в файле не совпадает")
                self.provider = self.load(item)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Ошибка загрузки версии")
                self.error = type(exc).__name__
            else:
                self.current = item
                self.seen = entries[-1][0]
                if revision == self.seen:
                    self.error = None
                return
            if self.current:
                break
        if entries and entries[-1][0] > self.seen:
            self.seen = entries[-1][0]
            if self.current:
                try:
                    self.provider = self.load(self.current)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Ошибка восстановления модели")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", type=int)
    parser.add_argument("version")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    publish(args.root, args.revision, args.version)
