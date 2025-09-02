from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json
from document_processor import DocumentProcessor
from search_engine import SearchEngine

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///documents.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'seu-secret-key-aqui'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

db = SQLAlchemy(app)

# Modelos
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False, unique=True)
    file_type = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer)
    created_date = db.Column(db.DateTime)
    modified_date = db.Column(db.DateTime)
    indexed_date = db.Column(db.DateTime)
    content_text = db.Column(db.Text)
    embeddings = db.Column(db.Text)  # JSON string dos embeddings
    status = db.Column(db.String(20), default='pending')  # pending, indexed, error
    folder_path = db.Column(db.String(500))
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'filepath': self.filepath,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'created_date': self.created_date.isoformat() if self.created_date else None,
            'modified_date': self.modified_date.isoformat() if self.modified_date else None,
            'indexed_date': self.indexed_date.isoformat() if self.indexed_date else None,
            'status': self.status,
            'folder_path': self.folder_path
        }

class SearchQuery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query_text = db.Column(db.Text, nullable=False)
    search_type = db.Column(db.String(20))  # filename, content, vector
    results_count = db.Column(db.Integer)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

# Inicializar processadores
document_processor = DocumentProcessor()
#search_engine = SearchEngine()
search_engine = SearchEngine(model_name="paraphrase-multilingual-MiniLM-L12-v2")

@app.route('/')
def index():
    stats = {
        'total_docs': Document.query.count(),
        'indexed_docs': Document.query.filter_by(status='indexed').count(),
        'pending_docs': Document.query.filter_by(status='pending').count(),
        'error_docs': Document.query.filter_by(status='error').count()
    }
    recent_docs = Document.query.order_by(Document.indexed_date.desc()).limit(10).all()
    return render_template('index.html', stats=stats, recent_docs=recent_docs)

@app.route('/scan_folder', methods=['GET', 'POST'])
def scan_folder():
    if request.method == 'POST':
        folder_path = request.form.get('folder_path')
        if folder_path and os.path.exists(folder_path):
            count = document_processor.scan_folder(folder_path, db)
            return jsonify({'success': True, 'message': f'{count} documentos encontrados e adicionados ao banco.'})
        else:
            return jsonify({'success': False, 'message': 'Caminho da pasta inválido.'})
    
    return render_template('scan_folder.html')

@app.route('/documents')
def documents():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = Document.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    documents = query.paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('documents.html', documents=documents, status_filter=status_filter)

@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        # 1) Normalize
        query_text = (request.form.get('query') or '').strip()
        search_type = (request.form.get('search_type') or 'filename').strip()

        # 2) Validação: não prossiga nem salve se vazio
        if not query_text:
            # opcional: flash exige um bloco para mostrar no template base
            flash('Digite um termo de busca.', 'warning')
            return render_template('search.html')

        # 3) Executa a busca
        if search_type == 'filename':
            results = Document.query.filter(
                Document.filename.contains(query_text)
            ).all()
        elif search_type == 'content':
            results = Document.query.filter(
                Document.content_text.contains(query_text)
            ).all()
        elif search_type == 'vector':
            results = search_engine.vector_search(query_text, db.session, Document, limit=12)
        else:
            results = []

        # 4) Persiste a consulta só se houver query_text válido
        try:
            search_query = SearchQuery(
                query_text=query_text,
                search_type=search_type,
                results_count=len(results)
            )
            db.session.add(search_query)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # log opcional
            app.logger.exception("Falha ao salvar SearchQuery")
            # Não derrube a página de resultado por causa do log
            # (se preferir, pode exibir um aviso)
            # flash('Não foi possível registrar a consulta no histórico.', 'danger')

        # 5) Render
        return render_template(
            'search_results.html',
            results=results,
            query=query_text,
            search_type=search_type
        )

    # GET
    return render_template('search.html')

@app.route('/index_documents')
def index_documents():
    pending_docs = Document.query.filter_by(status='pending').all()
    indexed_count = 0
    
    for doc in pending_docs:
        try:
            content = document_processor.extract_content(doc.filepath, doc.file_type)
            embeddings = search_engine.create_embeddings(content)
            
            doc.content_text = content
            doc.embeddings = json.dumps(embeddings.tolist()) if embeddings is not None else None
            doc.status = 'indexed'
            doc.indexed_date = datetime.utcnow()
            
            indexed_count += 1
        except Exception as e:
            doc.status = 'error'
            print(f"Erro ao indexar {doc.filepath}: {str(e)}")
    
    db.session.commit()
    return jsonify({'success': True, 'message': f'{indexed_count} documentos indexados com sucesso.'})

@app.route('/folder_structure')
def folder_structure():
    folder_paths = db.session.query(Document.folder_path).distinct().all()
    folder_structure = {}
    
    for (folder_path,) in folder_paths:
        if folder_path:
            parts = folder_path.split(os.sep)
            current = folder_structure
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
    
    return render_template('folder_structure.html', folder_structure=folder_structure)

@app.route('/rag_chat', methods=['GET', 'POST'])
def rag_chat():
    if request.method == 'POST':
        question = request.form.get('question')
        if question:
            # Busca por documentos relevantes
            embeddings = search_engine.create_embeddings(content)
            doc.embeddings = json.dumps(embeddings.tolist()) if embeddings is not None else None

            # Gera resposta baseada nos documentos
            context = '\n\n'.join([doc.content_text[:500] for doc in relevant_docs if doc.content_text])
            
            # Aqui você pode integrar com uma API de LLM como OpenAI GPT
            # Por enquanto, retornamos uma resposta simples
            answer = f"Baseado nos documentos encontrados:\n\n{context}\n\nPara uma resposta mais elaborada, integre com um modelo de linguagem."
            
            return render_template('rag_results.html', 
                                 question=question, 
                                 answer=answer, 
                                 relevant_docs=relevant_docs)
    
    return render_template('rag_chat.html')

@app.route('/document/<int:doc_id>')
def view_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return render_template('document_detail.html', document=doc)

@app.route('/api/documents')
def api_documents():
    documents = Document.query.all()
    return jsonify([doc.to_dict() for doc in documents])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)