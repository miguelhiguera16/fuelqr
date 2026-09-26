// Copyright (c) 2026, FuelQR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fuel Ticket", {

	refresh(frm) {
		frm._set_status_indicator(frm);
		frm._set_qty_progress(frm);

		// Botón para reenviar email si el ticket ya fue submitted
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Anulado") {
			frm.add_custom_button(__("Reenviar Email"), () => {
				frappe.call({
					method: "fuelqr.fuelqr.doctype.fuel_ticket.fuel_ticket_utils.send_ticket_email",
					args: { ticket_name: frm.doc.name },
					callback(r) {
						if (!r.exc) {
							frappe.show_alert({ message: __("Email enviado exitosamente"), indicator: "green" });
							frm.reload_doc();
						}
					}
				});
			}, __("Acciones"));
		}
	},

	// ─── Helpers del formulario ──────────────────────────────────

	_set_status_indicator(frm) {
		const colors = {
			"Creado":            "blue",
			"Enviado":           "blue",
			"Pendiente":         "yellow",
			"Próximo a Vencer":  "orange",
			"Vencido":           "red",
			"Consumido":         "green",
			"Anulado":           "grey"
		};
		const color = colors[frm.doc.status] || "grey";
		frm.set_indicator_formatter("status", () => color);
	},

	_set_qty_progress(frm) {
		// Muestra una barra de progreso de consumo si el ticket tiene despachos
		if (!frm.doc.qty_authorized || frm.doc.docstatus !== 1) return;

		const pct = Math.round((frm.doc.qty_dispatched / frm.doc.qty_authorized) * 100);
		const color = pct >= 100 ? "green" : pct >= 75 ? "orange" : "blue";

		frm.dashboard.add_progress(
			__("Consumo: {0} / {1} {2}", [
				frm.doc.qty_dispatched,
				frm.doc.qty_authorized,
				frm.doc.uom
			]),
			pct,
			color
		);
	}

});