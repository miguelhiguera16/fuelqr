# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import base64
import binascii
import hashlib
import hmac
import io
import json
import re
import secrets
import uuid

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, escape_html, flt, get_datetime, now_datetime

from fuelqr.fuelqr.doctype.fuel_audit_log.fuel_audit_log import write_log

NOTIFY_METHOD = "fuelqr.fuelqr.doctype.fuel_ticket.fuel_ticket.send_ticket_notifications"
ACTIVE_STATUSES = ("Creado", "Enviado", "Pendiente", "Próximo a Vencer")


class FuelTicket(Document):

	# ── Hooks del documento ──────────────────────────────────────────────────

	def before_insert(self):
		self._set_uuid()
		self._set_issued_on()
		self._set_qty_remaining()

	def before_submit(self):
		self._generate_qr_token()
		self._generate_short_code()
		self._generate_qr_image()
		self.status = "Creado"

	def on_submit(self):
		write_log(
			action="Crear",
			ref_doctype="Fuel Ticket",
			ref_docname=self.name,
			data={
				"employee": self.employee,
				"vehicle": self.vehicle,
				"qty_authorized": self.qty_authorized,
				"fuel_item": self.fuel_item,
				"station": self.station,
				"expires_on": str(self.expires_on),
			},
		)
		self.queue_notifications()

	def on_cancel(self):
		if not self.cancel_reason:
			frappe.throw(_("Debe especificar un motivo de anulación."))
		self.db_set("status", "Anulado")
		self._invalidate_qr()
		write_log(
			action="Cancelar",
			ref_doctype="Fuel Ticket",
			ref_docname=self.name,
			data={"cancel_reason": self.cancel_reason},
		)

	# ── Ciclo de vida del QR (un solo uso) ───────────────────────────────────

	def rotate_qr(self):
		"""
		Se llama después de cada despacho (y de su anulación) con el ticket
		recargado desde la base de datos.

		- Si quedan galones: el QR y el código corto actuales se destruyen y
		  se genera un QR nuevo, que se envía al empleado.
		- Si el saldo es cero: el QR se destruye y no se genera otro.
		"""
		if self.docstatus != 1 or self.status == "Anulado":
			return

		if flt(self.qty_remaining) > 0:
			self._regenerate_qr()
		else:
			self._invalidate_qr()
			write_log(
				action="Invalidar QR",
				ref_doctype="Fuel Ticket",
				ref_docname=self.name,
				data={"motivo": "Ticket consumido"},
			)

	def queue_notifications(self):
		send_ticket_notifications(self.name)

	def _regenerate_qr(self):
		old_url = self.qr_image

		# Todo se genera primero; el QR anterior se elimina al final.
		self._generate_qr_token()
		self._generate_short_code()
		self._generate_qr_image(suffix=now_datetime().strftime("%Y%m%d%H%M%S"))

		new_values = {
			"qr_token": self.qr_token,
			"short_code": self.short_code,
			"short_code_hash": self.short_code_hash,
			"qr_image": self.qr_image,
		}

		self._delete_qr_file(old_url)
		# db_set porque el ticket ya está enviado (docstatus 1): save() fallaría.
		self.db_set(new_values)

		write_log(
			action="Regenerar QR",
			ref_doctype="Fuel Ticket",
			ref_docname=self.name,
			data={"qty_remaining": self.qty_remaining},
		)
		self.queue_notifications()

	def _invalidate_qr(self):
		old_url = self.qr_image
		self._delete_qr_file(old_url)
		self.db_set({
			"qr_token": None,
			"short_code": None,
			"short_code_hash": None,
			"qr_image": None,
		})

	def _delete_qr_file(self, file_url):
		if not file_url:
			return
		try:
			file_name = frappe.db.get_value(
				"File",
				{"file_url": file_url, "attached_to_doctype": "Fuel Ticket"},
				"name",
			)
			if file_name:
				frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Fuel Ticket - no se pudo borrar el QR anterior",
			)

	# ── Generación de identificadores ────────────────────────────────────────

	def _set_uuid(self):
		"""Genera un UUID único para este ticket."""
		if not self.uuid:
			self.uuid = str(uuid.uuid4())

	def _set_issued_on(self):
		"""Establece la fecha y hora de emisión."""
		if not self.issued_on:
			self.issued_on = now_datetime()

	def _set_qty_remaining(self):
		"""Inicializa la cantidad restante igual a la autorizada."""
		self.qty_dispatched = 0
		self.qty_remaining = self.qty_authorized

	def _generate_qr_token(self):
		"""
		Genera el token QR firmado con HMAC-SHA256.
		Formato: FT1.<kid>.<payload_b64url>.<sig_b64url>

		El payload contiene:
		  t = uuid del ticket (identificador opaco)
		  s = nombre del ticket (serie)
		  e = unix timestamp de expiración
		  n = nonce aleatorio (distinto en cada regeneración)
		"""
		settings = frappe.get_single("Fuel Settings")
		kid = settings.qr_key_id or "k1"

		# La llave secreta vive en site_config.json, nunca en la base de datos
		fuel_qr_keys = frappe.conf.get("fuel_qr_keys", {})
		if isinstance(fuel_qr_keys, str):
			fuel_qr_keys = json.loads(fuel_qr_keys)
		secret = fuel_qr_keys.get(kid)

		if not secret:
			frappe.throw(
				_("Llave QR '{0}' no encontrada en site_config.json bajo fuel_qr_keys.").format(kid)
			)

		expires_ts = int(get_datetime(self.expires_on).timestamp())
		payload_dict = {
			"t": self.uuid,
			"s": self.name,
			"e": expires_ts,
			"n": secrets.token_hex(8),
		}
		payload_json = json.dumps(payload_dict, separators=(",", ":"))
		payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

		message = f"FT1.{kid}.{payload_b64}"

		try:
			secret_bytes = base64.b64decode(secret)
		except (ValueError, binascii.Error):
			secret_bytes = base64.urlsafe_b64decode(secret + "==")

		sig = hmac.new(secret_bytes, message.encode(), hashlib.sha256).digest()
		sig_b64 = base64.urlsafe_b64encode(sig[:16]).decode().rstrip("=")

		self.qr_token = f"FT1.{kid}.{payload_b64}.{sig_b64}"

	def _generate_short_code(self):
		"""
		Genera un código corto de 10 caracteres para SMS.
		Alfanumérico sin caracteres ambiguos (sin 0, O, 1, I, l).
		Guarda el hash SHA256 en short_code_hash para búsqueda en DB.
		"""
		alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
		code = "".join(secrets.choice(alphabet) for _ in range(10))
		self.short_code = code

		site_salt = frappe.conf.get("db_password", "default_salt")
		hash_input = f"{site_salt}:{code}".encode()
		self.short_code_hash = hashlib.sha256(hash_input).hexdigest()

	def _generate_qr_image(self, suffix=""):
		"""Genera la imagen PNG del QR y la adjunta al ticket como archivo privado."""
		import qrcode

		qr = qrcode.QRCode(
			version=None,
			error_correction=qrcode.constants.ERROR_CORRECT_M,
			box_size=10,
			border=4,
		)
		qr.add_data(self.qr_token)
		qr.make(fit=True)

		img = qr.make_image(fill_color="black", back_color="white")

		buffer = io.BytesIO()
		img.save(buffer, format="PNG")
		buffer.seek(0)

		# El sufijo evita choques de nombre cuando se regenera el QR
		filename = f"qr_{self.name}_{suffix}.png" if suffix else f"qr_{self.name}.png"
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": filename,
			"attached_to_doctype": "Fuel Ticket",
			"attached_to_name": self.name,
			"attached_to_field": "qr_image",
			"is_private": 1,
			"content": buffer.read(),
		})
		file_doc.save(ignore_permissions=True)

		self.qr_image = file_doc.file_url


