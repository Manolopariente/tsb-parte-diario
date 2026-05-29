"""
Motor de procesamiento — Sistema Parte Diario YPF
Contrato 4900100500 — Puesto Hernández
"""
import pdfplumber, fitz, openpyxl, shutil, re, os
from PIL import Image
import numpy as np
from datetime import time
from pypdf import PdfWriter, PdfReader

# ── MAPA MAESTRO ──────────────────────────────────────────────────
EQUIPOS_ACTIVOS = {
    "4664": {"pos":237, "desc":"SERV. TAR.A P/H RETRO 11TN"},
    "4659": {"pos":243, "desc":"RH TAR.A P/H CUAD. TAR.GENERALES"},
    "4663": {"pos":237, "desc":"SERV. TAR.A P/H RETRO 11TN"},
    "4656": {"pos":243, "desc":"RH TAR.A P/H CUAD. TAR.GENERALES"},
    "4689": {"pos":225, "desc":"SERV. TAR.A P/H CARG.FRON. 10TN"},
    "4687": {"pos":215, "desc":"SERV. HN CAM.TRAKKER 18M3"},
    "4669": {"pos":233, "desc":"SERV. TAR.A P/H MOTONIV. 170HP"},
}

# Orden fijo del Excel — regla de oro para el PDF unido
ORDEN_EXCEL = ["4664","4659","4663","4656","4689","4687","4669"]

FILAS = {"4664":8,"4659":13,"4663":18,"4656":23,"4689":28,"4687":33,"4669":38}

STANDBY = [
    {"fb":43,"k_t":"Tarea",    "l":"sin chofer",                "pos":59,"w":"SERV. TAR.C P/H CAM.REGAD. 25M3",   "i_m":5,"i_t":3},
    {"fb":48,"k_t":"Espera OT","l":"Sin programacion",          "pos":11,"w":"SERV. HN TOPAD. 180HP",              "i_m":0,"i_t":0},
    {"fb":53,"k_t":"Espera OT","l":"Sin programacion de tareas.","pos":75,"w":"SERV. TAR.C P/H CAM.C/BATEA 25M3", "i_m":0,"i_t":0},
    {"fb":58,"k_t":"Espera OT","l":"Sin programacion",          "pos":51,"w":"SERV. HN V.COMPAC.AUTOIM. 10TN",    "i_m":0,"i_t":0},
    {"fb":63,"k_t":"Espera OT","l":"Sin programacion",          "pos":51,"w":"SERV. HN V.COMPAC.AUTOIM. 10TN",    "i_m":0,"i_t":0},
]

# Posiciones Tarifa C por equipo (cuando no hay OT y motivo aplica TarifaC)
TARIFA_C_POS = {
    "4664": 35, "4663": 35,   # Retro
    "4659": 3,  "4656": 3,    # ATG/Tareas generales
    "4689": 27,               # Cargadora
    "4669": 19,               # Moto
    "4687": 67,               # Tracker
}

ONCALL_CONFIG = {
    "carreton":    {"id":"4694","pos":81, "um":"DIA","desc":"SERV. CARRETON"},
    "geomembrana": {"pos":97,  "um":"M2", "desc":"PROVISION GEOMEMBRANA"},
    "hormigon":    {"pos":105, "um":"M3", "desc":"PROVISION HORMIGON/CEMENTO"},
}

# Distribución horaria automática según cantidad de OTs por equipo
# La tarde (14→17, 3hs) siempre va completa para la ÚLTIMA OT
# Las 5hs de mañana se reparten entre las anteriores
HORARIOS_MANANA = {
    1: [(time(8,0),  time(13,0), 5)],   # 1 OT: mañana 08→13, tarde 14→17
    2: [(time(8,0),  time(13,0), 5)],
    3: [(time(8,0),  time(10,0), 2), (time(10,0), time(13,0), 3)],
    4: [(time(8,0),  time(9,0),  1), (time(9,0),  time(11,0), 2), (time(11,0), time(13,0), 2)],
}
HORARIO_TARDE = (time(14,0), time(17,0), 3)

