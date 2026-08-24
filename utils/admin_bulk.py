"""
Katta hajmdagi jadvallar uchun tez o'chirish admin action'lari.

Django default'dagi "Delete selected" action har bir obyektni RAM ga yuklaydi
va confirmation sahifasini render qiladi. 100K+ entry'da bu:
  - Brauzer osilib qoladi
  - 400/500 xato beradi
  - Timeout bo'ladi

Ushbu mixin quyidagi action'larni qo'shadi:
  1) delete_selected_fast — tanlangan entry'lar SQL DELETE bilan darrov o'chadi
                            (memory'ga yuklamasdan, confirmation'siz)
  2) truncate_entire_table — BUTUN jadvalni TRUNCATE qiladi (millisekundlarda)

Har ikkalasi ham signal'larni ISHGA TUSHIRMAYDI (post_delete, pre_delete),
lekin ForeignKey CASCADE odatdagidek ishlaydi (Postgres darajasida).
"""
from django.contrib import admin, messages
from django.db import connection
from django.http import HttpResponseRedirect


class BulkDeleteAdminMixin:
    """ModelAdmin'ga qo'shing va action'lar avtomatik qo'shiladi."""

    # Kichik matn — actions dropdown ostida bu ko'rinadi
    actions = ['delete_selected_fast', 'truncate_entire_table']

    @admin.action(description='⚡ Tanlanganlarni DARROV o\'chirish (confirmation\'siz)')
    def delete_selected_fast(self, request, queryset):
        """Tanlanganlarni bitta SQL DELETE bilan o'chiradi."""
        try:
            count = queryset.count()
            if count == 0:
                self.message_user(request, "Hech nima tanlanmagan", level=messages.WARNING)
                return
            queryset._raw_delete(queryset.db)  # eng tez usul, signal chaqirmaydi
            self.message_user(
                request,
                f"✓ {count:,} ta entry o'chirildi",
                level=messages.SUCCESS,
            )
        except Exception as e:
            # _raw_delete FK cascade'ni ishlatmaydi, xato bo'lsa qaytamiz
            try:
                deleted, _ = queryset.delete()  # standart, cascade ishlaydi
                self.message_user(
                    request,
                    f"✓ {deleted:,} ta entry (cascade bilan) o'chirildi",
                    level=messages.SUCCESS,
                )
            except Exception as e2:
                self.message_user(request, f"✗ Xato: {e2}", level=messages.ERROR)

    @admin.action(description='☠ BUTUN jadvalni TRUNCATE (barchasi yo\'q bo\'ladi)')
    def truncate_entire_table(self, request, queryset):
        """
        Butun jadvalni TRUNCATE qiladi. queryset e'tibordan qoladi.
        Faqat superuser bajarishi mumkin.
        """
        if not request.user.is_superuser:
            self.message_user(
                request,
                "Faqat superuser TRUNCATE qila oladi",
                level=messages.ERROR,
            )
            return

        model = self.model
        table = model._meta.db_table
        try:
            with connection.cursor() as cursor:
                # RESTART IDENTITY — auto-increment counterni ham nolga qaytaradi
                # CASCADE — bog'liq jadvallarni ham tozalaydi
                cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
            self.message_user(
                request,
                f"☠ {table} jadvali to'liq TRUNCATE qilindi (barcha ma'lumot yo'q qilindi)",
                level=messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(request, f"✗ TRUNCATE xato: {e}", level=messages.ERROR)