def create_from_request(fuel_request):
	ticket = frappe.new_doc("Fuel Ticket")
	ticket.fuel_request = fuel_request.name
	ticket.employee = fuel_request.employee
	ticket.department = fuel_request.department
	ticket.vehicle = fuel_request.vehicle
	ticket.fuel_item = fuel_request.fuel_item
	ticket.station = fuel_request.station
	ticket.qty_authorized = fuel_request.qty_authorized
	ticket.qty_dispatched = 0
	ticket.qty_remaining = fuel_request.qty_authorized
	ticket.uom = fuel_request.uom

	if fuel_request.valid_until:
		ticket.expires_on = get_datetime(str(fuel_request.valid_until) + " 23:59:59")
	else:
		ticket.expires_on = get_datetime(add_days(frappe.utils.today(), 3) + " 23:59:59")

	ticket.insert(ignore_permissions=True)
	ticket.submit()

	frappe.msgprint(
		_("Ticket {0} generado exitosamente.").format(ticket.name),
		indicator="green",
		alert=True,
	)

	return ticket


# ── Notificaciones (RF-09): email con QR y SMS con código corto ──────────────

def send_ticket_notifications(ticket_name):
	"""Trabajo en segundo plano. Un fallo aquí nunca afecta al despacho."""
	ticket = frappe.get_doc("Fuel Ticket", ticket_name)

	if ticket.docstatus != 1 or not ticket.qr_token or ticket.status not in ACTIVE_STATUSES:
		return

	emp = frappe.db.get_value(
		"Employee",
		ticket.employee,
		["employee_name", "company_email", "personal_email", "cell_number", "user_id"],
		as_dict=True,
	) or frappe._dict()

	email_sent = _send_email(ticket, emp)
	sms_sent = _send_sms(ticket, emp)

	if (email_sent or sms_sent) and ticket.status == "Creado":
		ticket.db_set("status", "Enviado")

	if email_sent and frappe.get_meta("Fuel Ticket").has_field("sent_email_on"):
		ticket.db_set("sent_email_on", now_datetime())


