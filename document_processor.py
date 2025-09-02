import os
import json
import mimetypes
from datetime import datetime
from docx import Document as DocxDocument
from openpyxl import load_workbook
from pptx import Presentation
import PyPDF2
import pdfplumber
import pytesseract
from PIL import Image
import io

class DocumentProcessor:
    
    SUPPORTED_EXTENSIONS = {
        '.doc': 'doc',
        '.docx': 'docx',
        '.ppt': 'ppt', 
        '.pptx': 'pptx',
        '.xls': 'xls',
        '.xlsx': 'xlsx',
        '.pdf': 'pdf'
    }
    
    def scan_folder(self, folder_path, db):
        """Escaneia uma pasta e adiciona documentos ao banco de dados"""
        from app import Document
        
        count = 0
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext in self.SUPPORTED_EXTENSIONS:
                    # Verifica se já existe no banco
                    existing = Document.query.filter_by(filepath=file_path).first()
                    if not existing:
                        file_stats = os.stat(file_path)
                        
                        doc = Document(
                            filename=file,
                            filepath=file_path,
                            file_type=self.SUPPORTED_EXTENSIONS[file_ext],
                            file_size=file_stats.st_size,
                            created_date=datetime.fromtimestamp(file_stats.st_ctime),
                            modified_date=datetime.fromtimestamp(file_stats.st_mtime),
                            folder_path=root,
                            status='pending'
                        )
                        
                        db.session.add(doc)
                        count += 1
        
        db.session.commit()
        return count
    
    def extract_content(self, file_path, file_type):
        """Extrai conteúdo de texto do arquivo"""
        try:
            if file_type == 'docx':
                return self._extract_docx(file_path)
            elif file_type == 'doc':
                # Para arquivos .doc antigos, seria necessário usar python-docx2txt ou libreoffice
                return "Conteúdo não disponível para arquivos .doc antigos"
            elif file_type in ['xlsx', 'xls']:
                return self._extract_excel(file_path)
            elif file_type in ['pptx', 'ppt']:
                return self._extract_powerpoint(file_path)
            elif file_type == 'pdf':
                return self._extract_pdf(file_path)
            else:
                return ""
        except Exception as e:
            print(f"Erro ao extrair conteúdo de {file_path}: {str(e)}")
            return ""
    
    def _extract_docx(self, file_path):
        """Extrai texto de arquivos DOCX"""
        doc = DocxDocument(file_path)
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return '\n'.join(text)
    
    def _extract_excel(self, file_path):
        """Extrai texto de arquivos Excel"""
        wb = load_workbook(file_path, data_only=True)
        text = []
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            text.append(f"--- Planilha: {sheet_name} ---")
            
            for row in ws.iter_rows(values_only=True):
                row_text = []
                for cell in row:
                    if cell is not None:
                        row_text.append(str(cell))
                if row_text:
                    text.append('\t'.join(row_text))
        
        return '\n'.join(text)
    
    def _extract_powerpoint(self, file_path):
        """Extrai texto de arquivos PowerPoint"""
        prs = Presentation(file_path)
        text = []
        
        for i, slide in enumerate(prs.slides):
            text.append(f"--- Slide {i+1} ---")
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text.append(shape.text)
        
        return '\n'.join(text)
    
    def _extract_pdf(self, file_path):
        """Extrai texto de arquivos PDF"""
        text = []
        
        # Primeira tentativa: usar pdfplumber
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
        except:
            pass
        
        # Se não conseguiu texto, tenta PyPDF2
        if not text:
            try:
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text.append(page_text)
            except:
                pass
        
        # Se ainda não tem texto, pode ser um PDF com imagens - usar OCR
        if not text:
            try:
                import pdf2image
                images = pdf2image.convert_from_path(file_path)
                for image in images:
                    ocr_text = pytesseract.image_to_string(image, lang='por')
                    if ocr_text.strip():
                        text.append(ocr_text)
            except Exception as e:
                print(f"OCR falhou para {file_path}: {str(e)}")
        
        return '\n'.join(text)