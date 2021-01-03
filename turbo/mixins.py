from django.db.models import Model

import turbo
from turbo import (
    CREATED,
    UPDATED,
    DELETED,
    REPLACE,
    REMOVE,
    APPEND, )


class BroadcastableMixin(object):
    default_stream_action = APPEND
    turbo_streams_template = None

    def get_turbo_streams_template(self, target):
        raise NotImplementedError

    def get_dom_target(self, target):
        raise NotImplementedError

    def append_context(self, target):
        return {}

    def _get_context(self, target):
        context = {"model_template": self.get_turbo_streams_template(target)}
        context.update(self.append_context(target))
        return context

    def send_broadcast(self, target, action):
        turbo.send_broadcast(target, self.get_dom_target(target), action,
                             self.get_turbo_streams_template(target), self._get_context(target))


class BroadcastableModelMixin(BroadcastableMixin):
    broadcasts_to = []  # Foreign Key fieldnames to broadcast updates for.
    broadcast_self = True  # Whether or not to broadcast updates on this model's own stream.
    inserts_by = APPEND  # Whether to append or prepend when adding to a list (broadcasting to a foreign key).

    def get_turbo_streams_template(self, target):
        if self.turbo_streams_template is not None:
            return self.turbo_streams_template
        app_name, model_name = self._meta.label.lower().split(".")
        return f"{app_name}/{model_name}.html"

    def append_context(self, target):
        # Add Custom context
        app_name, model_name = self._meta.label.lower().split(".")
        return {
            "object": self,
            model_name: self
        }

    def get_action(self, model_action):
        if model_action == CREATED:
            streams_action = self.inserts_by
        elif model_action == UPDATED:
            streams_action = REPLACE
        elif model_action == DELETED:
            streams_action = REMOVE
        else:  # TODO: What should the default be?
            streams_action = REPLACE
        return streams_action

    def broadcast(self, model_action):
        streams_action = self.get_action(model_action)

        if self.broadcast_self:
            self.send_broadcast(self, streams_action)

        for field_name in self.broadcasts_to:
            if hasattr(self, field_name):
                self.send_broadcast(getattr(self, field_name), streams_action)
            else:
                self.send_broadcast(field_name, streams_action)

    def get_dom_target(self, target):
        if isinstance(target, Model):
            model: Model = target
            if self._meta.model != model:
                # Broadcast to self
                return self._meta.verbose_name_plural.lower()
            else:
                return f"{self._meta.verbose_name.lower()}_{self.pk}"
        else:
            return f'{target.lower()}'

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        self.broadcast(CREATED if creating else UPDATED)

    def delete(self, *args, **kwargs):
        self.broadcast(DELETED)
        super().delete(*args, **kwargs)
