# Copyright (c) 2026, FuelQR and contributors
# API endpoints para la página de despacho

import frappe
from frappe import _
from frappe.utils import now_datetime

from fuelqr.fuelqr.doctype.fuel_audit_log.fuel_audit_log import write_log


@frappe.whitelist()
def validate_ticket(token):
    """
    Valida un token QR o código corto.
    Retorna los datos del ticket si es válido.
    """
    from fuelqr.fuelqr.doctype.fuel_scan_log.fuel_scan_log import register_scan

    if not token:
        return {"success": False, "error": "Token vacío"}

    token = token.strip()

    # Determinar si es QR token o código corto
    if token.startswith("FT1."):
        ticket = _validate_qr_token(token)
    else:
        ticket = _validate_short_code(token)

    if not ticket:
        register_scan("No Encontrado", failure_reason=f"Token no resuelto: {token[:20]}")
        return {"success": False, "error": "Ticket no encontrado"}

    # Verificar estado
    valid_statuses = ["Creado", "Enviado", "Pendiente", "Próximo a Vencer"]
    if ticket.status not in valid_statuses:
        register_scan(
            "Ya Consumido" if ticket.status == "Consumido" else ticket.status,
            ticket=ticket.name,
            failure_reason=f"Estado inválido: {ticket.status}"
        )
        return {
            "success": False,
            "error": f"El ticket no puede ser despachado. Estado: {ticket.status}"
        }

    # Verificar vencimiento
    if ticket.expires_on and frappe.utils.get_datetime(ticket.expires_on) < now_datetime():
        frappe.db.set_value("Fuel Ticket", ticket.name, "status", "Vencido")
        register_scan("Expirado", ticket=ticket.name, failure_reason="Ticket vencido")
        return {"success": False, "error": "El ticket ha vencido"}

    # Verificar estación
    dispatcher_station = _get_dispatcher_station()
    if dispatcher_station and ticket.station != dispatcher_station:
        register_scan(
            "Estación Incorrecta",
            ticket=ticket.name,
            failure_reason=f"Estación del ticket: {ticket.station}, estación del despachador: {dispatcher_station}"
        )
        return {
            "success": False,
            "error": f"Este ticket es para la estación {ticket.station}"
        }

    # Todo OK — registrar escaneo exitoso
    register_scan("Válido", ticket=ticket.name)

    # Obtener datos adicionales
    employee_name = frappe.db.get_value("Employee", ticket.employee, "employee_name")
    cedula = frappe.db.get_value("Employee", ticket.employee, "cedula")

    write_log(
        action="Escanear",
        ref_doctype="Fuel Ticket",
        ref_docname=ticket.name,
        data={
            "result": "Válido",
            "dispatcher": frappe.session.user,
        }
    )

    return {
        "success": True,
        "ticket": {
            "name":           ticket.name,
            "status":         ticket.status,
            "employee":       ticket.employee,
            "employee_name":  employee_name,
            "cedula":         cedula,
            "vehicle":        ticket.vehicle,
            "department":     ticket.department,
            "fuel_item":      ticket.fuel_item,
            "station":        ticket.station,
            "qty_authorized": ticket.qty_authorized,
            "qty_dispatched": ticket.qty_dispatched,
            "qty_remaining":  ticket.qty_remaining,
            "uom":            ticket.uom,
            "expires_on":     str(ticket.expires_on),
        }
    }


@frappe.whitelist()
def create_dispatch(ticket_name, qty_dispatched, odometer=None,
                    identity_method=None, identity_ref=None, observations=None):
    if not ticket_name or not qty_dispatched:
        frappe.throw(_("Datos incompletos para el despacho"))

    # Obtener todos los datos del ticket
    ticket = frappe.get_doc("Fuel Ticket", ticket_name)

    dispatch = frappe.new_doc("Fuel Dispatch")
    dispatch.fuel_ticket     = ticket_name
    dispatch.qty_dispatched  = float(qty_dispatched)
    dispatch.station         = ticket.station
    dispatch.vehicle         = ticket.vehicle
    dispatch.employee        = ticket.employee
    dispatch.fuel_item       = ticket.fuel_item
    dispatch.uom             = ticket.uom
    dispatch.qty_authorized  = ticket.qty_authorized
    dispatch.identity_method = identity_method or "Visual"
    dispatch.identity_ref    = identity_ref or ""
    dispatch.observations    = observations or ""

    if odometer:
        dispatch.odometer = float(odometer)

    dispatch.insert(ignore_permissions=True)
    dispatch.submit()

    return {
        "success": True,
        "dispatch": dispatch.name,
        "message": f"Despacho {dispatch.name} registrado exitosamente"
    }


# ─── Helpers privados ───────────────────────────────────────────────────────

def _validate_qr_token(token):
    """Busca el ticket por QR token y verifica la firma HMAC."""
    import hashlib
    import hmac
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 4:
        return None

    version, kid, payload_b64, sig_b64 = parts

    # Obtener la llave
    fuel_qr_keys = frappe.conf.get("fuel_qr_keys", {})
    if isinstance(fuel_qr_keys, str):
        fuel_qr_keys = json.loads(fuel_qr_keys)

    secret = fuel_qr_keys.get(kid)
    if not secret:
        return None

    # Verificar firma
    message = f"{version}.{kid}.{payload_b64}"
    secret_bytes = base64.b64decode(secret)
    expected_sig = hmac.new(
        secret_bytes,
        message.encode(),
        hashlib.sha256
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig[:16]).decode().rstrip("=")

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        return None

    # Decodificar payload
    padding = 4 - len(payload_b64) % 4
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))

    # Buscar el ticket por uuid
    ticket_name = frappe.db.get_value("Fuel Ticket", {"uuid": payload.get("t")}, "name")
    if not ticket_name:
        return None

    return frappe.get_doc("Fuel Ticket", ticket_name)


def _validate_short_code(code):
    """Busca el ticket por código corto usando el hash."""
    import hashlib

    site_salt = frappe.conf.get("db_password", "default_salt")
    hash_input = f"{site_salt}:{code}".encode()
    code_hash = hashlib.sha256(hash_input).hexdigest()

    ticket_name = frappe.db.get_value(
        "Fuel Ticket",
        {"short_code_hash": code_hash, "docstatus": 1},
        "name"
    )
    if not ticket_name:
        return None

    return frappe.get_doc("Fuel Ticket", ticket_name)


def _get_dispatcher_station():
    """
    Retorna la estación asignada al despachador actual.
    Por ahora retorna None (sin restricción por estación).
    Se puede extender agregando un campo station al User.
    """
    return None