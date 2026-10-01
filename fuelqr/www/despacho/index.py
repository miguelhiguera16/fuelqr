
import frappe

login_required = True

def get_context(context):
    user_roles = frappe.get_roles(frappe.session.user)
    allowed_roles = {"Fuel Dispatcher", "Fuel Manager", "System Manager"}

    if not allowed_roles.intersection(user_roles):
        frappe.throw("No tiene permisos para acceder a esta página.", frappe.PermissionError)

    context.no_cache = 1
    context.no_navbar = True
    context.show_sidebar = False
    context.title = "Despacho de Combustible — FuelQR"
    context.dispatcher = frappe.session.user
    context.dispatcher_name = frappe.db.get_value(
        "User", frappe.session.user, "full_name"
    ) or frappe.session.user
    context.no_breadcrumbs = True
    context.no_header = True