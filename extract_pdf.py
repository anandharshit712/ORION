import sys
try:
    from PyPDF2 import PdfReader
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2", "--quiet"])
    from PyPDF2 import PdfReader

pdf_path = r"c:\Users\anand\Downloads\AUTONOMOUS ROBUSTNESS EVALUATION PLATFORM (AREP)\Autonomous Driving Simulator Idea.pdf"
reader = PdfReader(pdf_path)
print(f"Total pages: {len(reader.pages)}")
print("=" * 80)

with open("pdf_extracted.txt", "w", encoding="utf-8") as f:
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        f.write(f"=== PAGE {i+1} ===\n")
        f.write(text if text else "(empty page)")
        f.write("\n\n")

print("Extracted to pdf_extracted.txt")
