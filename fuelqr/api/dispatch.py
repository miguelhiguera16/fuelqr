# Copyright (c) 2026, FuelQR and contributors
# API endpoints para la página de despacho

import hashlib
import hmac as hmac_mod

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
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        ["name", "employee_name"],
        as_dict=True
    )

    if not employee:
        frappe.get_doc({
            "doctype": "Fuel Scan Log",
            "timestamp": frappe.utils.now_datetime(),
            "result": "Fallido",
            "user": frappe.session.user,
            "ip_address": frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None,
            "failure_reason": "El usuario no tiene un empleado activo vinculado"
        }).insert(ignore_permissions=True)

        return {
            "success": False,
            "error": "Tu usuario no tiene un empleado activo asignado. Contacta al administrador."
        }

    from fuelqr.fuelqr.doctype.fuel_scan_log.fuel_scan_log import register_scan

    if not token:
        return {"success": False, "error": "Token vacío"}

    token = token.strip()

    # Determinar si es QR token o código corto
    if token.startswith("FT1."):
        ticket = _validate_qr_token(token)

        # El QR debe ser exactamente el vigente: uno regenerado o consumido no vale,
        # aunque la firma HMAC y el uuid sigan siendo válidos.
        if ticket and not (ticket.qr_token and hmac_mod.compare_digest(ticket.qr_token, token)):
            register_scan(
                "Ya Consumido",
                ticket=ticket.name,
                failure_reason="QR reemplazado o ya utilizado"
            )
            return {
                "success": False,
                "error": "Este QR ya fue utilizado. Solicite el código vigente más reciente."
            }
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

    if frappe.session.user != "Administrator":
        dispatcher_employee = frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user, "status": "Active"},
            "name"
        )

        if not dispatcher_employee:
            frappe.throw(_("Tu usuario no tiene un empleado activo asignado."))

        if not ticket_name or not qty_dispatched:
            frappe.throw(_("Datos incompletos para el despacho"))

    # Obtener todos los datos del ticket
    ticket = frappe.get_doc("Fuel Ticket", ticket_name)

    # ── Verificación de identidad (RF-12) ────────────────────────────────────
    # Único método soportado además de la confirmación visual: cédula.
    method = (identity_method or "Visual").strip()
    ref = (identity_ref or "").strip()

    if method == "Cédula (últimos 4 dígitos)":
        if not ref or len(ref) != 4 or not ref.isdigit():
            frappe.throw(_("Ingrese los últimos 4 dígitos de la cédula."))

        real_cedula = frappe.db.get_value("Employee", ticket.employee, "cedula") or ""
        real_last4 = "".join(c for c in real_cedula if c.isdigit())[-4:]

        if not real_last4 or not hmac_mod.compare_digest(ref, real_last4):
            from fuelqr.fuelqr.doctype.fuel_scan_log.fuel_scan_log import register_scan
            register_scan(
                "Identidad Rechazada",
                ticket=ticket.name,
                failure_reason="Los últimos 4 dígitos de la cédula no coinciden"
            )
            write_log(
                action="Rechazar Identidad",
                ref_doctype="Fuel Ticket",
                ref_docname=ticket.name,
                data={"dispatcher": frappe.session.user, "method": method}
            )
            frappe.throw(_("Los últimos 4 dígitos de la cédula no coinciden con el empleado del ticket."))

    elif method != "Visual":
        frappe.throw(_("Método de verificación no soportado: {0}").format(method))

    dispatch = frappe.new_doc("Fuel Dispatch")
    dispatch.fuel_ticket     = ticket_name
    dispatch.qty_dispatched  = float(qty_dispatched)
    dispatch.station         = ticket.station
    dispatch.vehicle         = ticket.vehicle
    dispatch.employee        = ticket.employee
    dispatch.fuel_item       = ticket.fuel_item
    dispatch.uom             = ticket.uom
    dispatch.qty_authorized  = ticket.qty_authorized
    dispatch.identity_method = method
    dispatch.identity_ref    = ref
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
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 4:
        return None

    version, kid, payload_b64, sig_b64 = parts

    fuel_qr_keys = frappe.conf.get("fuel_qr_keys", {})
    if isinstance(fuel_qr_keys, str):
        fuel_qr_keys = json.loads(fuel_qr_keys)

    secret = fuel_qr_keys.get(kid)
    if not secret:
        return None

    message = f"{version}.{kid}.{payload_b64}"
    secret_bytes = base64.b64decode(secret)
    expected_sig = hmac_mod.new(
        secret_bytes,
        message.encode(),
        hashlib.sha256
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig[:16]).decode().rstrip("=")

    if not hmac_mod.compare_digest(sig_b64, expected_sig_b64):
        return None

    padding = 4 - len(payload_b64) % 4
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))

    ticket_name = frappe.db.get_value("Fuel Ticket", {"uuid": payload.get("t")}, "name")
    if not ticket_name:
        return None

    return frappe.get_doc("Fuel Ticket", ticket_name)


def _validate_short_code(code):
    """Busca el ticket por código corto usando el hash."""
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
    """
    return None


@frappe.whitelist()
def get_my_dispatches():
    """Retorna los despachos del despachador actual del día de hoy."""
    today = frappe.utils.today()

    dispatches = frappe.db.sql("""
        SELECT
            d.name,
            d.fuel_ticket,
            d.vehicle,
            d.qty_dispatched,
            d.uom,
            d.scanned_at,
            d.station,
            e.employee_name,
            t.status as ticket_status
        FROM `tabFuel Dispatch` d
        LEFT JOIN `tabEmployee` e ON e.name = d.employee
        LEFT JOIN `tabFuel Ticket` t ON t.name = d.fuel_ticket
        WHERE d.dispatcher = %(user)s
        AND DATE(d.scanned_at) = %(today)s
        AND d.docstatus = 1
        ORDER BY d.scanned_at DESC
    """, {
        "user": frappe.session.user,
        "today": today
    }, as_dict=True)

    total_qty = sum(d.qty_dispatched or 0 for d in dispatches)

    return {
        "dispatches": dispatches,
        "total_qty": total_qty,
        "count": len(dispatches)
    }


@frappe.whitelist()
def search_ticket(query):
    """Busca tickets por número, placa o código corto."""
    if not query or len(query) < 3:
        return []

    query = query.strip()

    tickets = frappe.db.sql("""
        SELECT
            t.name,
            t.status,
            t.vehicle,
            t.qty_authorized,
            t.qty_remaining,
            t.uom,
            t.expires_on,
            t.short_code,
            e.employee_name
        FROM `tabFuel Ticket` t
        LEFT JOIN `tabEmployee` e ON e.name = t.employee
        WHERE t.docstatus = 1
        AND (
            t.name LIKE %(q)s
            OR t.vehicle LIKE %(q)s
            OR t.short_code LIKE %(q)s
        )
        ORDER BY t.creation DESC
        LIMIT 10
    """, {"q": f"%{query}%"}, as_dict=True)

    return tickets