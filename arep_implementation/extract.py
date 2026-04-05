import zipfile
import xml.etree.ElementTree as ET
import sys

def extract():
    z = zipfile.ZipFile('../autonomous_driving_simulation_platforms.docx')
    tree = ET.fromstring(z.read('word/document.xml'))
    text = ''.join(node.text for node in tree.iter() if node.text)
    with open('doc.txt', 'w', encoding='utf-8') as f:
        f.write(text)

extract()
