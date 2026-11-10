"""
Katta hajmdagi jadvallar uchun tez o'chirish admin action'lari.

Django default'dagi "Delete selected" action har bir obyektni RAM ga yuklaydi
va confirmation sahifasini render qiladi. 100K+ entry'da bu:
  - Brauzer osilib qoladi
  - 400/500 xato beradi
  - Timeout bo'ladi

Shuningdek, "Select all across pages" bosilganda 100K+ pk POST'da yuboriladi
va Django `DATA_UPLOAD_MAX_NUMBER_FIELDS=1000` default cheklov tufayli
**400 Bad Request** qaytaradi. Settings.py'da bu qiymat None (cheksiz)
qilinishi ham kerak.

Ushbu mixin quyidagi action/tugmalarni qo'shadi:

  1) ⚡ delete_selected_fast
     — tanlangan entry'lar bitta SQL DELETE bilan darrov o'chadi
     — 100K entry ham ~1-2 sek'da tugaydi (memory'ga yuklanmaydi)
     — Django signal'larini chaqirmaydi (post_delete/pre_delete)

  2) ☠ truncate_entire_table (action — selection kerak)
     — BUTUN jadvalni TRUNCATE qiladi (millisekundlarda)
     — Auto-increment counterni ham nolga qaytaradi
     — Faqat superuser bajarishi mumkin

  3) 💥 "TRUNCATE barcha jadval" tugmasi changelist sahifasida
     — Selection TALAB QILMAYDI — bir bosilsa butun jadval tozalanadi
     — URL: /admin/<app>/<model>/truncate-all/
     — Confirmation sahifasi orqali tasdiqlash

ForeignKey CASCADE Postgres darajasida ishlaydi (TRUNCATE CASCADE).
"""
from django.contrib import admin, messages
from django.db import connection
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html


class BulkDeleteAdminMixin:
    """ModelAdmin'ga qo'shing — action'lar va tugmalar avtomatik qo'shiladi.

    Default `delete_selected` action'ni OLIB TASHLAYMIZ — u sekin va katta
    hajmda crash beradi. Uning o'rniga `delete_selected_fast` ishlatiladi.
    """

    actions = ['delete_selected_fast', 'truncate_entire_table']

    change_list_template = 'admin/bulk_truncate_change_list.html'

    def get_actions(self, request):
        """Default `delete_selected` ni olib tashlaymiz — _raw_delete bilan
        almashtirilgan `delete_selected_fast` afzal."""
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                'truncate-all/',
                self.admin_site.admin_view(self.truncate_all_view),
                name='%s_%s_truncate_all' % info,
            ),
        ]
        return custom + urls

    def truncate_all_view(self, request):
        """Changelist sahifasidagi tugma shu view'ga olib keladi.
        POST — truncate bajariladi. GET — confirmation ko'rsatiladi.
        """
        if not request.user.is_superuser:
            self.message_user(request, "Faqat superuser bajara oladi", level=messages.ERROR)
            return HttpResponseRedirect(self._changelist_url())

        model = self.model
        total = model.objects.count()

        if request.method == 'POST':
            table = model._meta.db_table
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
                self.message_user(
                    request,
                    f"☠ {table}: {total:,} ta yozuv TRUNCATE qilindi",
                    level=messages.SUCCESS,
                )
            except Exception as e:
                self.message_user(request, f"✗ TRUNCATE xato: {e}", level=messages.ERROR)
            return HttpResponseRedirect(self._changelist_url())

        # GET — confirmation sahifasi
        context = {
            'opts': model._meta,
            'total': total,
            'table': model._meta.db_table,
            'title': f"TRUNCATE {model._meta.verbose_name_plural}",
            'app_label': model._meta.app_label,
            'has_view_permission': True,
            **self.admin_site.each_context(request),
        }
        return render(request, 'admin/bulk_truncate_confirm.html', context)

    def _changelist_url(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        return reverse('admin:%s_%s_changelist' % info)

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
                cursor.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
            self.message_user(
                request,
                f"☠ {table} jadvali to'liq TRUNCATE qilindi (barcha ma'lumot yo'q qilindi)",
                level=messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(request, f"✗ TRUNCATE xato: {e}", level=messages.ERROR)
