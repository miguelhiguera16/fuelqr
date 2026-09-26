# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FuelScanLog(Document):
	pass


def register_scan(result, ticket=None, failure_reason=None):
	"""
	Registra un intento de escaneo QR.
	Llamar desde el endpoint de validación del QR.

	Args:
		result        : str  — resultado del escaneo (ej: "Válido", "Firma Inválida")
		ticket        : str  — nombre del Fuel Ticket si se pudo resolver
		failure_reason: str  — detalle del motivo de fallo
	"""
	try:
		log = frappe.new_doc("Fuel Scan Log")
		log.timestamp      = frappe.utils.now_datetime()
		log.result         = result
		log.user           = frappe.session.user
		log.ip_address     = frappe.local.request_ip if hasattr(frappe.local, "request_ip") else None
		log.ticket         = ticket
		log.failure_reason = failure_reason
		log.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		# El log nunca debe interrumpir el flujo principal
		frappe.log_error(frappe.get_traceback(), "Fuel Scan Log - Error al registrar")