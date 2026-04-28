import contentful_management
import contentful
from app.config import settings


class ContentfulClient:
    """Wrapper around Contentful Management API (writes) and Delivery API (reads)."""

    def __init__(self):
        self._cma = None
        self._cda = None

    @property
    def cma(self) -> contentful_management.Client:
        if self._cma is None:
            self._cma = contentful_management.Client(settings.contentful_management_token)
        return self._cma

    @property
    def cda(self) -> contentful.Client:
        if self._cda is None:
            self._cda = contentful.Client(
                settings.contentful_space_id,
                settings.contentful_delivery_token,
                environment=settings.contentful_environment,
            )
        return self._cda

    def _get_environment(self):
        space = self.cma.spaces().find(settings.contentful_space_id)
        return space.environments().find(settings.contentful_environment)

    def create_entry(self, content_type_id: str, fields: dict) -> dict:
        """Create a new entry in Contentful. Fields should be locale-keyed, e.g. {'title': {'en-US': 'Hello'}}."""
        env = self._get_environment()
        entry = env.entries().create(
            None,  # let Contentful auto-generate the ID
            {"content_type_id": content_type_id, "fields": fields},
        )
        return {"id": entry.id, "fields": fields}

    def publish_entry(self, entry_id: str) -> dict:
        """Publish an entry to make it visible via the Delivery API."""
        env = self._get_environment()
        entry = env.entries().find(entry_id)
        entry.publish()
        return {"id": entry_id, "status": "published"}

    def update_entry(self, entry_id: str, fields: dict) -> dict:
        """Update fields on an existing entry."""
        env = self._get_environment()
        entry = env.entries().find(entry_id)
        for field_name, value in fields.items():
            setattr(entry, field_name, value)
        entry.save()
        return {"id": entry_id, "fields": fields}

    def get_entries(self, content_type_id: str, query: dict | None = None) -> list:
        """Fetch entries from Contentful Delivery API with optional query filters."""
        params = {"content_type": content_type_id}
        if query:
            params.update(query)
        entries = self.cda.entries(params)
        return [
            {"id": e.id, "fields": {k: getattr(e, k, None) for k in e.fields().keys()}}
            for e in entries
        ]

    def get_entry(self, entry_id: str) -> dict:
        """Fetch a single entry by ID from the Delivery API."""
        entry = self.cda.entry(entry_id)
        return {
            "id": entry.id,
            "fields": {k: getattr(entry, k, None) for k in entry.fields().keys()},
        }


contentful_client = ContentfulClient()
