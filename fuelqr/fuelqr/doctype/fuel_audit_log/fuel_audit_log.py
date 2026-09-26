# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import json
import frappe
import hashlib

from frappe.model.document import Document


class FuelAuditLog(Document):
	pass


def write_log(action, ref_doctype=None, ref_docname=None, data=None):
	"""
	Escribe una entrada en el Fuel Audit Log encadenada por hash.
	Nadie tiene permisos de escritura directa sobre este doctype —
	solo se escribe a través de esta función.

	Args:
		action      : str  — tipo de acción (Crear, Modificar, Despachar, etc.)
		ref_doctype : str  — DocType del documento afectado
		ref_docname : str  — nombre del documento afectado
		data        : dict — snapshot del documento (antes/después)
	"""
	try:
		timestamp = str(frappe.utils.now_datetime())
		user      = frappe.session.user
		data_json = json.dumps(data or {}, default=str, ensure_ascii=False)

		# Obtener el hash del último registro para encadenar
		last_hash = frappe.db.get_value(
			"Fuel Audit Log",
			filters={},
			fieldname="record_hash",
			order_by="creation desc"
		) or "GENESIS"

		# Calcular el hash de este registro
		raw = f"{last_hash}|{timestamp}|{action}|{user}|{ref_doctype}|{ref_docname}|{data_json}"
		record_hash = hashlib.sha256(raw.encode()).hexdigest()

		# Insertar directamente sin pasar por el ORM para evitar hooks
		frappe.db.sql("""
			INSERT INTO `tabFuel Audit Log`
				(name, creation, modified, modified_by, owner, docstatus,
				 timestamp, action, user, ip_address,
				 ref_doctype, ref_docname, data_json,
				 prev_hash, record_hash)
			VALUES
				(%(name)s, NOW(), NOW(), %(user)s, %(user)s, 0,
				 %(timestamp)s, %(action)s, %(user)s, %(ip)s,
				 %(ref_doctype)s, %(ref_docname)s, %(data_json)s,
				 %(prev_hash)s, %(record_hash)s)
		""", {
			"name":        frappe.generate_hash(length=10),
			"user":        user,
			"timestamp":   timestamp,
			"action":      action,
			"ip":          getattr(frappe.local, "request_ip", None),
			"ref_doctype": ref_doctype,
			"ref_docname": ref_docname,
			"data_json":   data_json,
			"prev_hash":   last_hash,
			"record_hash": record_hash,
		})
		frappe.db.commit()

	except Exception:
		# El audit log nunca debe interrumpir el flujo principal
		frappe.log_error(frappe.get_traceback(), "Fuel Audit Log - Error al escribir")


def verify_chain():
	"""
	Verifica la integridad de la cadena de hash.
	Llamado por el scheduled job diario.
	Retorna True si la cadena es válida, False si fue manipulada.
	"""
	records = frappe.db.sql("""
		SELECT timestamp, action, user, ip_address,
		       ref_doctype, ref_docname, data_json,
		       prev_hash, record_hash
		FROM `tabFuel Audit Log`
		ORDER BY creation ASC
	""", as_dict=True)

	prev_hash = "GENESIS"

	for r in records:
		raw = (
			f"{r.prev_hash}|{r.timestamp}|{r.action}|{r.user}|"
			f"{r.ref_doctype}|{r.ref_docname}|{r.data_json}"
		)
		expected = hashlib.sha256(raw.encode()).hexdigest()

		if expected != r.record_hash:
			frappe.log_error(
				f"Cadena de auditoría comprometida en registro con prev_hash={r.prev_hash}",
				"Fuel Audit Log - Integridad comprometida"
			)
			return False

		prev_hash = r.record_hash

	return True