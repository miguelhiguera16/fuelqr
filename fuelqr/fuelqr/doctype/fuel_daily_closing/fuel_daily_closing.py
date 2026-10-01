# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from fuelqr.fuelqr.doctype.fuel_audit_log.fuel_audit_log import write_log


class FuelDailyClosing(Document):

	def before_insert(self):
		if not self.date:
			self.date = today()
		if not self.closed_by:
			self.closed_by = frappe.session.user
		if not self.status:
			self.status = "Borrador"

	def validate(self):
		self._load_dispatches()
		self._load_inventory()
		self._calculate_difference()

	def before_submit(self):
		if self.actual_closing_qty in (None, ""):
			frappe.throw(
				_("Debe ingresar el inventario físico real (conteo en estación) antes de cerrar.")
			)

	def on_submit(self):
		write_log(
			action="Cierre Diario",
			ref_doctype="Fuel Daily Closing",
			ref_docname=self.name,
			data={
				"date": str(self.date),
				"station": self.station,
				"total_dispatches": self.total_dispatches,
				"total_qty_dispatched": self.total_qty_dispatched,
				"closing_qty": self.closing_qty,
				"difference": self.difference,
			}
		)

	def on_cancel(self):
		self.db_set("status", "Borrador")

	def _load_dispatches(self):
		"""Carga todos los despachos del día y estación seleccionados."""
		if not self.date or not self.station:
			return

		dispatches = frappe.db.sql("""
			SELECT
				d.name,
				d.fuel_ticket,
				d.employee,
				d.vehicle,
				d.fuel_item,
				d.qty_dispatched,
				d.uom,
				d.identity_method,
				d.scanned_at,
				d.dispatcher
			FROM `tabFuel Dispatch` d
			WHERE d.station    = %(station)s
			AND d.docstatus  = 1
			AND DATE(d.scanned_at) = %(date)s
			ORDER BY d.scanned_at ASC
		""", {"station": self.station, "date": self.date}, as_dict=True)

		if self.fuel_item:
			dispatches = [d for d in dispatches if d.fuel_item == self.fuel_item]

		self.dispatches = []
		for d in dispatches:
			self.append("dispatches", {
				"fuel_dispatch":   d.name,
				"fuel_ticket":     d.fuel_ticket,
				"employee":        d.employee,
				"vehicle":         d.vehicle,
				"fuel_item":       d.fuel_item,
				"qty_dispatched":  d.qty_dispatched,
				"uom":             d.uom,
				"identity_method": d.identity_method,
				"dispatched_at":   d.scanned_at,
				"user":            d.dispatcher,
			})

		self.total_dispatches     = len(dispatches)
		self.total_qty_dispatched = sum(flt(d.qty_dispatched) for d in dispatches)
		self.dispatched_qty       = self.total_qty_dispatched

	def _load_inventory(self):
		"""Carga el inventario inicial, recepciones y final de la estación."""
		if not self.date or not self.station:
			return

		fuel_item = self.fuel_item or None

		# Inventario al inicio del día (stock a las 00:00:00 de ese día)
		self.opening_qty = self._get_stock_qty(
			self.station, fuel_item, self.date, time="00:00:00"
		)

		# Recepciones del día (Stock Entry tipo Material Receipt)
		self.received_qty = self._get_receipts(self.station, fuel_item, self.date)

		# Inventario final actual
		self.closing_qty = self._get_stock_qty(self.station, fuel_item)

	def _get_stock_qty(self, warehouse, item_code, date=None, time="23:59:59"):
		"""Obtiene el stock actual o histórico de un warehouse."""

		if date:
			bin_data = frappe.db.sql("""
				SELECT COALESCE(sle.qty_after_transaction, 0)
				FROM "tabStock Ledger Entry" sle
				WHERE sle.warehouse = %(warehouse)s
				AND sle.docstatus = 1
				AND (
					sle.posting_date < %(date)s
					OR (sle.posting_date = %(date)s AND sle.posting_time <= %(time)s)
				)
				{item_filter}
				ORDER BY sle.posting_date DESC, sle.posting_time DESC
				LIMIT 1
			""".format(
				item_filter="AND sle.item_code = %(item_code)s" if item_code else ""
			), {
				"warehouse": warehouse,
				"date": date,
				"time": time,
				"item_code": item_code,
			})
			return flt(bin_data[0][0]) if bin_data else 0.0
		else:
			result = frappe.db.sql("""
				SELECT COALESCE(SUM(actual_qty), 0)
				FROM "tabBin"
				WHERE warehouse = %(warehouse)s
				{item_filter}
			""".format(
				item_filter="AND item_code = %(item_code)s" if item_code else ""
			), {"warehouse": warehouse, "item_code": item_code})
			return flt(result[0][0]) if result else 0.0

	def _get_receipts(self, warehouse, item_code, date):
		"""Suma las recepciones de combustible del día."""
		filters = {
			"warehouse": warehouse,
			"date": date,
			"item_code": item_code,
		}
		result = frappe.db.sql("""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.docstatus     = 1
			AND se.posting_date  = %(date)s
			AND sed.t_warehouse  = %(warehouse)s
			AND se.stock_entry_type = 'Entrada de Material'
			{item_filter}
		""".format(
			item_filter="AND sed.item_code = %(item_code)s" if item_code else ""
		), filters)
		return flt(result[0][0]) if result else 0.0

	def _calculate_difference(self):
		"""
		Diferencia = Conteo físico real − Inventario calculado por el sistema.
		Positivo: hay más combustible del que el sistema espera (posible error de registro).
		Negativo: falta combustible (merma, fuga, despacho no registrado).
		Mientras no se haya digitado el conteo físico, se muestra 0 como referencia.
		"""
		if self.actual_closing_qty not in (None, ""):
			self.difference = flt(self.actual_closing_qty) - flt(self.closing_qty)
		else:
			self.difference = 0


@frappe.whitelist()
def get_closing_preview(date, station, fuel_item=None):
	"""Endpoint para previsualizar el cierre antes de crearlo."""
	doc = frappe.new_doc("Fuel Daily Closing")
	doc.date       = date
	doc.station    = station
	doc.fuel_item  = fuel_item
	doc.closed_by  = frappe.session.user
	doc._load_dispatches()
	doc._load_inventory()
	doc._calculate_difference()

	return {
		"total_dispatches":     doc.total_dispatches,
		"total_qty_dispatched": doc.total_qty_dispatched,
		"opening_qty":          doc.opening_qty,
		"received_qty":         doc.received_qty,
		"closing_qty":          doc.closing_qty,
		"difference":           doc.difference,
		"dispatches":           [d.as_dict() for d in doc.dispatches],
	}