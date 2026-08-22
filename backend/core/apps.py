from django.apps import AppConfig

#: Placeholder values shipped in .env.example.  Booting with DEBUG=False while
#: any of these is still in effect means a production deployment forgot to set
#: its own secret - refuse to start rather than run with a guessable one.
_INSECURE_DEFAULTS = {
    "DJANGO_SECRET_KEY": "dev-insecure-django-secret-key",
    "JWT_SECRET": "change-me-in-production-super-secret",
    "INTERNAL_API_KEY": "change-me-internal-service-key",
}


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Core"

    def ready(self):
        self._check_secrets()

        # Register the Mongo connection before any Document class is queried.
        from core.mongo import connect_mongo

        connect_mongo()

    @staticmethod
    def _check_secrets():
        from django.conf import settings

        if settings.DEBUG:
            return

        insecure = []
        if settings.SECRET_KEY == _INSECURE_DEFAULTS["DJANGO_SECRET_KEY"]:
            insecure.append("DJANGO_SECRET_KEY")
        if settings.JWT["SECRET"] == _INSECURE_DEFAULTS["JWT_SECRET"]:
            insecure.append("JWT_SECRET")
        if settings.REALTIME["INTERNAL_API_KEY"] == _INSECURE_DEFAULTS["INTERNAL_API_KEY"]:
            insecure.append("INTERNAL_API_KEY")

        if insecure:
            raise RuntimeError(
                "Refusing to start with DJANGO_DEBUG=False while these secrets still "
                "have their insecure placeholder value: {}. Set real values in the "
                "environment before deploying.".format(", ".join(insecure))
            )
