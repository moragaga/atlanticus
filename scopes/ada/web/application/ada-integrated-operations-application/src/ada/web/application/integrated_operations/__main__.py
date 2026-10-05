from ada.web.application.generic.host import run_operational_application
from ada.web.application.integrated_operations.composition import (
    create_integrated_operations_extension,
)
from ada.web.application.integrated_operations.descriptor import (
    INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
)


def main() -> None:
    run_operational_application(
        application_descriptor=INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
        extension_factory=create_integrated_operations_extension,
    )


if __name__ == '__main__':
    main()