def _send_email(ticket, emp):
	recipient = emp.get("company_email") or emp.get("personal_email")
	if not recipient and emp.get("user_id"):
		recipient = frappe.db.get_value("User", emp.get("user_id"), "email")
	if not recipient:
		return False

	try:
		attachments = None
		if ticket.qr_image:
			file_doc = frappe.get_doc("File", {"file_url": ticket.qr_image})
			attachments = [{"fname": f"{ticket.name}.png", "fcontent": file_doc.get_content()}]

		expires = get_datetime(ticket.expires_on).strftime("%d/%m/%Y %H:%M")
		rows = [
			("Ticket", ticket.name),
			("Vehículo", ticket.vehicle),
			("Combustible", ticket.fuel_item),
			("Estación", ticket.station),
			("Saldo disponible", f"{flt(ticket.qty_remaining):g} {ticket.uom}"),
			("Vence", expires),
			("Código corto", ticket.short_code),
		]
		table = "".join(
			f"<tr><td style='padding:4px 12px 4px 0;color:#8a6a3a'>{escape_html(k)}</td>"
			f"<td style='padding:4px 0'><b>{escape_html(str(v))}</b></td></tr>"
			for k, v in rows
		)
		message = (
			f"<p>Hola {escape_html(emp.get('employee_name') or '')},</p>"
			"<p>Este es tu ticket de combustible. Presenta el QR adjunto al despachador. "
			"Cada QR se puede usar una sola vez: si queda saldo, recibirás uno nuevo "
			"después del despacho.</p>"
			f"<table>{table}</table>"
		)

		frappe.sendmail(
			recipients=[recipient],
			subject=_("Ticket de combustible {0}").format(ticket.name),
			message=message,
			attachments=attachments,
			reference_doctype="Fuel Ticket",
			reference_name=ticket.name,
			delayed=False,
		)
		return True
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Fuel Ticket - email {ticket.name}")
		return False


def _send_sms(ticket, emp):
	"""
	Envía el código corto por SMS o WhatsApp, según Twilio Settings.
	Las credenciales viven en el doctype Twilio Settings, no en site_config.json.
	"""
	settings = frappe.get_cached_doc("Twilio Settings")

	if not settings.enabled:
		return False

	sid = settings.account_sid
	auth_token = settings.get_password("auth_token", raise_exception=False)
	to_number = _to_e164(emp.get("cell_number"))

	if not (sid and auth_token and to_number):
		return False

	if settings.use_whatsapp:
		if not settings.whatsapp_from:
			return False
		from_number = settings.whatsapp_from
		to_number = f"whatsapp:{to_number}"
	else:
		if not settings.from_number:
			return False
		from_number = settings.from_number

	expires = get_datetime(ticket.expires_on).strftime("%d/%m/%Y")
	body = (
		f"FuelQR {ticket.name}: codigo {ticket.short_code}. "
		f"Saldo {flt(ticket.qty_remaining):g} {ticket.uom}. Vence {expires}."
	)

	try:
		response = requests.post(
			f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
			data={"To": to_number, "From": from_number, "Body": body},
			auth=(sid, auth_token),
			timeout=15,
		)
		if response.status_code >= 300:
			frappe.log_error(response.text, f"Fuel Ticket - SMS {ticket.name}")
			return False
		return True
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Fuel Ticket - SMS {ticket.name}")
		return False


def _to_e164(number):
	"""Convierte un teléfono dominicano (809/829/849) al formato +1XXXXXXXXXX."""
	if not number:
		return None
	digits = re.sub(r"\D", "", number)
	if number.strip().startswith("+"):
		return "+" + digits
	if len(digits) == 10:
		return "+1" + digits
	if len(digits) == 11 and digits.startswith("1"):
		return "+" + digits
	return None


@frappe.whitelist()
def resend_notifications(ticket_name):
	"""Botón «Reenviar» del formulario: reenvía el QR vigente, sin regenerarlo."""
	frappe.only_for(("Fuel Manager", "Fuel Supervisor", "System Manager"))

	ticket = frappe.get_doc("Fuel Ticket", ticket_name)
	if ticket.docstatus != 1 or ticket.status not in ACTIVE_STATUSES or not ticket.qr_token:
		frappe.throw(_("Este ticket ya no tiene un QR vigente para reenviar."))

	frappe.enqueue(NOTIFY_METHOD, queue="short", ticket_name=ticket.name)
	return {"success": True}