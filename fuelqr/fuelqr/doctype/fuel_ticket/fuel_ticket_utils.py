# Copyright (c) 2026, Pymegrowth and contributors

import base64
import frappe


def get_qr_image_base64(ticket_name):
    """
    Retorna la imagen QR como string base64 para uso en Print Formats.
    Accede al archivo privado directamente desde el sistema de archivos.
    """
    qr_image_url = frappe.db.get_value("Fuel Ticket", ticket_name, "qr_image")
    if not qr_image_url:
        return None

    # Construir la ruta absoluta del archivo
    site_path = frappe.get_site_path()
    
    # Los archivos privados van en sites/<site>/private/files/
    if qr_image_url.startswith("/private/files/"):
        file_path = site_path + qr_image_url
    elif qr_image_url.startswith("/files/"):
        file_path = site_path + "/public" + qr_image_url
    else:
        return None

    try:
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return encoded
    except FileNotFoundError:
        frappe.log_error(f"QR image not found: {file_path}", "FuelQR")
        return None