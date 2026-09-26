from __future__ import annotations

import base64
import json
from binascii import Error as BinasciiError
from collections.abc import Mapping


# La revisión Tool ausente se declara, nunca se inventa.
def inspect_import(contents: str, filename: str | None) -> dict[str, object]:
    if not isinstance(contents, str) or ',' not in contents:
        raise ValueError('El archivo importado no contiene un documento JSON válido.')
    try:
        payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
        document = json.loads(payload.decode('utf-8'))
    except (BinasciiError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('El archivo seleccionado no contiene JSON válido.') from error
    if not isinstance(document, dict):
        raise ValueError('El archivo debe contener un documento JSON.')
    if 'configuration' in document or 'tool_dependencies' in document:
        configuration = document.get('configuration')
        manifest = document.get('tool_dependencies')
        if not isinstance(configuration, dict) or not isinstance(manifest, dict):
            raise ValueError('El snapshot debe contener configuración y dependencias Tool.')
        revision = manifest.get('confirmed_tool_catalog_revision')
        if not isinstance(revision, str) or not revision.strip():
            raise ValueError('El snapshot debe identificar la revisión Tool confirmada.')
        kind = 'Snapshot con evidencia Tool'
    else:
        configuration = document
        revision = None
        kind = 'Configuración simple'
    if not isinstance(configuration.get('rules'), list) or not isinstance(
        configuration.get('messages'), list
    ):
        raise ValueError('La configuración debe contener listas de reglas y mensajes.')
    return {
        'filename': filename or 'Archivo JSON',
        'kind': kind,
        'tool_revision': revision,
        'configuration': configuration,
        'tool_dependencies': manifest if revision is not None else None,
    }


def revision_warning(review: Mapping[str, object], confirmed_revision: str | None) -> str | None:
    revision = review.get('tool_revision')
    if revision is None:
        return 'El archivo no incluye revisión Tool: el Manager debe validar las referencias antes de publicar.'
    if not isinstance(revision, str):
        return 'La revisión Tool incluida no es válida.'
    if confirmed_revision is None:
        return 'No existe catálogo Tool confirmado para comparar la revisión incluida.'
    if revision != confirmed_revision:
        return 'La revisión del archivo no coincide con el catálogo Tool confirmado. No importar.'
    return None


def can_confirm(review: Mapping[str, object], confirmed_revision: str | None) -> bool:
    revision = review.get('tool_revision')
    if review.get('kind') == 'Snapshot con evidencia Tool' and revision is None:
        return False
    return revision is None or isinstance(revision, str) and revision == confirmed_revision
