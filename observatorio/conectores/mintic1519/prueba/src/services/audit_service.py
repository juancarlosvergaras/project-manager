REGISTROS = []
def log_action(action, resource, resource_id, details=None):
    REGISTROS.append((action, resource, resource_id, details))
