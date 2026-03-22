import uuid
from django.db import models

class BaseModel(models.Model):
    # Asosiy ID sifatida UUID ishlatamiz
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Har bir yozuvning qachon yaratilgani va oxirgi marta tahrirlangani
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Bu model bazada alohida jadval bo'lib yaratilmaydi, 
        # faqat boshqa modellarga meros bo'lib o'tadi
        abstract = True