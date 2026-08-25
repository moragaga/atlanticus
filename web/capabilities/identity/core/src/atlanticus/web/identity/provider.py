from __future__ import annotations

from abc import ABC, abstractmethod

from flask import Flask, Request

from atlanticus.web.identity.models import AuthenticatedIdentity


class IdentityProvider(ABC):
    @property
    @abstractmethod
    def key(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def production_ready(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate_configuration(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def resolve(self, request: Request) -> AuthenticatedIdentity:
        raise NotImplementedError

    def configure(self, server: Flask) -> None:
        del server
