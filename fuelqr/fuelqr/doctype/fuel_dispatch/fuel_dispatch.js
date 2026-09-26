// Copyright (c) 2026, FuelQR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fuel Dispatch", {

	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("scanned_at", frappe.datetime.now_datetime());
			frm.set_value("dispatcher", frappe.session.user);
			frm.set_value("identity_method", "Cédula (últimos 4 dígitos)");
		}
	},

	refresh(frm) {
		// Mostrar links a los documentos ERP generados
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Ver Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			}, __("Documentos"));
		}
		if (frm.doc.vehicle_log) {
			frm.add_custom_button(__("Ver Vehicle Log"), () => {
				frappe.set_route("Form", "Vehicle Log", frm.doc.vehicle_log);
			}, __("Documentos"));
		}
	},

	// Al seleccionar el ticket — autocompleta todos los campos
	fuel_ticket(frm) {
		if (!frm.doc.fuel_ticket) return;

		frappe.db.get_value(
			"Fuel Ticket",
			frm.doc.fuel_ticket,
			["vehicle", "employee", "department", "fuel_item", "uom",
			 "qty_authorized", "qty_remaining", "station", "status", "expires_on"],
			(r) => {
				if (!r) return;

				frm.set_value("vehicle",       r.vehicle);
				frm.set_value("employee",      r.employee);
				frm.set_value("fuel_item",     r.fuel_item);
				frm.set_value("uom",           r.uom);
				frm.set_value("qty_authorized", r.qty_authorized);
				frm.set_value("station",       r.station);

				// Mostrar cantidad restante como referencia
				frm.set_df_property(
					"qty_dispatched",
					"description",
					__("Cantidad restante en el ticket: {0} {1}", [r.qty_remaining, r.uom])
				);

				// Advertencia si el ticket está próximo a vencer o vencido
				if (r.status === "Próximo a Vencer") {
					frappe.show_alert({
						message: __("El ticket vence el {0}", [r.expires_on]),
						indicator: "orange"
					});
				}
				if (r.status === "Vencido") {
					frappe.msgprint({
						title: __("Ticket vencido"),
						message: __("Este ticket venció el {0} y no puede ser despachado.", [r.expires_on]),
						indicator: "red"
					});
				}
			}
		);
	},

	// Validación visual de cantidad antes de guardar
	qty_dispatched(frm) {
		if (!frm.doc.qty_dispatched || !frm.doc.fuel_ticket) return;

		frappe.db.get_value("Fuel Ticket", frm.doc.fuel_ticket, "qty_remaining", (r) => {
			if (r && frm.doc.qty_dispatched > r.qty_remaining) {
				frappe.show_alert({
					message: __("La cantidad supera el saldo disponible del ticket ({0})", [r.qty_remaining]),
					indicator: "orange"
				});
			}
		});
	}

});