def get_horarios(n_ots):
    """Retorna lista de (desde, hasta, horas) para cada OT del día."""
    n = min(n_ots, 4)
    bloques = list(HORARIOS_MANANA[n])
    bloques.append(HORARIO_TARDE)
    return bloques

# ── FIRMA ─────────────────────────────────────────────────────────
def preparar_firma(firma_src, firma_dst):
    img  = Image.open(firma_src).convert("RGBA")
    arr  = np.array(img)
    rgb  = arr[:,:,:3].astype(np.float32)
    alpha = np.clip((255 - rgb.mean(axis=2)) * 2.5, 0, 255).astype(np.uint8)
    out  = np.zeros_like(arr); out[:,:,3] = alpha
    Image.fromarray(out,'RGBA').save(firma_dst)

# ── DETECCIÓN EQUIPO EN PDF ───────────────────────────────────────
def detectar_equipo_en_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        words = pdf.pages[0].extract_words()
        for w in words:
            for eq_id in list(EQUIPOS_ACTIVOS.keys()) + ["4694","4675","4693","4680","4691","4692"]:
                if eq_id in w['text']:
                    return eq_id
    return None

# ── LEER OT PDF ────────────────────────────────────────────────────
def leer_ot(pdf_path, fecha_dd):
    with pdfplumber.open(pdf_path) as pdf:
        ot_num = None
        for page in pdf.pages:
            words = page.extract_words()
            for i,w in enumerate(words):
                if w['text']=='N°' and i+1<len(words):
                    try: ot_num=int(words[i+1]['text']); break
                    except: pass
            if ot_num: break

        for page in pdf.pages:
            words = page.extract_words()
            for i,w in enumerate(words):
                if 'Programaci' not in w['text']: continue
                txt = w['text']+(" "+words[i+1]['text'] if i+1<len(words) else "")
                if fecha_dd not in txt: continue

                op_num = op_idx = None
                for k in range(i-1, max(-1,i-50), -1):
                    if words[k]['text'] in ('Operación','Operacion') and k+1<len(words):
                        try: op_num=int(words[k+1]['text']); op_idx=k; break
                        except: pass
                    m = re.match(r'Operaci[oó]n(\d+)', words[k]['text'])
                    if m: op_num=int(m.group(1)); op_idx=k; break

                tarea = None
                if op_idx is not None:
                    parts=[]
                    for j in range(op_idx+2, i):
                        if 'Programaci' in words[j]['text']: break
                        if words[j]['text']=='-': continue
                        parts.append(words[j]['text'])
                    tarea = ' '.join(parts).strip(' -,')

                ubic = None
                for k,ww in enumerate(words):
                    if ww['text']=='Código' and k+1<len(words):
                        c = words[k+1]['text']
                        if c.startswith('CV-'):
                            ubic = c
                            break

                return {"ot":ot_num,"op":op_num,"tarea":tarea,"ubic":ubic}
    return None

