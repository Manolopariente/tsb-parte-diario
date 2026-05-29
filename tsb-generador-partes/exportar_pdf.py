"""
TSB · Generador de Partes — Exportador PDF
==========================================
1. Convierte Excel a PDF via LibreOffice
2. Agrega firma al pie con PyMuPDF
   - Nombre supervisor (bold)
   - "Compañia TSB" (italic)
"""

import subprocess, os, shutil
import fitz  # PyMuPDF

def _ocultar_hoja_datos(src, dst):
    """Oculta la hoja Datos y actualiza Print_Area dinámico antes de exportar."""
    import zipfile, re
    from lxml import etree
    NS_WB = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist()}
    
    # Calcular última fila con datos en Parte Diario
    sheet = etree.fromstring(files['xl/worksheets/sheet1.xml'])
    rows = [int(r.get('r',0)) for r in sheet.findall(f".//{{{NS_WB}}}row")]
    ultima_fila = max(rows) if rows else 70
    print(f"  Última fila detectada: {ultima_fila}")
    
    # Actualizar Print_Area en workbook.xml
    wb = etree.fromstring(files['xl/workbook.xml'])
    dn_el = wb.find(f"{{{NS_WB}}}definedNames")
    if dn_el is None:
        dn_el = etree.SubElement(wb, f"{{{NS_WB}}}definedNames")
    updated = False
    for dn in dn_el.findall(f"{{{NS_WB}}}definedName"):
        if dn.get('name') == '_xlnm.Print_Area':
            dn.text = f"'Parte Diario'!$A$1:$Z${ultima_fila}"
            updated = True
            break
    if not updated:
        dn_new = etree.SubElement(dn_el, f"{{{NS_WB}}}definedName")
        dn_new.set('name', '_xlnm.Print_Area')
        dn_new.set('localSheetId', '0')
        dn_new.text = f"'Parte Diario'!$A$1:$Z${ultima_fila}"
    
    # Ocultar hoja Datos
    for sh in wb.findall(f".//{{{NS_WB}}}sheet"):
        if sh.get('name') == 'Datos':
            sh.set('state', 'hidden')
    
    files['xl/workbook.xml'] = etree.tostring(
        wb, xml_declaration=True, encoding='UTF-8', standalone=True
    )
    
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)


def exportar_pdf(xlsx_path, supervisor, yacimiento, output_path=None):
    """
    Exporta el parte diario a PDF con firma al pie.
    
    Args:
        xlsx_path: ruta al Excel generado
        supervisor: nombre del supervisor (ej: "MESA GONZALO NICOLAS")
        yacimiento: "PHZ" | "SP" | "CHSN"
        output_path: ruta de salida del PDF (opcional)
    
    Returns:
        ruta del PDF generado
    """
    # Definir nombre de salida
    if output_path is None:
        base = os.path.splitext(xlsx_path)[0]
        output_path = base + ".pdf"
    
    tmp_dir = "/tmp/tsb_pdf_export"
    os.makedirs(tmp_dir, exist_ok=True)
    
    # 1. Preparar Excel con hoja Datos oculta (solo exporta Parte Diario)
    xlsx_tmp = os.path.join(tmp_dir, "parte_export.xlsx")
    _ocultar_hoja_datos(xlsx_path, xlsx_tmp)

    # 2. Convertir a PDF con LibreOffice
    print(f"Exportando PDF via LibreOffice...")
    result = subprocess.run([
        "libreoffice", "--headless", "--convert-to", "pdf",
        "--outdir", tmp_dir,
        xlsx_tmp
    ], capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        raise Exception(f"LibreOffice error: {result.stderr}")
    
    # Encontrar el PDF generado
    base_name = os.path.splitext(os.path.basename(xlsx_tmp))[0]
    pdf_tmp = os.path.join(tmp_dir, base_name + ".pdf")
    
    if not os.path.exists(pdf_tmp):
        raise Exception(f"PDF no encontrado en {tmp_dir}")
    
    print(f"✅ PDF generado: {pdf_tmp}")
    
    # 2. Agregar firma con PyMuPDF
    print(f"Agregando firma: {supervisor}...")
    pdf_con_firma = agregar_firma(pdf_tmp, supervisor)
    
    # 3. Copiar a destino final
    shutil.copy2(pdf_con_firma, output_path)
    
    # Limpiar tmp
    os.remove(pdf_tmp)
    if pdf_con_firma != pdf_tmp:
        os.remove(pdf_con_firma)
    
    print(f"✅ PDF final: {output_path}")
    return output_path


def agregar_firma(pdf_path, supervisor):
    """
    Agrega firma al pie de la última página del PDF.
    Formato:
        [Nombre Supervisor]  ← bold
        Compañia TSB         ← regular
    Posición: esquina inferior derecha
    """
    doc = fitz.open(pdf_path)
    ultima_pagina = doc[-1]
    
    page_rect = ultima_pagina.rect
    page_width  = page_rect.width
    page_height = page_rect.height
    
    # Formatear nombre del supervisor (Title Case)
    nombre_display = supervisor.title()
    
    # Dimensiones del bloque de firma
    font_size_nombre = 10
    font_size_empresa = 9
    
    # Posición: esquina inferior derecha, margen 30pt
    x_derecha = page_width - 30
    y_base = page_height - 70   # línea base de "Compañia TSB" (más arriba)
    y_nombre = y_base - 16      # línea nombre arriba
    # Calcular ancho del texto para alinear a la derecha
    # (aproximado — PyMuPDF no tiene getTextWidth fácil, usamos 6pt por char)
    ancho_nombre  = len(nombre_display)  * 5.5
    ancho_empresa = len("Compañia TSB")  * 5.0
    ancho_max = max(ancho_nombre, ancho_empresa)
    
    x_inicio = x_derecha - ancho_max
    
    # Nombre supervisor — bold
    ultima_pagina.insert_text(
        fitz.Point(x_inicio, y_nombre),
        nombre_display,
        fontsize=font_size_nombre,
        fontname="hebo",   # Helvetica Bold
        color=(0, 0, 0)
    )
    
    # Compañia TSB — regular
    ultima_pagina.insert_text(
        fitz.Point(x_inicio, y_base),
        "Compañia TSB",
        fontsize=font_size_empresa,
        fontname="helv",   # Helvetica
        color=(0, 0, 0)
    )
    
    # Guardar con firma
    out_path = pdf_path.replace(".pdf", "_firmado.pdf")
    doc.save(out_path)
    doc.close()
    
    return out_path


# TEST
if __name__ == "__main__":
    xlsx = "/home/claude/tsb_generador/4900100500_26052026_PD_PHZ_v3.xlsx"
    output = "/home/claude/tsb_generador/4900100500_26052026_PD_PHZ_v3.pdf"
    
    exportar_pdf(
        xlsx_path=xlsx,
        supervisor="MESA GONZALO NICOLAS",
        yacimiento="PHZ",
        output_path=output
    )
