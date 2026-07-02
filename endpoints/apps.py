from django.apps import AppConfig


class EndpointsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'endpoints'

    def ready(self):
        # Admin delete_selected ni tezlashtirish — bog'liq obyektlar ro'yxatini
        # ko'rsatmaslik (CASCADE baribir ishlaydi).
        from utils.admin_patches import apply_fast_delete_patch
        apply_fast_delete_patch()