# ── COMPLETAR EXCEL ────────────────────────────────────────────────
def completar_excel(excel_base, fecha_dd, datos_ots_por_equipo, out_path, oncall=None):
    """
    datos_ots_por_equipo: {eq_id: [lista de dicts OT]}
    """
    shutil.copy(excel_base, out_path)
    wb = openpyxl.load_workbook(out_path)
    ws = wb["Parte Diario"]

    # Fecha del parte en C3
    try:
        from datetime import datetime as _dt
        ws["C3"] = _dt.strptime(fecha_dd, "%d.%m.%Y").date()
    except: pass

    # Solo escribir en estas columnas — NUNCA tocar I(9),J(10),U(21),V(22),W(23) que tienen fórmulas
    def _cel(f,c,v): ws.cell(f,c,v)
    COLS_LIMPIAR = [11,12,13,14,16,17,18,19]  # K,L,M,N,P,Q,R,S

    for eq_id in ORDEN_EXCEL:
        if eq_id not in FILAS: continue
        eq  = EQUIPOS_ACTIVOS[eq_id]
        fb  = FILAS[eq_id]
        datos_lista = datos_ots_por_equipo.get(eq_id, [{}])
        n   = len(datos_lista)

        pos_usar  = 67 if eq_id=="4687" and not any(d.get("ot") for d in datos_lista) else eq["pos"]
        desc_usar = "SERV. TAR.C P/H CAM.TRAKKER 18M3" if pos_usar==67 else eq["desc"]

        horarios = get_horarios(n)
        off = 0

        # Limpiar solo K,L,M,N,P,Q,R,S en las 3 filas del equipo — sin borrar formato
        for limpia in range(3):
            for col in COLS_LIMPIAR:
                ws.cell(fb+limpia, col, "")

        # Filas de mañana
        for i, (desde, hasta, horas) in enumerate(horarios[:-1]):
            d = datos_lista[i] if i < len(datos_lista) else {}
            fila = fb + off
            _cel(fila,11,"Tarea")
            _cel(fila,16,desde);  _cel(fila,17,hasta)
            _cel(fila,12,d.get("tarea","")); _cel(fila,13,d.get("ot"))
            _cel(fila,14,d.get("op"));       _cel(fila,18,d.get("ubic",""))
            _cel(fila,19,pos_usar)
            off += 1

        # Almuerzo — solo K,L,P,Q,S — M,N,R quedan vacíos (ya limpiados arriba)
        fila = fb + off
        _cel(fila,11,"Almuerzo")
        _cel(fila,16,time(13,0)); _cel(fila,17,time(14,0))
        _cel(fila,12,"refrigerio"); _cel(fila,19,None)
        off += 1

        # Tarde — última OT
        d_ult = datos_lista[-1]
        desde_t, hasta_t, horas_t = horarios[-1]
        fila = fb + off
        _cel(fila,11,"Tarea")
        _cel(fila,16,desde_t); _cel(fila,17,hasta_t)
        _cel(fila,12,d_ult.get("tarea","")); _cel(fila,13,d_ult.get("ot"))
        _cel(fila,14,d_ult.get("op"));       _cel(fila,18,d_ult.get("ubic",""))
        _cel(fila,19,pos_usar)
        off += 1

        # On-call material (fila extra 17:00→17:15)
        if oncall:
            ocfg = cfg = cant = None
            if oncall.get("geomembrana") and oncall["geomembrana"]["eq_id"]==eq_id:
                ocfg = oncall["geomembrana"]; cfg = ONCALL_CONFIG["geomembrana"]
                cant = ocfg["cantidad"]
            elif oncall.get("hormigon") and oncall["hormigon"]["eq_id"]==eq_id:
                ocfg = oncall["hormigon"]; cfg = ONCALL_CONFIG["hormigon"]
                cant = ocfg["cantidad"]
            if ocfg and cfg:
                cant_fmt = int(cant) if cant==int(cant) else cant
                fila = fb + off
                for col in range(1, 8):
                    ws.cell(fila, col, ws.cell(fb, col).value)
                _cel(fila,11,"Tarea")
                _cel(fila,16,time(17,0)); _cel(fila,17,time(17,15)); _cel(fila,20,10)
                if "GEO" in cfg["desc"].upper():
                    _cel(fila,12,"Provision de geomembrana")
                else:
                    _cel(fila,12,"Provision de hormigon")
                _cel(fila,13,d_ult.get("ot"))
                _cel(fila,18,d_ult.get("ubic","")); _cel(fila,19,cfg["pos"])
                _cel(fila,21,cant_fmt); _cel(fila,22,cfg["um"]); _cel(fila,23,cfg["desc"])

    # Standby
    for eq in STANDBY:
        fb = eq["fb"]
        for off,(k_act,p,q) in enumerate([
            (eq["k_t"], time(8,0),  time(13,0)),
            ("Almuerzo", time(13,0), time(14,0)),
            (eq["k_t"], time(14,0), time(17,0)),
        ]):
            fila = fb + off; es_alm = (k_act == "Almuerzo")
            ws.cell(fila,11,k_act)
            ws.cell(fila,16,p); ws.cell(fila,17,q)
            if not es_alm:
                ws.cell(fila,12,eq["l"]); ws.cell(fila,19,eq["pos"])
            else:
                ws.cell(fila,12,"Refrigerio en el lugar de trabajo.")
                ws.cell(fila,19,None)
                ws.cell(fila,13,""); ws.cell(fila,14,""); ws.cell(fila,18,"")

    # Carretón
    if oncall and oncall.get("carreton"):
        c = oncall["carreton"]; cfg = ONCALL_CONFIG["carreton"]; fila=41
        ws.cell(fila,7,"4694 -Carretón"); ws.cell(fila,11,"Tarea")
        ws.cell(fila,12,c.get("tarea","Movilizacion equipo vial"))
        ws.cell(fila,13,c.get("ot")); ws.cell(fila,14,c.get("op"))
        ws.cell(fila,16,time(8,0)); ws.cell(fila,17,time(13,0))
        ws.cell(fila,18,c.get("ubic","")); ws.cell(fila,19,cfg["pos"])
        ws.cell(fila,20,10); ws.cell(fila,21,1)
        ws.cell(fila,22,cfg["um"])

    # Equipos sin OT (notas de faltantes)
    notas = datos_ots_por_equipo.get("_notas_faltantes", {})
    for eq_id, nota in notas.items():
        if eq_id not in FILAS: continue
        if nota.get("accion") == "motivo":
            fb  = FILAS[eq_id]
            motivo = nota["motivo"]
            desc   = nota["descripcion"]
            tarifa_c = nota.get("tarifa_c", False)
            pos = TARIFA_C_POS.get(eq_id) if tarifa_c else None

            # Limpiar solo las 3 filas del equipo (mañana, almuerzo, tarde)
            for limpia in range(3):
                for col in [11,12,13,14,16,17,18,19]:
                    ws.cell(fb+limpia, col, "")

            # Mañana
            ws.cell(fb,  11, motivo); ws.cell(fb,  12, desc)
            ws.cell(fb,  16, time(8,0)); ws.cell(fb, 17, time(13,0))
            ws.cell(fb,  19, pos)
            # Almuerzo
            ws.cell(fb+1,11,"Almuerzo"); ws.cell(fb+1,12,"refrigerio")
            ws.cell(fb+1,16,time(13,0)); ws.cell(fb+1,17,time(14,0))
            ws.cell(fb+1,19,None)
            # Tarde
            ws.cell(fb+2,11, motivo); ws.cell(fb+2,12, desc)
            ws.cell(fb+2,16, time(14,0)); ws.cell(fb+2,17, time(17,0))
            ws.cell(fb+2,19, pos)

    wb.save(out_path)

