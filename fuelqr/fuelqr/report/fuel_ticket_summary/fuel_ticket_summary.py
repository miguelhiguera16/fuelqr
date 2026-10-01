# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

# RF-19 — Reportes filtrables por: Fecha, Empleado, Vehículo, Departamento,
#         Tipo combustible, Estado ticket.
# RF-20 — Exportación Excel / CSV / PDF: nativa de Frappe en cualquier
#         Script Report, no requiere código adicional.
#
# Visibilidad: Fuel Manager y Fuel Supervisor ven todos los tickets.
# Cualquier otro rol (Auditor, Consulta, etc.) solo ve los tickets
# del empleado vinculado a su propio usuario.

import frappe
from frappe import _
from frappe.utils import flt

FULL_ACCESS_ROLES = {"Fuel Manager", "Fuel Supervisor", "System Manager"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    restricted_employee = get_employee_restriction()

    columns = get_columns()
    data = get_data(filters, restricted_employee)
    chart = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_employee_restriction():
    """
    Retorna el nombre del Employee al que debe restringirse la consulta,
    o None si el usuario tiene visibilidad completa.

    Si el usuario no tiene rol de visibilidad total y tampoco tiene un
    Employee vinculado, se retorna un valor que nunca coincide con ningún
    ticket (en vez de un caso especial aparte), dejando el reporte vacío.
    """
    user_roles = set(frappe.get_roles(frappe.session.user))
    if user_roles & FULL_ACCESS_ROLES:
        return None

    employee = frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user}, "name"
    )
    return employee or "__SIN_EMPLEADO_VINCULADO__"


def get_columns():
    return [
        {"label": _("Ticket"), "fieldname": "name", "fieldtype": "Link",
         "options": "Fuel Ticket", "width": 140},
        {"label": _("Fecha Emisión"), "fieldname": "issued_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Empleado"), "fieldname": "employee", "fieldtype": "Link",
         "options": "Employee", "width": 110},
        {"label": _("Nombre Empleado"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Departamento"), "fieldname": "department", "fieldtype": "Link",
         "options": "Department", "width": 130},
        {"label": _("Vehículo"), "fieldname": "vehicle", "fieldtype": "Link",
         "options": "Vehicle", "width": 110},
        {"label": _("Combustible"), "fieldname": "fuel_item", "fieldtype": "Link",
         "options": "Item", "width": 120},
        {"label": _("Estación"), "fieldname": "station", "fieldtype": "Link",
         "options": "Warehouse", "width": 130},
        {"label": _("Autorizado"), "fieldname": "qty_authorized", "fieldtype": "Float", "width": 100},
        {"label": _("Despachado"), "fieldname": "qty_dispatched", "fieldtype": "Float", "width": 100},
        {"label": _("Restante"), "fieldname": "qty_remaining", "fieldtype": "Float", "width": 100},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 90},
        {"label": _("Estado"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Vence"), "fieldname": "expires_on", "fieldtype": "Datetime", "width": 150},
    ]


def get_conditions(filters, restricted_employee):
    conditions = ["t.docstatus = 1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("DATE(t.issued_on) >= %(from_date)s")
        values["from_date"] = filters.from_date

    if filters.get("to_date"):
        conditions.append("DATE(t.issued_on) <= %(to_date)s")
        values["to_date"] = filters.to_date

    if filters.get("employee"):
        conditions.append("t.employee = %(employee)s")
        values["employee"] = filters.employee

    if filters.get("vehicle"):
        conditions.append("t.vehicle = %(vehicle)s")
        values["vehicle"] = filters.vehicle

    if filters.get("department"):
        conditions.append("t.department = %(department)s")
        values["department"] = filters.department

    if filters.get("fuel_item"):
        conditions.append("t.fuel_item = %(fuel_item)s")
        values["fuel_item"] = filters.fuel_item

    if filters.get("station"):
        conditions.append("t.station = %(station)s")
        values["station"] = filters.station

    if filters.get("status"):
        conditions.append("t.status = %(status)s")
        values["status"] = filters.status

    # Restricción por rol: si no tiene visibilidad total, solo ve su propio empleado,
    # sin importar qué empleado haya puesto en el filtro manual.
    if restricted_employee:
        conditions.append("t.employee = %(restricted_employee)s")
        values["restricted_employee"] = restricted_employee

    return " AND ".join(conditions), values


def get_data(filters, restricted_employee):
    where_clause, values = get_conditions(filters, restricted_employee)

    return frappe.db.sql(f"""
        SELECT
            t.name,
            t.issued_on,
            t.employee,
            e.employee_name,
            t.department,
            t.vehicle,
            t.fuel_item,
            t.station,
            t.qty_authorized,
            t.qty_dispatched,
            t.qty_remaining,
            t.uom,
            t.status,
            t.expires_on
        FROM `tabFuel Ticket` t
        LEFT JOIN `tabEmployee` e ON e.name = t.employee
        WHERE {where_clause}
        ORDER BY t.issued_on DESC
    """, values, as_dict=True)


def get_chart(data):
    if not data:
        return None

    status_totals = {}
    for row in data:
        status_totals[row.status] = status_totals.get(row.status, 0) + 1

    return {
        "data": {
            "labels": list(status_totals.keys()),
            "datasets": [{"name": _("Tickets"), "values": list(status_totals.values())}],
        },
        "type": "donut",
        "height": 260,
    }


def get_summary(data):
    total_authorized = sum(flt(d.qty_authorized) for d in data)
    total_dispatched = sum(flt(d.qty_dispatched) for d in data)
    total_remaining = sum(flt(d.qty_remaining) for d in data)

    return [
        {"label": _("Total Tickets"), "value": len(data), "indicator": "blue"},
        {"label": _("Galones Autorizados"), "value": total_authorized,
         "indicator": "blue", "datatype": "Float"},
        {"label": _("Galones Despachados"), "value": total_dispatched,
         "indicator": "green", "datatype": "Float"},
        {"label": _("Galones Restantes"), "value": total_remaining,
         "indicator": "orange", "datatype": "Float"},
    ]