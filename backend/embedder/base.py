from abc import ABC, abstractmethod
from typing import List

import numpy as np


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    def similarity(self, text_a: str, text_b: str) -> float:
        vec_a = np.array(self.embed_text(text_a))
        vec_b = np.array(self.embed_text(text_b))
        denom = np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
        if denom == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / denom)
