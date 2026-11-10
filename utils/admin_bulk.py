"""
Katta hajmdagi jadvallar uchun tez o'chirish admin action'i.

Django default'dagi "Delete selected" action har bir obyektni RAM ga yuklaydi
va confirmation sahifasini render qiladi. 100K+ entry'da bu:
  - Brauzer osilib qoladi
  - 400/500 xato beradi
  - Timeout bo'ladi

Shuningdek, "Select all across pages" bosilganda 100K+ pk POST'da yuboriladi
va Django `DATA_UPLOAD_MAX_NUMBER_FIELDS=1000` default cheklov tufayli
**400 Bad Request** qaytaradi. Settings.py'da bu qiymat None (cheksiz)
qilinishi ham kerak.

Ushbu mixin quyidagi action qo'shadi:

  ⚡ delete_selected_fast
     — tanlangan entry'lar bitta SQL DELETE bilan darrov o'chadi
     — 100K entry ham ~1-2 sek'da tugaydi (memory'ga yuklanmaydi)
     — Django signal'larini chaqirmaydi (post_delete/pre_delete)
     — Confirmation'siz — bosilganda darhol o'chadi

ESLATMA: "TRUNCATE barcha jadval" tugmasi QO'SHILMAGAN — adashib bosib yuborsa
belgilanmagan yozuvlar ham o'chib ketishi mumkin. Agar hammasini o'chirmoqchi
bo'lsangiz — "Select all" belgilang + action'ni ishlating.
"""
from django.contrib import admin, messages


class BulkDeleteAdminMixin:
    """ModelAdmin'ga qo'shing — tez `delete_selected_fast` action qo'shiladi.

    Default `delete_selected` ni OLIB TASHLAYMIZ — u sekin va katta hajmda
    crash beradi. Uning o'rniga `delete_selected_fast` ishlatiladi.
    """

    actions = ['delete_selected_fast']

    def get_actions(self, request):
        """Default `delete_selected` ni olib tashlaymiz — _raw_delete bilan
        almashtirilgan `delete_selected_fast` afzal."""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

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
