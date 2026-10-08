from contextlib import contextmanager
from functools import wraps
from threading import Condition

from app.extensions import db


class DeliveryStateCoordinator:
    def __init__(self):
        self._condition = Condition()
        self._active = False
        self._queued_changes = 0

    @contextmanager
    def change(self):
        with self._condition:
            self._queued_changes += 1
            try:
                self._condition.wait_for(lambda: not self._active)
            finally:
                self._queued_changes -= 1
            self._active = True
        try:
            yield
        finally:
            self._finish()

    @contextmanager
    def dispatch(self):
        with self._condition:
            self._condition.wait_for(lambda: not self._active and not self._queued_changes)
            self._active = True
        try:
            yield
        finally:
            self._finish()

    def _finish(self):
        try:
            db.session.rollback()
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


DELIVERY_STATE = DeliveryStateCoordinator()


def serialized_delivery_state_change(operation):
    @wraps(operation)
    def serialized(*args, **kwargs):
        # End stale DB transactions before waiting for the dispatch coordinator.
        db.session.rollback()
        with DELIVERY_STATE.change():
            return operation(*args, **kwargs)
    return serialized
