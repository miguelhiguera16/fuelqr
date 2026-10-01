// Copyright (c) 2026, FuelQR and contributors
// For license information, please see license.txt

// RF-19 — Filtros: Fecha, Empleado, Vehículo, Departamento, Tipo combustible, Estado ticket.

frappe.query_reports["Fuel Ticket Summary"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Desde"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("Hasta"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Empleado"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "vehicle",
			label: __("Vehículo"),
			fieldtype: "Link",
			options: "Vehicle",
		},
		{
			fieldname: "department",
			label: __("Departamento"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "fuel_item",
			label: __("Tipo de Combustible"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({
				filters: { is_stock_item: 1 }
			}),
		},
		{
			fieldname: "station",
			label: __("Estación"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { is_group: 0 }
			}),
		},
		{
			fieldname: "status",
			label: __("Estado del Ticket"),
			fieldtype: "Select",
			options: "\nCreado\nEnviado\nPendiente\nPróximo a Vencer\nVencido\nConsumido\nAnulado",
		},
	],
};