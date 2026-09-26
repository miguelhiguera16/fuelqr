# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, add_days


class FuelRequest(Document):

	def before_save(self):
		self._set_valid_until()

	def validate(self):
		self._validate_vehicle()
		self._validate_employee()
		self._validate_qty()

	def on_submit(self):
		self.db_set("status", "Aprobada")
		self._create_fuel_ticket()

	def on_cancel(self):
		self.db_set("status", "Cancelada")
		self._cancel_linked_ticket()

	# ─── Helpers privados ───────────────────────────────────────────

	def _set_valid_until(self):
		"""Si no se especifica fecha de vencimiento, calcularla desde Fuel Settings."""
		if not self.valid_until:
			settings = frappe.get_single("Fuel Settings")
			self.valid_until = add_days(today(), settings.default_validity_days or 3)

	def _validate_vehicle(self):
		"""El vehículo debe existir y estar Activo."""
		status = frappe.db.get_value("Vehicle", self.vehicle, "status")
		if not status:
			frappe.throw(_("Vehículo {0} no encontrado.").format(self.vehicle))
		if status != "Activo":
			frappe.throw(
				_("El vehículo {0} no está activo. Estado actual: {1}").format(
					self.vehicle, status
				)
			)

	def _validate_employee(self):
		"""El empleado debe existir y estar Activo."""
		status = frappe.db.get_value("Employee", self.employee, "status")
		if not status:
			frappe.throw(_("Empleado {0} no encontrado.").format(self.employee))
		if status != "Active":
			frappe.throw(
				_("El empleado {0} no está activo. Estado actual: {1}").format(
					self.employee, status
				)
			)

	def _validate_qty(self):
		"""Cantidad autorizada debe ser positiva y no superar la capacidad del tanque."""
		if not self.qty_authorized or self.qty_authorized <= 0:
			frappe.throw(_("La cantidad autorizada debe ser mayor a cero."))

		tank_capacity = frappe.db.get_value("Vehicle", self.vehicle, "tank_capacity")
		if tank_capacity and self.qty_authorized > tank_capacity:
			frappe.throw(
				_("La cantidad autorizada ({0}) supera la capacidad del tanque del vehículo {1} ({2}).").format(
					self.qty_authorized, self.vehicle, tank_capacity
				)
			)

	def _create_fuel_ticket(self):
		"""Crea un Fuel Ticket al hacer submit de la solicitud aprobada."""
		from fuelqr.fuelqr.doctype.fuel_ticket.fuel_ticket import create_from_request
		create_from_request(self)

	def _cancel_linked_ticket(self):
		"""Cancela el Fuel Ticket vinculado si existe y no ha sido consumido."""
		ticket_name = frappe.db.get_value(
			"Fuel Ticket",
			{"fuel_request": self.name, "docstatus": 1},
			"name"
		)
		if not ticket_name:
			return

		ticket = frappe.get_doc("Fuel Ticket", ticket_name)

		if ticket.status == "Consumido":
			frappe.throw(
				_("No se puede cancelar la solicitud {0} porque el ticket {1} ya fue consumido.").format(
					self.name, ticket_name
				)
			)

		ticket.cancel_reason = _("Solicitud de origen {0} cancelada.").format(self.name)
		ticket.save(ignore_permissions=True)
		ticket.cancel()