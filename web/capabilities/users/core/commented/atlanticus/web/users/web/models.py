# Espejo pedagógico: Users Administration conserva identidad de origen y limita edición a profile y enabled.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.users.administration import UsersAdministrationService


@dataclass(frozen=True, slots=True)
class UsersAdminWebContext:
    administration: UsersAdministrationService
    can_manage: Callable[[], bool] = lambda: True
