from pathlib import Path

from ada.web.application.generic import AdaApplicationDescriptor

INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR = AdaApplicationDescriptor(
    import_name='ada.web.application.integrated_operations',
    application_id='ada-integrated-operations-application',
    display_name='ADA Operaciones Integradas',
    distribution_name='ada-integrated-operations-application',
    application_root=Path(__file__).resolve().parents[5],
)
