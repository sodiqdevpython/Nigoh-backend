"""
Django admin panelida bulk delete uchun optimizatsiya.

Django default `ModelAdmin.get_deleted_objects` — barcha bog'liq (CASCADE)
obyektlarni recursive tekshiradi va sahifada ro'yxat qilib chiqaradi. Ma'lumot
ko'p bo'lsa (minglab log) sahifa qotib qoladi.

Bu patch hech qanday ro'yxat ko'rsatmaydi — faqat model bo'yicha son:
"5 Computers o'chiriladi. Ishonchingiz komilmi?" — shu yetadi.

CASCADE haqiqiy o'chirish paytida baribir ishlaydi.
"""
from django.contrib import admin


def _fast_get_deleted_objects(self, objs, request):
    model_count = {}
    for obj in objs:
        key = str(obj._meta.verbose_name_plural)
        model_count[key] = model_count.get(key, 0) + 1

    # to_delete bo'sh — tasdiqlash sahifasida hech qanday obyekt ro'yxati chiqmaydi.
    # model_count esa "N Computers" kabi qisqa xulosani ko'rsatadi.
    return [], model_count, set(), []


def apply_fast_delete_patch():
    admin.ModelAdmin.get_deleted_objects = _fast_get_deleted_objects
