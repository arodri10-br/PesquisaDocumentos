import json
import re
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class SearchEngine:
    """
    Engine de embeddings + FAISS, desacoplado do app.
    - NÃO importa db nem models do app.
    - Recebe db.session e a classe Document por parâmetro.
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.doc_ids: list[int] = []
        self.dim = None
        self._built = False

    # -----------------------
    # Embeddings
    # -----------------------
    def _encode(self, texts):
        # normaliza L2 -> pronto para cos_sim (e IP com vetores normalizados)
        return self.model.encode(texts, normalize_embeddings=True)

    def create_embeddings(self, text: str):
        if not text or not text.strip():
            return None
        try:
            vec = self._encode([text])[0]
            return vec  # np.ndarray float32
        except Exception as e:
            print(f"Erro ao criar embeddings: {e}")
            return None

    # -----------------------
    # Índice FAISS
    # -----------------------
    def reset_index(self):
        self.index = None
        self.doc_ids = []
        self.dim = None
        self._built = False

    def build_index(self, session, DocumentModel):
        docs = (
            session.query(DocumentModel)
            .filter(DocumentModel.status == 'indexed')
            .filter(DocumentModel.embeddings.isnot(None))
            .all()
        )
        vecs, ids = [], []
        for d in docs:
            try:
                emb = d.embeddings
                if isinstance(emb, str):
                    emb = np.array(json.loads(emb), dtype=np.float32)
                else:
                    emb = np.array(emb, dtype=np.float32)
                if emb.ndim == 1:
                    vecs.append(emb)
                    ids.append(d.id)
            except Exception:
                pass

        if not vecs:
            self.reset_index()
            return

        mat = np.vstack(vecs).astype('float32')
        self.dim = mat.shape[1]
        faiss.normalize_L2(mat)

        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(mat)
        self.doc_ids = ids
        self._built = True

    # -----------------------
    # Busca
    # -----------------------
    def vector_search(self, query_text: str, session, DocumentModel, limit: int = 10):
        """Retorna lista de Document com atributo .similarity_score (0..1)."""
        if not query_text or not query_text.strip():
            return []

        if self.index is None or not self._built or self.index.ntotal == 0:
            self.build_index(session, DocumentModel)

        if self.index is None or self.index.ntotal == 0:
            return []

        q = self.create_embeddings(query_text)
        if q is None:
            return []

        q = np.array([q], dtype=np.float32)
        faiss.normalize_L2(q)

        if self.dim is not None and q.shape[1] != self.dim:
            # Dimensão do embedding difere do índice (modelo mudou)
            print(f"[search_engine] Dimensão consulta {q.shape[1]} != índice {self.dim}. Reindexe com o mesmo modelo.")
            return []

        k = min(limit, self.index.ntotal)
        scores, idxs = self.index.search(q, k)

        out = []
        for score, idx in zip(scores[0], idxs[0]):
            if 0 <= idx < len(self.doc_ids):
                doc_id = self.doc_ids[idx]
                doc = session.get(DocumentModel, doc_id)
                if doc is not None:
                    try:
                        doc.similarity_score = float(score)
                    except Exception:
                        doc.similarity_score = None
                    out.append(doc)
        return out

    # -----------------------
    # Snippet relevante (opcional)
    # -----------------------
    def find_relevant_snippet(self, query_text: str, document_text: str, max_length: int = 300) -> str:
        if not document_text or not query_text:
            return document_text[:max_length] if document_text else ""

        sentences = re.split(r'[.!?]+', document_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return document_text[:max_length]

        qv = self.create_embeddings(query_text)
        if qv is None:
            return document_text[:max_length]

        best = ("", -1.0)
        for i in range(len(sentences)):
            end = min(i + 3, len(sentences))
            snippet = ". ".join(sentences[i:end])
            if len(snippet) > max_length:
                snippet = snippet[:max_length] + "..."
            sv = self.create_embeddings(snippet)
            if sv is not None:
                denom = (np.linalg.norm(qv) * np.linalg.norm(sv)) or 1.0
                sim = float(np.dot(qv, sv) / denom)
                if sim > best[1]:
                    best = (snippet, sim)
        return best[0] or document_text[:max_length]
