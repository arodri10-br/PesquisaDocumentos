import sys, importlib
mods = ["flask","flask_sqlalchemy","sqlalchemy","sentence_transformers","faiss","numpy","pdfplumber","pdf2image","pytesseract","pptx"]
print("Python:", sys.executable)
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"OK  {m:25} ->", getattr(mod,"__file__",None))
    except Exception as e:
        print(f"FAIL {m:25} ->", e)