# ── COMPLETAR OT PDF ───────────────────────────────────────────────
def completar_ot_pdf(input_pdf, output_pdf, eq_id, fecha_dd, firma_path,
                     hora_ini="08:00", hora_fin="17:00", tnr="8", oncall_str=None):
    if eq_id == "4694":
        cant_str = "1 pos 81"
    else:
        pos = EQUIPOS_ACTIVOS.get(eq_id,{}).get("pos",237)
        cant_str = f"{tnr} hs pos {pos}"

    fdd = fecha_dd[0:6]+fecha_dd[8:10]

    with pdfplumber.open(input_pdf) as pr:
        for pn, page in enumerate(pr.pages):
            words = page.extract_words()
            lines = page.lines
            for i,w in enumerate(words):
                if 'Programaci' not in w['text']: continue
                txt = w['text']+(" "+words[i+1]['text'] if i+1<len(words) else "")
                if fecha_dd not in txt: continue

                fi_y = td_y = None
                for k in range(i, min(i+80,len(words))):
                    wt = words[k]['text']
                    if wt=='Fecha' and k+2<len(words) and words[k+1]['text'] in ('Inicial','InicialReal'):
                        fi_y = words[k]['top']
                    if 'TDV' in wt and fi_y:
                        td_y = words[k]['top']; break
                if not fi_y or not td_y: continue

                def h_ys(y): return sorted(set(round(l['top'],1) for l in lines if abs(l['top']-l['bottom'])<1 and y<l['top']<y+70))
                def v_xs(yt,yb): return sorted(set(round(l['x0'],1) for l in lines if abs(l['x0']-l['x1'])<1 and l['top']<=yt+5 and l['bottom']>=yb-5))

                ys_fe=h_ys(fi_y); ys_hs=h_ys(td_y)
                if len(ys_fe)<2 or len(ys_hs)<2: continue
                fe_mid=(ys_fe[0]+ys_fe[1])/2+3
                hs_mid=(ys_hs[0]+ys_hs[1])/2+3
                xs_fe=v_xs(ys_fe[0],ys_fe[1])
                xs_hs=v_xs(ys_hs[0],ys_hs[1])

                doc=fitz.open(input_pdf); pg=doc[pn]

                for idx,txt in enumerate([fdd, hora_ini, fdd, hora_fin]):
                    if idx<len(xs_fe)-1:
                        pg.insert_text(fitz.Point(xs_fe[idx]+5,fe_mid),txt,
                                       fontname="helv",fontsize=10,color=(0,0,0))
                for ci,txt in [(1,tnr),(2,"1"),(5,cant_str)]:
                    if ci<len(xs_hs)-1:
                        pg.insert_text(fitz.Point(xs_hs[ci]+5,hs_mid),txt,
                                       fontname="helv",fontsize=10,color=(0,0,0))
                if oncall_str and len(xs_hs)>5:
                    pg.insert_text(fitz.Point(xs_hs[5]+5,hs_mid+11),
                                   oncall_str,fontname="helv",fontsize=10,color=(0,0,0))

                last=doc[len(doc)-1]
                with pdfplumber.open(input_pdf) as p2:
                    lw=p2.pages[len(doc)-1].extract_words()
                fy=next((fw['top'] for fw in lw if 'Ejecutante' in fw['text']),None)
                if fy:
                    last.insert_image(fitz.Rect(437.5,fy-90,536.5,fy-3),
                                      filename=firma_path,keep_proportion=True)
                doc.save(output_pdf); doc.close(); return True
    return False

