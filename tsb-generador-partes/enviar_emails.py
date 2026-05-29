"""
TSB · Generador de Partes — Módulo de Emails
Envía 2 emails por yacimiento via Outlook (win32com):
  Email 1: Parte diario (Excel + PDF)
  Email 2: OTs unidas (PDF)
"""

EMAIL_CONFIG = {
    "PHZ": {
        "parte": {
            "to":      ["german.huerta@set.ypf.com", "juan.c.sanchez@set.ypf.com"],
            "cc":      ["rrodriguez@tsbsa.com.ar", "agonsales@tsbsa.com.ar", "mrolando@tsbsa.com.ar"],
            "asunto":  "4900100500_{ddmmyy}_PD_PHZ",
            "cuerpo":  "Estimados, buen día.\n\nEnvío parte diario correspondiente al día {fecha_larga}.\nFavor de devolver firmado.\n\nSaludos.",
        },
        "ots": {
            "to":      ["rrodriguez@tsbsa.com.ar", "mrolando@tsbsa.com.ar"],
            "cc":      ["mpariente@tsbsa.com.ar"],
            "asunto":  "OT COMPLETAS PHZ {dd}.{mm}.{yy}",
            "cuerpo":  "Estimado/a, buen día.\n\nLes adjunto las OT completas correspondientes al día {fecha_larga}.\n\nSaludos.-",
        },
    },
    "SP": {
        "parte": {
            "to":      ["claudio.mendez@ypf.com", "nestor.f.ramirez@ypf.com",
                        "angel.torres@ypf.com", "francisco.j.rosales@set.ypf.com"],
            "cc":      ["mpariente@tsbsa.com.ar", "rrodriguez@tsbsa.com.ar",
                        "mrolando@tsbsa.com.ar", "jrherrera@tsbsa.com.ar",
                        "jizquierdo@tsbsa.com.ar", "ralvarenga@tsbsa.com.ar"],
            "asunto":  "4900100500_{ddmmyy}_PD_SP",
            "cuerpo":  "Estimados, buen día.\n\nEnvío parte diario correspondiente al día {fecha_larga}.\nFavor de devolver firmado.\n\nSaludos.",
        },
        "ots": {
            "to":      ["rrodriguez@tsbsa.com.ar", "mrolando@tsbsa.com.ar"],
            "cc":      ["mpariente@tsbsa.com.ar"],
            "asunto":  "OT COMPLETAS SP {dd}.{mm}.{yy}",
            "cuerpo":  "Estimado/a, buen día.\n\nLes adjunto las OT completas correspondientes al día {fecha_larga}.\n\nSaludos.-",
        },
    },
    "CHSN": {
        "parte": {
            "to":      ["hector.n.cayupan@set.ypf.com", "carlos.a.gatica@ypf.com"],
            "cc":      ["mpariente@tsbsa.com.ar", "rrodriguez@tsbsa.com.ar",
                        "ralvarenga@tsbsa.com.ar", "mrolando@tsbsa.com.ar",
                        "veronica.e.colonna@aesa.com.ar"],
            "asunto":  "4900100500_{ddmmyy}_PD_CHSN",
            "cuerpo":  "Estimados, buen día.\n\nEnvío parte diario correspondiente al día {fecha_larga}.\nFavor de devolver firmado.\n\nSaludos.",
        },
        "ots": {
            "to":      ["rrodriguez@tsbsa.com.ar", "mrolando@tsbsa.com.ar"],
            "cc":      ["mpariente@tsbsa.com.ar"],
            "asunto":  "OT COMPLETAS CHSN {dd}.{mm}.{yy}",
            "cuerpo":  "Estimado/a, buen día.\n\nLes adjunto las OT completas correspondientes al día {fecha_larga}.\n\nSaludos.-",
        },
    },
}

MESES_ES = {
    1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
    7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"
}

def _formatear_fecha(fecha):
    """fecha: datetime.date → dict con claves para format strings."""
    return {
        "dd":          f"{fecha.day:02d}",
        "mm":          f"{fecha.month:02d}",
        "yy":          str(fecha.year)[2:],
        "yyyy":        str(fecha.year),
        "ddmmyy":      f"{fecha.day:02d}{fecha.month:02d}{str(fecha.year)[2:]}",
        "fecha_larga": f"{fecha.day} de {MESES_ES[fecha.month]} de {fecha.year}",
    }

def enviar_via_outlook(to, cc, asunto, cuerpo, adjuntos, log_fn=print):
    """
    Envía email usando Outlook via win32com (Windows).
    adjuntos: lista de rutas de archivo absolutas.
    """
    import win32com.client
    import os

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail    = outlook.CreateItem(0)  # 0 = olMailItem

        mail.To  = "; ".join(to)
        mail.CC  = "; ".join(cc)
        mail.Subject = asunto
        mail.Body    = cuerpo

        for path in adjuntos:
            if os.path.exists(path):
                mail.Attachments.Add(os.path.abspath(path))
            else:
                log_fn(f"  ⚠ Adjunto no encontrado: {path}")

        mail.Send()
        log_fn(f"  ✅ Email enviado: {asunto}")
        return True

    except Exception as e:
        log_fn(f"  ❌ Error enviando email: {e}")
        return False


def enviar_parte_y_ots(yacimiento, fecha, excel_path, pdf_parte_path,
                        pdf_ots_path, log_fn=print):
    """
    Envía los 2 emails del yacimiento:
      1. Parte diario (Excel + PDF parte)
      2. OTs unidas (PDF OTs)

    yacimiento: "PHZ" | "SP" | "CHSN"
    fecha: datetime.date
    """
    cfg = EMAIL_CONFIG[yacimiento]
    fv  = _formatear_fecha(fecha)

    # Email 1: Parte diario
    cfg_parte = cfg["parte"]
    ok1 = enviar_via_outlook(
        to       = cfg_parte["to"],
        cc       = cfg_parte["cc"],
        asunto   = cfg_parte["asunto"].format(**fv),
        cuerpo   = cfg_parte["cuerpo"].format(**fv),
        adjuntos = [excel_path, pdf_parte_path],
        log_fn   = log_fn,
    )

    # Email 2: OTs
    cfg_ots = cfg["ots"]
    ok2 = enviar_via_outlook(
        to       = cfg_ots["to"],
        cc       = cfg_ots["cc"],
        asunto   = cfg_ots["asunto"].format(**fv),
        cuerpo   = cfg_ots["cuerpo"].format(**fv),
        adjuntos = [pdf_ots_path],
        log_fn   = log_fn,
    )

    return ok1, ok2
