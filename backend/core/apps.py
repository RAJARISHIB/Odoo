from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Core"

    def ready(self):
        # Register the Mongo connection before any Document class is queried.
        from core.mongo import connect_mongo

        connect_mongo()
