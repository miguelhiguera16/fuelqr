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
		// Indicador de color según estado
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
		frm.page.set_indicator(frm.doc.status, color);

		// Barra de progreso
		if (frm.doc.qty_authorized && frm.doc.docstatus === 1) {
			const pct = Math.round((frm.doc.qty_dispatched / frm.doc.qty_authorized) * 100);
			const barColor = pct >= 100 ? "green" : pct >= 75 ? "orange" : "blue";
			frm.dashboard.add_progress(
				__("Consumo: {0} / {1} {2}", [
					frm.doc.qty_dispatched,
					frm.doc.qty_authorized,
					frm.doc.uom
				]),
				pct,
				barColor
			);
		}

		// Botón reenviar email
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