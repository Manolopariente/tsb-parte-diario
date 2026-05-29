"""
TSB · Generador de Partes — Servidor Web
Flask app que sirve la UI y expone la API para el motor.
"""
from flask import Flask, send_from_directory, jsonify, request
import os, sys

app = Flask(__name__, static_folder='ui')

# Servir la UI
@app.route('/')
def index():
    return send_from_directory('ui', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('ui', path)

# API: generar parte
@app.route('/api/generar', methods=['POST'])
def generar():
    from motor_final import generar_parte, procesar_ots_pdf, EQUIPOS
    from exportar_pdf import exportar_pdf
    from motor_phz_original import completar_ot_pdf, preparar_firma
    from enviar_emails import enviar_parte_y_ots
    from datetime import date, datetime
    from pypdf import PdfWriter, PdfReader
    import tempfile, shutil

    data = request.json
    yac        = data['yacimiento']
    supervisor = data['supervisor']
    fecha_str  = data['fecha']  # YYYY-MM-DD
    fecha      = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    eq_dia     = data['equipos_activos']
    conductores= data.get('conductores', {})
    actividades= data.get('actividades', {})
    oncall     = data.get('oncall', {})
    ot_files   = data.get('ot_files', [])  # rutas temporales

    out_dir = os.path.join(os.path.dirname(__file__), 'outputs')
    os.makedirs(out_dir, exist_ok=True)

    ddmmyyyy = fecha.strftime('%d%m%Y')
    ddmmyy   = fecha.strftime('%d%m%y')

    # 1. Procesar OTs
    ots_dia = {}
    if ot_files:
        ots_dia = procesar_ots_pdf(ot_files, EQUIPOS[yac])

    # 2. Generar Excel
    wb = generar_parte(yac, fecha, supervisor, eq_dia, conductores,
                       actividades_dia=actividades, ots_dia=ots_dia, oncall=oncall)
    xlsx_path = os.path.join(out_dir, f"4900100500_{ddmmyy}_PD_{yac}.xlsx")
    wb.save(xlsx_path)

    # 3. Exportar PDF parte
    from exportar_pdf import exportar_pdf
    pdf_parte = os.path.join(out_dir, f"4900100500_{ddmmyy}_PD_{yac}.pdf")
    exportar_pdf(xlsx_path, supervisor, yac, pdf_parte)

    # 4. Completar y unir OTs
    firma_src = os.path.join(os.path.dirname(__file__), 'FIRMA_CON_NOMBRE.PNG')
    firma_tmp = os.path.join(out_dir, '_firma_tmp.png')
    preparar_firma(firma_src, firma_tmp)

    writer = PdfWriter()
    fecha_dd = fecha.strftime('%d.%m.%Y')
    ORDEN = [e['id_ypf'] for e in EQUIPOS[yac] if not e.get('sinprog')]

    for eq in EQUIPOS[yac]:
        if eq.get('sinprog'): continue
        id_ypf = eq['id_ypf']
        if id_ypf not in ot_files: continue
        eq_num = id_ypf.split()[0]
        ots_eq = [f for f in ot_files if f and eq_num in f]
        for i, pdf_path in enumerate(ots_eq):
            tmp = os.path.join(out_dir, f'_tmp_{eq_num}_{i}.pdf')
            ok = completar_ot_pdf(pdf_path, tmp, eq_num, fecha_dd, firma_tmp)
            if ok:
                for pg in PdfReader(tmp).pages: writer.add_page(pg)
                os.remove(tmp)

    pdf_ots = os.path.join(out_dir, f"OT_4900100500_TSB_{ddmmyyyy}_{yac}.pdf")
    with open(pdf_ots, 'wb') as f: writer.write(f)

    try: os.remove(firma_tmp)
    except: pass

    # 5. Enviar emails (solo en Windows con Outlook)
    try:
        enviar_parte_y_ots(yac, fecha, xlsx_path, pdf_parte, pdf_ots)
        emails_ok = True
    except Exception as e:
        emails_ok = False

    return jsonify({
        "ok": True,
        "xlsx": xlsx_path,
        "pdf_parte": pdf_parte,
        "pdf_ots": pdf_ots,
        "emails": emails_ok,
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"TSB Generador de Partes — http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
