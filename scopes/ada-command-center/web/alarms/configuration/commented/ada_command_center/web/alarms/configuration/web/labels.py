# Etiquetas y explicaciones de presentación; el contrato serializado no se traduce.
from __future__ import annotations

LABELS = {
    'Family key': 'Familia',
    'Alarm key': 'Identificador de alarma',
    'Rule name': 'Nombre técnico de la regla',
    'Display name': 'Nombre visible',
    'Title': 'Título',
    'Cause template': 'Texto de la causa',
    'Active': 'Activa',
    'Visibility': 'Visibilidad',
    'Special condition': 'Esta regla es una condición especial',
    'Kind': 'Tipo de alarma',
    'Criticality': 'Criticidad',
    'Business category': 'Categoría de negocio',
    'Operational areas': 'Áreas operacionales',
    'Color': 'Color de representación',
    'Evaluator key': 'Evaluador',
    'Parameters JSON': 'Parámetros del evaluador (JSON)',
    'Priority group': 'Grupo de prioridad',
    'Priority order': 'Orden de prioridad',
    'Messages': 'Mensajes asociados',
    'After minutes': 'Volver a mostrar tras (minutos)',
    'Special conditions': 'Condiciones que pueden reactivar la visualización',
    'Enabled': 'Habilitado',
    'Max duration hours': 'Duración máxima (horas)',
    'Approval required': 'Requiere aprobación',
    'Origin tool key': 'Herramienta de origen',
    'Step order': 'Orden del paso',
    'Target tool key': 'Herramienta de destino',
    'Wait minutes from previous step': 'Espera desde el paso anterior (minutos)',
    'Tool key': 'Herramienta visual',
    'Process projection mode': 'Modo de presentación Process',
    'Message key': 'Identificador del mensaje',
    'Scope': 'Alcance',
    'Display text': 'Texto del mensaje',
    'Deactivation override': 'Configurar desactivación para este mensaje',
    'Override enabled': 'Permite desactivación',
    'Override max duration hours': 'Duración máxima (horas)',
    'Override approval required': 'Requiere aprobación',
    'Identity and presentation': 'Identidad y presentación',
    'Classification': 'Clasificación',
    'Evaluation and priority': 'Evaluación y prioridad',
    'Reappearance': 'Reaparición',
    'Default deactivation': 'Desactivación',
}

HELP = {
    'Family key': 'La familia agrupa reglas y mensajes; no se guarda como entidad independiente.',
    'Alarm key': 'Identidad estable usada por Runtime e histórico. Evita cambiarla después de publicar.',
    'Rule name': 'Nombre técnico único dentro de la familia.',
    'Title': 'Encabezado estático que recibirá la Web.',
    'Cause template': 'Puede incluir variables de evidencia, que materializa el backend.',
    'Visibility': 'Visible aparece en las superficies operacionales; sólo trazabilidad no se muestra.',
    'Special condition': 'Esta regla podrá ser referenciada por otras del mismo grupo y familia.',
    'Criticality': 'C1: destinos inmediatos. C2: espera positiva. C3: sólo origen, sin escalamiento.',
    'Evaluator key': 'Se verificará contra el catálogo de evaluadores cuando esté disponible.',
    'Parameters JSON': 'Sólo admite claves de texto y valores texto, número o booleano.',
    'Priority group': 'El orden de prioridad es único dentro de este grupo.',
    'Priority order': 'Un número menor representa mayor prioridad.',
    'Special conditions': 'Son OTRAS reglas especiales de esta familia y grupo; no marcan esta regla como especial.',
    'After minutes': 'Si la condición principal sigue activa, puede reaparecer después de esta espera.',
    'Deactivation override': 'Sustituye completamente la política de desactivación de la regla.',
    'Process projection mode': 'Sólo aplica a herramientas Process con presentación de carrusel.',
    'Origin tool key': 'Lugar donde se origina el routing. No implica posición de visualización.',
    'Tool key': 'La Web utiliza esta herramienta y su estructura para colocar y colorear la alarma.',
}

VALUES = {
    'Yes': 'Sí',
    'No': 'No',
    'VISIBLE': 'Visible',
    'TRACE_ONLY': 'Sólo trazabilidad',
    'IMPACT': 'Impacto',
    'RISK': 'Riesgo',
    'C1': 'C1 · Inmediata',
    'C2': 'C2 · Con escalamiento diferido',
    'C3': 'C3 · Sólo herramienta de origen',
    'ECOLOGY': 'Ecología',
    'PRODUCTIVITY': 'Productividad',
    'SAFETY_HEALTH': 'Seguridad y salud',
    'COSTS': 'Costos',
    'MINE': 'Mina',
    'PLANT': 'Planta',
    'RED': 'Rojo',
    'YELLOW': 'Amarillo',
    'GENERIC': 'Genérico',
    'DISTRIBUTED': 'Distribuido',
    'GLOBAL': 'Global',
    'FAMILY': 'Familia',
}


def field_label(value: str) -> str:
    return LABELS.get(value, value)


def field_help(value: str) -> str | None:
    return HELP.get(value)


def value_label(value: str) -> str:
    return VALUES.get(value, value)
