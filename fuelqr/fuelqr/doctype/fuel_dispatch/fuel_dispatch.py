# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from fuelqr.fuelqr.doctype.fuel_audit_log.fuel_audit_log import write_log

class FuelDispatch(Document):

	def before_insert(self):
		self._set_scanned_at()
		self._set_dispatcher()

	def validate(self):
		self._validate_ticket()
		self._validate_station()
		self._validate_qty()

	def on_submit(self):
		self._consume_ticket_qty()
		self._create_stock_entry()
		self._create_vehicle_log()
		write_log(
			action="Despachar",
			ref_doctype="Fuel Dispatch",
			ref_docname=self.name,
			data={
				"fuel_ticket": self.fuel_ticket,
				"vehicle": self.vehicle,
				"employee": self.employee,
				"qty_dispatched": self.qty_dispatched,
				"station": self.station,
				"identity_method": self.identity_method,
				"odometer": self.odometer,
			}
		)

	def on_cancel(self):
		self._reverse_ticket_qty()
		self._cancel_stock_entry()
		write_log(
			action="Cancelar",
			ref_doctype="Fuel Dispatch",
			ref_docname=self.name,
			data={
				"fuel_ticket": self.fuel_ticket,
				"qty_dispatched": self.qty_dispatched,
			}
		)

	# ─── Helpers privados ───────────────────────────────────────────

	def _set_scanned_at(self):
		if not self.scanned_at:
			self.scanned_at = now_datetime()

	def _set_dispatcher(self):
		if not self.dispatcher:
			self.dispatcher = frappe.session.user

	def _validate_ticket(self):
		"""El ticket debe existir, estar submitted y en estado válido para despacho."""
		ticket = frappe.get_doc("Fuel Ticket", self.fuel_ticket)

		if ticket.docstatus != 1:
			frappe.throw(_("El ticket {0} no está activo.").format(self.fuel_ticket))

		valid_statuses = ["Creado", "Enviado", "Pendiente", "Próximo a Vencer"]
		if ticket.status not in valid_statuses:
			frappe.throw(
				_("El ticket {0} no puede ser despachado. Estado actual: {1}").format(
					self.fuel_ticket, ticket.status
				)
			)

	def _validate_station(self):
		"""La estación del despacho debe coincidir con la del ticket."""
		ticket_station = frappe.db.get_value("Fuel Ticket", self.fuel_ticket, "station")
		if self.station != ticket_station:
			frappe.throw(
				_("La estación del despacho ({0}) no coincide con la del ticket ({1}).").format(
					self.station, ticket_station
				)
			)

	def _validate_qty(self):
		"""La cantidad despachada no puede superar la cantidad restante más la tolerancia."""
		if not self.qty_dispatched or self.qty_dispatched <= 0:
			frappe.throw(_("La cantidad despachada debe ser mayor a cero."))

		ticket = frappe.get_doc("Fuel Ticket", self.fuel_ticket)
		settings = frappe.get_single("Fuel Settings")
		tolerance_pct = settings.dispatch_tolerance_pct or 0
		max_qty = ticket.qty_remaining * (1 + tolerance_pct / 100)

		if self.qty_dispatched > max_qty:
			frappe.throw(
				_("La cantidad despachada ({0}) supera la cantidad restante del ticket ({1}) más la tolerancia permitida ({2}%).").format(
					self.qty_dispatched, ticket.qty_remaining, tolerance_pct
				)
			)

	def _consume_ticket_qty(self):
		frappe.db.sql("""
			UPDATE `tabFuel Ticket`
			SET
				qty_dispatched = qty_dispatched + %(qty)s,
				qty_remaining  = qty_remaining  - %(qty)s,
				modified       = NOW(),
				modified_by    = %(user)s
			WHERE
				name      = %(ticket)s
				AND docstatus = 1
				AND status IN ('Creado', 'Enviado', 'Pendiente', 'Próximo a Vencer')
				AND qty_remaining >= %(qty)s
		""", {
			"qty":    self.qty_dispatched,
			"ticket": self.fuel_ticket,
			"user":   frappe.session.user
		})

		# Verificar que el update realmente afectó el ticket
		ticket_data = frappe.db.get_value(
			"Fuel Ticket",
			self.fuel_ticket,
			["qty_remaining", "qty_dispatched", "status"],
			as_dict=True
		)

		# Si qty_dispatched no cambió, el WHERE no se cumplió
		expected_dispatched = (ticket_data.qty_remaining + self.qty_dispatched)
		if ticket_data.qty_dispatched < self.qty_dispatched:
			frappe.throw(
				_("No se pudo consumir el ticket {0}. Verifique el estado y saldo disponible.").format(
					self.fuel_ticket
				)
			)

		# Cambiar estado según saldo restante
		if ticket_data.qty_remaining <= 0:
			frappe.db.set_value("Fuel Ticket", self.fuel_ticket, "status", "Consumido")
		elif ticket_data.status in ["Creado", "Enviado"]:
			frappe.db.set_value("Fuel Ticket", self.fuel_ticket, "status", "Pendiente")

	def _create_stock_entry(self):
		"""Crea un Stock Entry tipo Material Issue para descontar el inventario."""
		ticket = frappe.get_doc("Fuel Ticket", self.fuel_ticket)

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.posting_date = frappe.utils.today()
		se.posting_time = frappe.utils.nowtime()
		se.remarks = _("Despacho de combustible - Ticket {0}").format(self.fuel_ticket)

		se.append("items", {
			"item_code":         ticket.fuel_item,
			"qty":               self.qty_dispatched,
			"uom":               ticket.uom,
			"stock_uom":         ticket.uom,
			"conversion_factor": 1,
			"s_warehouse":       self.station,
		})

		se.insert(ignore_permissions=True)
		se.submit()

		self.db_set("stock_entry", se.name)

	def _create_vehicle_log(self):
		"""Crea un Vehicle Log con la lectura del odómetro si fue proporcionada."""
		if not self.odometer:
			return

		vl = frappe.new_doc("Vehicle Log")
		vl.license_plate = self.vehicle
		vl.date = frappe.utils.today()
		vl.odometer = self.odometer
		vl.fuel_qty = self.qty_dispatched
		vl.employee = self.employee

		vl.insert(ignore_permissions=True)
		self.db_set("vehicle_log", vl.name)

	def _reverse_ticket_qty(self):
		"""Al cancelar el despacho, devuelve la cantidad al ticket."""
		ticket = frappe.get_doc("Fuel Ticket", self.fuel_ticket)

		if ticket.docstatus != 1:
			return

		frappe.db.sql("""
			UPDATE `tabFuel Ticket`
			SET
				qty_dispatched = qty_dispatched - %(qty)s,
				qty_remaining  = qty_remaining  + %(qty)s,
				modified       = NOW(),
				modified_by    = %(user)s
			WHERE name = %(ticket)s
		""", {
			"qty":    self.qty_dispatched,
			"ticket": self.fuel_ticket,
			"user":   frappe.session.user
		})

		# Si el ticket estaba Consumido, regresa a Pendiente
		current_status = frappe.db.get_value("Fuel Ticket", self.fuel_ticket, "status")
		if current_status == "Consumido":
			frappe.db.set_value("Fuel Ticket", self.fuel_ticket, "status", "Pendiente")

	def _cancel_stock_entry(self):
		"""Cancela el Stock Entry asociado."""
		if not self.stock_entry:
			return

		se = frappe.get_doc("Stock Entry", self.stock_entry)
		if se.docstatus == 1:
			se.cancel()