# Pesquisa de Documentos — Flask + SQLite + Embeddings

Gerenciador simples de documentos com **busca por nome**, **busca por conteúdo** e **busca semântica (IA)** usando embeddings.  
Interface web em Flask, persistência em SQLite e indexação de textos para consultas rápidas.

> Repositório: `arodri10-br/PesquisaDocumentos`

---

## ✨ Funcionalidades

- **Dashboard** com estatísticas de documentos.
- **Escanear pasta** e registrar arquivos no banco (sem indexar o conteúdo).
- **Indexação**: extrai texto, gera embeddings e marca status como `indexed`.
- **Busca**:
  - **Por nome do arquivo** (`filename`).
  - **Por conteúdo** (`content_text`, LIKE no SQLite).
  - **Semântica (IA)** com embeddings e FAISS (similaridade de cosseno).
- **Estrutura de pastas** navegável.
- **Visualização** de documento (metadados e trecho do conteúdo).
- **API**: `GET /api/documents` lista documentos em JSON.
- **Chat RAG (demo)**: usa busca vetorial para montar um contexto de resposta.

Rotas principais:
- `/` — Dashboard
- `/scan_folder` — Escanear uma pasta e cadastrar arquivos
- `/index_documents` — Indexar pendentes (extrair texto + embeddings)
- `/documents` — Listagem com paginação e filtro por status
- `/search` — Formulário de busca (nome, conteúdo, semântica)
- `/folder_structure` — Árvore de diretórios
- `/rag_chat` — Exemplo de RAG
- `/api/documents` — API (JSON)

---

## 🧱 Arquitetura (resumo)

- **Flask** (`app.py`) para as rotas e templates (`templates/`).
- **Flask‑SQLAlchemy** para modelos:
  - `Document`: metadados do arquivo + `content_text` + `embeddings` (JSON) + `status`.
  - `SearchQuery`: histórico de buscas.
- **`document_processor.py`**: extrai conteúdo conforme tipo (PDF, DOCX etc.).
- **`search_engine.py`**: cria embeddings e executa busca vetorial (FAISS).

> Banco padrão: `sqlite:///documents.db` (arquivo na raiz do projeto).

---

## ✅ Requisitos

- **Python 3.10+** (recomendado 3.11)
- Git (opcional, para clonar o repositório)
- Pacotes Python (instalados via `pip`):
  - `Flask`, `Flask-SQLAlchemy`
  - `sentence-transformers`
  - `faiss-cpu`  *(em Windows/Linux/macOS via pip)*
  - `numpy`
  - (opcional) bibliotecas para extração de texto: `python-docx`, `PyPDF2`, `pdfminer.six`, etc.

> Dica: se estiver em Windows, certifique-se de que o `pip` do seu ambiente virtual está atual e que você está usando `faiss-cpu` (não `faiss` puro).

---

## 🧪 Subir um ambiente virtual (venv)

### Windows (PowerShell)

```powershell
# dentro da pasta do projeto
py -3.11 -m venv .venv
.\.venv\Scripts\Activate

python -m pip install --upgrade pip
pip install -r requirements.txt  # se existir
# ou instale manualmente (exemplo):
pip install Flask Flask-SQLAlchemy sentence-transformers faiss-cpu numpy
```

### Linux / macOS

```bash
# dentro da pasta do projeto
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt  # se existir
# ou instale manualmente (exemplo):
pip install Flask Flask-SQLAlchemy sentence-transformers faiss-cpu numpy
```

> Para sair do ambiente virtual: `deactivate`

---

## ⚙️ Configuração do modelo de embeddings

Este projeto usa **Sentence-Transformers**. Recomendação para PT‑BR:
- `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões; rápido e robusto).

No código, instancie assim (exemplo):
```python
search_engine = SearchEngine(model_name="paraphrase-multilingual-MiniLM-L12-v2")
```

> **Importante:** o **mesmo modelo** deve ser usado **tanto para indexar** quanto para **consultar**. Trocar o modelo exige **reindexação** (veja abaixo).

---

## ▶️ Como rodar o projeto (dev)

1. **Ative o venv** (veja seção acima) e instale dependências.
2. Inicialize o banco (o `create_all()` já está no `app.py`):
   ```bash
   python app.py
   ```
   Acesse: `http://127.0.0.1:5000/`

3. **Escanear uma pasta** (menu **Escanear Pasta**) para popular a tabela `Document`.
4. **Indexar** (abra `/index_documents`) para extrair conteúdo e gerar embeddings.
5. **Buscar** (menu **Buscar**), escolhendo o tipo de busca.
6. **RAG (demo)**: acesse **Chat RAG** e faça uma pergunta.

---

## 🔁 Reindexar documentos (quando trocar o modelo ou extrator)

Se você alterou o modelo de embeddings ou a forma de extração de texto:

1. **Zere embeddings e marque como `pending`**  
   Via SQL:
   ```sql
   UPDATE document
      SET embeddings = NULL,
          status = 'pending',
          indexed_date = NULL;
   ```
   ou via script Python dentro do app context.

2. **Reindexe** acessando `/index_documents` novamente.

3. **Teste** a busca semântica. Se usar FAISS, não deve aparecer erro de dimensão.

---

## 🧰 Dicas / Troubleshooting

- **`AssertionError: d == self.d` em FAISS**  
  Dimensão do vetor de consulta diferente da dimensão do índice. Reindexe **tudo** com o **mesmo modelo** que será usado nas consultas.

- **`IntegrityError: NOT NULL constraint failed: search_query.query_text`**  
  Evite salvar consultas vazias. Valide `query_text` no backend antes de persistir.

- **`hasattr` em Jinja**  
  Jinja não expõe `hasattr`. Use `doc|attr('similarity_score')` + `is defined` ou padronize o dicionário enviado ao template.

- **`The current Flask app is not registered with this 'SQLAlchemy' instance`**  
  Não crie `SQLAlchemy()` fora do app. Passe sempre `db.session` e a classe `Document` para funções/serviços externos.

---

## 📦 Requirements (exemplo)

Se você ainda não tem um `requirements.txt`, gere um de base após instalar os pacotes:

```txt
Flask>=2.3
Flask-SQLAlchemy>=3.1
sentence-transformers>=3.0
faiss-cpu>=1.8
numpy>=1.26
# opcionalmente:
# PyPDF2>=3.0
# python-docx>=1.1
# pdfminer.six>=20240706
```

> Ajuste versões conforme seu ambiente. Depois de tudo instalado:  
> `pip freeze > requirements.txt`

---

## 📁 Estrutura sugerida

```
.
├── app.py
├── document_processor.py
├── search_engine.py
├── documents.db
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── scan_folder.html
│   ├── documents.html
│   ├── search.html
│   ├── search_results.html
│   ├── folder_structure.html
│   ├── rag_chat.html
│   └── document_detail.html
├── static/           # (css/js/img opcionais)
└── requirements.txt  # (recomendado)
```

---

## 🔐 Observações

- O `secret_key` do Flask está em código para ambiente de dev. Em produção, use variável de ambiente.
- Caso processe conteúdos sensíveis, considere isolar o ambiente (rede e storage) e controlar o cache de modelos (`HF_HOME`).

---

## 🤝 Contribuições

1. Faça um fork do repositório.
2. Crie uma branch: `git checkout -b feature/nome-da-feature`.
3. Commit: `git commit -m "feat: descreva sua mudança"`.
4. Push: `git push origin feature/nome-da-feature`.
5. Abra um Pull Request.

---

## 📜 Licença

Defina a licença do projeto (por exemplo, MIT). Se ainda não houver um arquivo `LICENSE`, considere adicioná-lo.
