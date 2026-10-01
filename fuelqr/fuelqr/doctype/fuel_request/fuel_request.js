frappe.ui.form.on("Fuel Request", {

	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("request_date", frappe.datetime.get_today());
			frm.set_value("request_type", "Manual");
		}
	},

	refresh(frm) {
		frm.set_query("station", () => {
			return {
				filters: {
					"disabled": 0,
					"is_group": 0,
				}
			};
		});

		// El vehículo se resuelve automáticamente desde el empleado
		frm.set_df_property("vehicle", "read_only", 1);
		frm.set_df_property("department", "read_only", 1);
		frm.set_df_property("fuel_item", "read_only", 1);
		frm.set_df_property("uom", "read_only", 1);
	},

	// Al seleccionar el empleado — busca su vehículo asignado y autocompleta todo
	employee(frm) {
		if (!frm.doc.employee) {
			frm.set_value("vehicle", "");
			frm.set_value("department", "");
			frm.set_value("fuel_item", "");
			frm.set_value("uom", "");
			return;
		}

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Vehicle",
				filters: { employee: frm.doc.employee },
				fields: ["name", "department", "fuel_item", "uom", "status", "tank_capacity", "license_plate"],
				limit_page_length: 1
			},
			callback(r) {
				if (!r.message || r.message.length === 0) {
					frappe.msgprint({
						title: __("Sin vehículo asignado"),
						message: __("El empleado {0} no tiene ningún vehículo asignado.", [frm.doc.employee]),
						indicator: "red"
					});
					frm.set_value("vehicle", "");
					frm.set_value("department", "");
					frm.set_value("fuel_item", "");
					frm.set_value("uom", "");
					return;
				}

				const v = r.message[0];

				frm.set_value("vehicle",     v.name);
				frm.set_value("department",  v.department);
				frm.set_value("fuel_item",   v.fuel_item);
				frm.set_value("uom",         v.uom);

				if (v.status && v.status !== "Activo") {
					frappe.msgprint({
						title: __("Vehículo no disponible"),
						message: __("El vehículo {0} ({1}) tiene estado: {2}", [v.name, v.license_plate, v.status]),
						indicator: "red"
					});
				}

				if (v.tank_capacity) {
					frm.set_df_property(
						"qty_authorized",
						"description",
						__("Capacidad del tanque de {0}: {1} {2}", [v.license_plate, v.tank_capacity, v.uom || ""])
					);
				}
			}
		});
	},

	// Al cambiar la fecha de solicitud — recalcula valid_until
	request_date(frm) {
		if (!frm.doc.request_date) return;

		frappe.db.get_single_value("Fuel Settings", "default_validity_days")
			.then(days => {
				if (days) {
					let valid = frappe.datetime.add_days(frm.doc.request_date, days);
					frm.set_value("valid_until", valid);
				}
			});
	},

	qty_authorized(frm) {
		if (!frm.doc.qty_authorized || !frm.doc.vehicle) return;

		frappe.db.get_value("Vehicle", frm.doc.vehicle, "tank_capacity", (r) => {
			if (r && r.tank_capacity && frm.doc.qty_authorized > r.tank_capacity) {
				frappe.msgprint({
					title: __("Cantidad excedida"),
					message: __("La cantidad {0} supera la capacidad del tanque ({1})", [
						frm.doc.qty_authorized, r.tank_capacity
					]),
					indicator: "orange"
				});
			}
		});
	}

});