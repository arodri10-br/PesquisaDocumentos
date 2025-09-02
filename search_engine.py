import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class SearchEngine:
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Use um modelo SBERT pronto para sentenças em PT para evitar o aviso:
        'No sentence-transformers model found ... Creating a new one with mean pooling.'
        Se quiser manter o neuralmind/bert-base-portuguese-cased, passe o nome no model_name.
        """
        self.model = SentenceTransformer(model_name)
        self.index = None            # faiss.IndexFlatIP
        self.doc_ids = []            # lista de IDs (ordem alinhada ao índice)
        self.dim = None              # dimensão dos embeddings
        self._built = False          # flag simples de construção

    # ---------- Embeddings util ----------
    def _encode(self, texts):
        # normalize_embeddings=True deixa prontos p/ cosseno (e p/ IP com normalização)
        return self.model.encode(texts, normalize_embeddings=True)

    def create_embeddings(self, text: str):
        """Cria embedding (np.ndarray) para um texto, já normalizado."""
        if not text or not text.strip():
            return None
        try:
            vec = self._encode([text])[0]
            return vec  # np.ndarray (float32)
        except Exception as e:
            print(f"Erro ao criar embeddings: {e}")
            return None

    # ---------- Indexação ----------
    def reset_index(self):
        """Reseta o índice FAISS (chame após grandes mudanças de base)."""
        self.index = None
        self.doc_ids = []
        self.dim = None
        self._built = False

    def build_index(self, session, DocumentModel):
        """
        Constrói o índice FAISS a partir dos documentos 'indexed' com embeddings.
        NÃO importa o db/app; usa apenas a session e o modelo recebidos.
        """
        docs = (
            session.query(DocumentModel)
            .filter(DocumentModel.status == 'indexed')
            .filter(DocumentModel.embeddings.isnot(None))
            .all()
        )
        if not docs:
            self.reset_index()
            return

        vectors = []
        ids = []
        for d in docs:
            try:
                emb = d.embeddings
                if isinstance(emb, str):
                    emb = np.array(json.loads(emb), dtype=np.float32)
                else:
                    emb = np.array(emb, dtype=np.float32)
                if emb.ndim != 1:
                    continue
                vectors.append(emb)
                ids.append(d.id)
            except Exception:
                continue

        if not vectors:
            self.reset_index()
            return

        mat = np.vstack(vectors).astype('float32')   # shape: (n_docs, dim)
        self.dim = mat.shape[1]

        # Normaliza L2 para usar Inner Product como similaridade de cosseno
        faiss.normalize_L2(mat)

        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(mat)
        self.doc_ids = ids
        self._built = True

    # ---------- Busca ----------
    def vector_search(self, query_text: str, session, DocumentModel, limit: int = 10):
        """
        Busca semântica usando FAISS. Retorna lista de Document com atributo .similarity_score (0..1).
        """
        if not query_text or not query_text.strip():
            return []

        # Constrói (ou reconstrói) sob demanda se ainda não existir
        if self.index is None or not self._built or self.index.ntotal == 0:
            self.build_index(session, DocumentModel)

        if self.index is None or self.index.ntotal == 0:
            return []

        q = self.create_embeddings(query_text)
        if q is None:
            return []

        q = np.array([q], dtype=np.float32)  # (1, dim)
        faiss.normalize_L2(q)

        k = min(limit, self.index.ntotal)
        scores, idxs = self.index.search(q, k)  # scores: (1, k), idxs: (1, k)

        out = []
        for score, idx in zip(scores[0], idxs[0]):
            if 0 <= idx < len(self.doc_ids):
                doc_id = self.doc_ids[idx]
                doc = session.get(DocumentModel, doc_id)
                if doc is not None:
                    # Como usamos IP com vetores normalizados, o score já é cos_sim (0..1)
                    try:
                        doc.similarity_score = float(score)
                    except Exception:
                        doc.similarity_score = None
                    out.append(doc)

        return out

    def semantic_search(self, query_text: str, documents, limit: int = 10):
        """
        Variante simples sem FAISS: calcula cos_sim contra embeddings salvos em 'documents'.
        Cada doc deve ter .embeddings (JSON list ou np-array-like).
        """
        if not documents:
            return []

        q = self.create_embeddings(query_text)
        if q is None:
            return []

        results = []
        for d in documents:
            emb = getattr(d, 'embeddings', None)
            if not emb:
                continue
            try:
                if isinstance(emb, str):
                    emb = np.array(json.loads(emb), dtype=np.float32)
                else:
                    emb = np.array(emb, dtype=np.float32)

                # cos_sim(q, emb) com normalização explícita
                denom = (np.linalg.norm(q) * np.linalg.norm(emb))
                if denom == 0:
                    sim = 0.0
                else:
                    sim = float(np.dot(q, emb) / denom)

                d.similarity_score = sim
                results.append(d)
            except Exception:
                continue

        results.sort(key=lambda x: (x.similarity_score or 0.0), reverse=True)
        return results[:limit]
