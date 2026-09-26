# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import hashlib
import hmac
import base64
import secrets
import uuid

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_days, get_datetime


class FuelTicket(Document):

	def before_insert(self):
		self._set_uuid()
		self._set_issued_on()
		self._set_qty_remaining()

	def before_submit(self):
		self._generate_qr_token()
		self._generate_short_code()
		self.status = "Creado"

	def on_cancel(self):
		if not self.cancel_reason:
			frappe.throw(_("Debe especificar un motivo de anulación."))
		self.db_set("status", "Anulado")

	# ─── Helpers privados ───────────────────────────────────────────

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
		  n = nonce aleatorio de 8 bytes
		"""
		settings = frappe.get_single("Fuel Settings")
		kid = settings.qr_key_id or "k1"

		# Obtener la llave secreta desde site_config.json
		import json
		fuel_qr_keys = frappe.conf.get("fuel_qr_keys", {})
		if isinstance(fuel_qr_keys, str):
			fuel_qr_keys = json.loads(fuel_qr_keys)
		secret = fuel_qr_keys.get(kid)

		if not secret:
			frappe.throw(
				_("Llave QR '{0}' no encontrada en site_config.json bajo fuel_qr_keys.").format(kid)
			)

		# Construir el payload
		import json
		expires_ts = int(get_datetime(self.expires_on).timestamp())
		nonce = secrets.token_hex(8)

		payload_dict = {
			"t": self.uuid,
			"s": self.name,
			"e": expires_ts,
			"n": nonce
		}
		payload_json = json.dumps(payload_dict, separators=(",", ":"))
		payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

		# Calcular la firma HMAC-SHA256
		message = f"FT1.{kid}.{payload_b64}"

		import binascii
		try:
			secret_bytes = base64.b64decode(secret)
		except (ValueError, binascii.Error):
			secret_bytes = base64.urlsafe_b64decode(secret + "==")

		sig = hmac.new(secret_bytes, message.encode(), hashlib.sha256).digest()
		sig_b64 = base64.urlsafe_b64encode(sig[:16]).decode().rstrip("=")  # 16 bytes truncado

		self.qr_token = f"FT1.{kid}.{payload_b64}.{sig_b64}"

	def _generate_short_code(self):
		"""
		Genera un código corto de 10 caracteres para uso en SMS.
		Alfanumérico sin caracteres ambiguos (sin 0, O, 1, I, l).
		Guarda el hash SHA256 en short_code_hash para búsqueda en DB.
		"""
		alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
		code = "".join(secrets.choice(alphabet) for _ in range(10))
		self.short_code = code

		# Hash con salt del sitio para almacenamiento seguro
		site_salt = frappe.conf.get("db_password", "default_salt")
		hash_input = f"{site_salt}:{code}".encode()
		self.short_code_hash = hashlib.sha256(hash_input).hexdigest()


def create_from_request(fuel_request):
	from frappe.utils import get_datetime, add_days

	ticket = frappe.new_doc("Fuel Ticket")
	ticket.fuel_request    = fuel_request.name
	ticket.employee        = fuel_request.employee
	ticket.department      = fuel_request.department
	ticket.vehicle         = fuel_request.vehicle
	ticket.fuel_item       = fuel_request.fuel_item
	ticket.station         = fuel_request.station
	ticket.qty_authorized  = fuel_request.qty_authorized
	ticket.qty_dispatched  = 0
	ticket.qty_remaining   = fuel_request.qty_authorized
	ticket.uom             = fuel_request.uom

	# Asegurar que expires_on sea un datetime válido
	if fuel_request.valid_until:
		ticket.expires_on = get_datetime(str(fuel_request.valid_until) + " 23:59:59")
	else:
		ticket.expires_on = get_datetime(add_days(frappe.utils.today(), 3) + " 23:59:59")

	ticket.insert(ignore_permissions=True)
	ticket.submit()

	frappe.msgprint(
		_("Ticket {0} generado exitosamente.").format(ticket.name),
		indicator="green",
		alert=True
	)

	return ticket