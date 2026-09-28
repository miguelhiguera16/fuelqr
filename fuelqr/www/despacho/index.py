# Copyright (c) 2026, FuelQR and contributors
# API endpoints para la página de despacho


import frappe

login_required = True

def get_context(context):
    # Verificar permisos
    user_roles = frappe.get_roles(frappe.session.user)
    allowed_roles = {"Fuel Dispatcher", "Fuel Manager", "System Manager"}

    if not allowed_roles.intersection(user_roles):
        frappe.throw("No tiene permisos para acceder a esta página.", frappe.PermissionError)

    context.no_cache = 1
    context.show_sidebar = False
    context.title = "Despacho de Combustible — FuelQR"

    context.dispatcher = frappe.session.user
    context.dispatcher_name = frappe.db.get_value(
        "User", frappe.session.user, "full_name"
    ) or frappe.session.user