# ── EXPORTAR EXCEL A PDF VÍA EXCEL COM (Windows, sin LibreOffice) ─
def exportar_excel_a_pdf_com(excel_path, firma_path, out_pdf, log_fn=print):
    import subprocess, sys
    excel_abs = os.path.abspath(excel_path)
    out_abs   = os.path.abspath(out_pdf)

    script = (
        "import win32com.client, os\n"
        "try:\n"
        "    xl = win32com.client.Dispatch('Excel.Application')\n"
        "    xl.Visible = False\n"
        "    xl.DisplayAlerts = False\n"
        f"    wb = xl.Workbooks.Open(r'{excel_abs}')\n"
        "    for sh in wb.Sheets:\n"
        "        if sh.Name != 'Parte Diario':\n"
        "            sh.Visible = 2\n"
        "    ws = wb.Sheets('Parte Diario')\n"
        "    ws.Activate()\n"
        "    ws.PageSetup.PrintArea = 'A1:Z70'\n"
        f"    ws.ExportAsFixedFormat(0, r'{out_abs}')\n"
        "    ws.PageSetup.PrintArea = ''\n"
        "    for sh in wb.Sheets:\n"
        "        if sh.Name != 'Parte Diario':\n"
        "            sh.Visible = -1\n"
        "    wb.Close(False)\n"
        "    xl.Quit()\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print('ERR:'+str(e))\n"
        "    try: xl.Quit()\n"
        "    except: pass\n"
    )
    tmp_sc = os.path.join(os.path.dirname(out_pdf), "_xl_export.py")
    with open(tmp_sc,"w",encoding="utf-8") as f: f.write(script)

    try:
        res = subprocess.run([sys.executable, tmp_sc],
                             capture_output=True, text=True, timeout=45)
        output = res.stdout.strip()
        stderr = res.stderr.strip()
    except subprocess.TimeoutExpired:
        output = "ERR:Excel tardó más de 45 segundos"
        stderr = ""
    finally:
        try: os.remove(tmp_sc)
        except: pass

    if output.startswith("ERR") or "OK" not in output:
        log_fn(f"  ⚠ PDF Excel falló: {output}")
        if stderr: log_fn(f"  ⚠ Detalle: {stderr[:300]}")
        return False

    # Agregar firma
    try:
        doc  = fitz.open(out_pdf)
        page = doc[0]
        pw, ph = page.rect.width, page.rect.height
        page.insert_image(fitz.Rect(pw-205, ph-205, pw-15, ph-15),
                          filename=firma_path, keep_proportion=True)
        tmp = out_pdf.replace(".pdf","_tmp.pdf")
        doc.save(tmp); doc.close()
        os.replace(tmp, out_pdf)
    except Exception as e:
        log_fn(f"  ⚠ Firma PDF: {e}")
    return True

