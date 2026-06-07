from abc import ABC, abstractmethod
from typing import List
import numpy as np

class BaseEmbedder(ABC):

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    def similarity(self, text_a: str, text_b: str) -> float:
        vec_a = np.array(self.embed_text(text_a))
        vec_b = np.array(self.embed_text(text_b))
        return float(
            np.dot(vec_a, vec_b) /
            (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        )