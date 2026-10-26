"""Модуль лексического поиска по каталогу расценок (Okapi BM25).

Реализует токенизацию русскоязычного текста, стемминг/нормализацию и ранжирование
релевантности расценок по ключевым словам и фразам.
"""
import math
import re
from typing import Sequence
from app.rag.schemas import RateItem

# Регулярное выражение для извлечения слов (русские и латинские буквы, цифры)
WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")

# Базовые русские стоп-слова, исключаемые из поискового индекса
STOP_WORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все",
    "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по",
    "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из",
    "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или",
    "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам",
    "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где",
    "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб",
    "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда",
    "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь",
    "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда",
    "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой",
    "хоть", "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего",
}


def tokenize(text: str) -> list[str]:
    """Токенизирует текст, приводит к нижнему регистру и нормализует окончания (простой стемминг)."""
    words = WORD_RE.findall(text.lower())
    tokens = []
    for w in words:
        if w in STOP_WORDS or len(w) < 2:
            continue
        # Простой псевдо-стемминг для русского языка (отсечение типичных окончаний)
        stemmed = re.sub(r"(ами|ями|ов|ев|ей|ам|ям|ом|ем|ой|ей|ью|а|я|о|е|ы|и|у|ю|ый|ий|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ым|им|ых|их)$", "", w)
        tokens.append(stemmed if len(stemmed) >= 2 else w)
    return tokens


class BM25SearchEngine:
    """Поисковый движок Okapi BM25 для каталога расценок."""

    def __init__(
        self,
        rates: Sequence[RateItem],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.rates = list(rates)
        self.corpus_size = len(self.rates)

        # Индексирование документов
        self.doc_tokens: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.doc_freqs: dict[str, int] = {}

        for rate in self.rates:
            # Текст документа включает наименование, описание, ключевые слова и код
            doc_text = f"{rate.work_name} {rate.description} {' '.join(rate.keywords)} {rate.rate_code}"
            tokens = tokenize(doc_text)
            self.doc_tokens.append(tokens)
            self.doc_lengths.append(len(tokens))

            unique_tokens = set(tokens)
            for token in unique_tokens:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        self.avg_doc_len = (
            sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 1.0
        )

    def _idf(self, token: str) -> float:
        """Расчёт Inverse Document Frequency (сглаженный)."""
        df = self.doc_freqs.get(token, 0)
        return math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 5) -> list[tuple[RateItem, float]]:
        """Выполняет поиск расценок по запросу и возвращает отсортированный список (расценка, score)."""
        query_tokens = tokenize(query)
        if not query_tokens or self.corpus_size == 0:
            return []

        scores: list[float] = [0.0] * self.corpus_size

        for token in query_tokens:
            idf = self._idf(token)
            for idx, doc in enumerate(self.doc_tokens):
                tf = doc.count(token)
                if tf == 0:
                    continue
                doc_len = self.doc_lengths[idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[idx] += idf * (numerator / denominator)

        # Сортировка по убыванию релевантности
        ranked = [
            (self.rates[idx], score)
            for idx, score in enumerate(scores)
            if score > 0.0
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
