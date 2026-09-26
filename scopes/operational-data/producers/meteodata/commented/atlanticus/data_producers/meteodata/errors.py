# Errores de contrato de la adquisición; nunca se muestra el cuerpo HTTP ni credenciales.
class MeteodataResponseError(ValueError):
    pass


class MeteodataAcquisitionError(RuntimeError):
    pass
