import zipfile
import xml.etree.ElementTree as ET

def extract():
    try:
        z = zipfile.ZipFile('../ORION_Design_Guide.docx')
        tree = ET.fromstring(z.read('word/document.xml'))
        text = ''.join(node.text for node in tree.iter() if node.text)
        with open('design_guide.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print("Extraction successful.")
    except Exception as e:
        print(f"Error: {e}")

extract()
