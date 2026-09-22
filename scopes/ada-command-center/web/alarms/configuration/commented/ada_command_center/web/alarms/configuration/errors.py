# Los errores separan fallas de validez intrínseca de la revisión y fallas del transporte Source.
# La validación describe contratos inválidos; Source describe problemas al leer o publicar releases.
class AlarmConfigurationSourceError(RuntimeError):
    pass
