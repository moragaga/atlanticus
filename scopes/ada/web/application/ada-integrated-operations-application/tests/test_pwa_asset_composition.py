from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.extension import extend_ada_application_definition
from ada.web.application.integrated_operations.composition import (
    create_integrated_operations_extension,
)
from ada.web.application.integrated_operations.descriptor import (
    INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
)
from atlanticus.web.application import create_web_application


class PwaAssetCompositionTest(TestCase):
    def test_operational_dashboard_and_pwa_publish_together(self) -> None:
        with TemporaryDirectory() as directory:
            descriptor = replace(
                INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
                application_root=Path(directory),
            )
            definition = create_application_definition(application_descriptor=descriptor)
            definition = extend_ada_application_definition(
                definition,
                create_integrated_operations_extension(None),
            )
            runtime = create_web_application(definition)
            client = runtime.server.test_client()

            manifest_response = client.get('/manifest.webmanifest')
            self.assertEqual(manifest_response.status_code, 200)
            manifest = manifest_response.get_json()
            self.assertEqual(manifest['id'], 'ada-integrated-operations-application')
            self.assertEqual(manifest['name'], 'ADA Operaciones Integradas')
            self.assertEqual(manifest['short_name'], 'ADA Operaciones')
            self.assertEqual(manifest['start_url'], '/')
            self.assertEqual(manifest['scope'], '/')
            self.assertEqual(len(manifest['icons']), 3)
            self.assertEqual(client.get('/health/live').status_code, 200)
            self.assertTrue(
                any('ada_stockpile' in name for name in runtime.assets.css_entries)
            )
            for icon in manifest['icons']:
                with closing(client.get(icon['src'])) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, 'image/png')
                    self.assertTrue(response.get_data().startswith(b'\x89PNG\r\n\x1a\n'))