# ── FLUJO COMPLETO ─────────────────────────────────────────────────
def procesar_todo(excel_base, ot_pdfs_por_equipo, fecha_dd, firma_src,
                  out_dir_pd, out_dir_ots, log_fn=print, oncall=None):
    """
    out_dir_pd:  carpeta donde van Excel + PDF parte diario
    out_dir_ots: carpeta donde van las OTs unidas
    """
    os.makedirs(out_dir_pd,  exist_ok=True)
    os.makedirs(out_dir_ots, exist_ok=True)

    tmp_dir   = out_dir_pd   # temporales junto al parte
    tmp_firma = os.path.join(tmp_dir,"_firma_tmp.png")
    preparar_firma(firma_src, tmp_firma)

    ddmmyy   = fecha_dd[0:2]+fecha_dd[3:5]+fecha_dd[8:10]
    ddmmyyyy = fecha_dd[0:2]+fecha_dd[3:5]+fecha_dd[6:10]
    nombre_base = f"4900100500  {ddmmyy} PD TSB PHZ"

    # Agregar PDFs subidos tardíamente desde notas de faltantes
    notas_faltantes = ot_pdfs_por_equipo.pop("_notas_faltantes", {})
    for eq_id, nota in notas_faltantes.items():
        if nota.get("accion") == "subir" and nota.get("pdfs"):
            ot_pdfs_por_equipo[eq_id] = nota["pdfs"]
    # Pasar notas al Excel para equipos con motivo
    datos_faltantes = {k:v for k,v in notas_faltantes.items() if v.get("accion")=="motivo"}

    # 1. Leer todas las OTs
    log_fn("Leyendo OTs...")
    datos_por_equipo = {}
    for eq_id, pdf_list in ot_pdfs_por_equipo.items():
        datos_list = []
        for pdf_path in pdf_list:
            d = leer_ot(pdf_path, fecha_dd)
            datos_list.append(d or {})
            log_fn(f"  ✓ {eq_id}: OT={d.get('ot') if d else '?'} Op={d.get('op') if d else '?'}")
        datos_por_equipo[eq_id] = datos_list

    if "4687" not in datos_por_equipo:
        datos_por_equipo["4687"] = [{"ot":None,"op":None,"tarea":"Realiza VTV","ubic":None}]
        log_fn("  ℹ 4687: VTV sin OT (Tarifa C)")

    # 2. Completar Excel
    log_fn("Completando Excel...")
    out_xls = os.path.join(out_dir_pd, nombre_base+".xlsx")
    # Combinar datos normales con notas de faltantes
    datos_completos = {**datos_por_equipo, "_notas_faltantes": datos_faltantes}
    completar_excel(excel_base, fecha_dd, datos_completos, out_xls, oncall=oncall)
    log_fn(f"  ✓ {os.path.basename(out_xls)}")

    # 3. Completar y unir PDFs EN ORDEN DEL EXCEL
    log_fn("Completando OTs PDF...")
    writer = PdfWriter()

    for eq_id in ORDEN_EXCEL:
        if eq_id not in ot_pdfs_por_equipo: continue
        pdf_list   = ot_pdfs_por_equipo[eq_id]
        n          = len(pdf_list)

        # Horarios por PDF:
        # 1 PDF → jornada completa 08:00→17:00, TNR=8
        # 2 PDF → primer PDF 08:00→13:00 (5hs), segundo 14:00→17:00 (3hs)
        # 3 PDF → 08→10 (2hs), 10→13 (3hs), 14→17 (3hs)
        # 4 PDF → 08→09 (1hs), 09→11 (2hs), 11→13 (2hs), 14→17 (3hs)
        if n == 1:
            horarios_pdf = [(time(8,0), time(17,0), 8)]
        else:
            horarios_pdf = get_horarios(n)  # retorna mañana bloques + tarde

        for i, pdf_path in enumerate(pdf_list):
            desde, hasta, horas = horarios_pdf[i] if i < len(horarios_pdf) else HORARIO_TARDE
            hora_ini = desde.strftime("%H:%M")
            hora_fin = hasta.strftime("%H:%M")
            tnr_str  = str(horas)

            # On-call solo en el primer PDF del equipo
            oncall_str = None
            if i==0 and oncall:
                if oncall.get("geomembrana") and oncall["geomembrana"]["eq_id"]==eq_id:
                    cant = oncall["geomembrana"]["cantidad"]
                    cf   = int(cant) if cant==int(cant) else cant
                    oncall_str = f"{cf} m2 pos {ONCALL_CONFIG['geomembrana']['pos']}"
                if oncall.get("hormigon") and oncall["hormigon"]["eq_id"]==eq_id:
                    cant = oncall["hormigon"]["cantidad"]
                    cf   = int(cant) if cant==int(cant) else cant
                    oncall_str = f"{cf} m3 pos {ONCALL_CONFIG['hormigon']['pos']}"

            tmp_ot = os.path.join(tmp_dir,f"_tmp_{eq_id}_{i}.pdf")
            ok = completar_ot_pdf(pdf_path, tmp_ot, eq_id, fecha_dd, tmp_firma,
                                  hora_ini=hora_ini, hora_fin=hora_fin,
                                  tnr=tnr_str, oncall_str=oncall_str)
            if ok:
                for pg in PdfReader(tmp_ot).pages: writer.add_page(pg)
                os.remove(tmp_ot)
                extra = f" +{oncall_str}" if oncall_str else ""
                log_fn(f"  ✓ {eq_id} [{hora_ini}→{hora_fin}]{extra}")

    # Carretón al final
    if oncall and oncall.get("carreton"):
        for pdf_path in oncall["carreton"].get("pdfs",[]):
            tmp_ot = os.path.join(tmp_dir,"_tmp_4694.pdf")
            ok = completar_ot_pdf(pdf_path, tmp_ot, "4694", fecha_dd, tmp_firma)
            if ok:
                for pg in PdfReader(tmp_ot).pages: writer.add_page(pg)
                os.remove(tmp_ot)
                log_fn("  ✓ Carretón 4694")

    out_ots = os.path.join(out_dir_ots, f"OT_4900100500_TSB_{ddmmyyyy}_PHZ.pdf")
    with open(out_ots,"wb") as f: writer.write(f)
    log_fn(f"  ✓ {os.path.basename(out_ots)}")

    # 4. Exportar Excel a PDF
    log_fn("Generando PDF Parte Diario...")
    out_pdf = os.path.join(out_dir_pd, nombre_base+".pdf")
    ok_pdf  = exportar_excel_a_pdf_com(out_xls, tmp_firma, out_pdf, log_fn=log_fn)
    if ok_pdf:
        log_fn(f"  ✓ {os.path.basename(out_pdf)}")
    else:
        log_fn("  ⚠ PDF no generado — verificá que Excel esté instalado y pywin32 disponible")

    try: os.remove(tmp_firma)
    except: pass

    log_fn("✅ LISTO")
    return {"excel":out_xls, "pdf_pd":out_pdf if ok_pdf else None, "pdf_ots":out_ots}
