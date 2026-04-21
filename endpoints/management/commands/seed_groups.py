import random
from django.core.management.base import BaseCommand
from faker import Faker
from endpoints.models import Group  # <-- Agar modelingiz nomi boshqa bo'lsa, almashtiring

class Command(BaseCommand):
    help = 'Bazaga soxta guruhlar (xonalar/bo\'limlar) kiritish'

    def add_arguments(self, parser):
        # Default holatda 10 ta guruh yaratadi
        parser.add_argument('count', type=int, nargs='?', default=10)

    def handle(self, *args, **kwargs):
        count = kwargs['count']
        fake = Faker()
        
        self.stdout.write(self.style.WARNING(f"{count} ta guruh kiritish boshlandi..."))

        # Guruh nomlari ishonarli chiqishi uchun maxsus so'zlar
        prefixes = ["Xona", "Laboratoriya", "Kafedra", "Bo'lim", "Zal", "Auditoriya"]

        for _ in range(count):
            # Masalan: "Laboratoriya-404" yoki "Auditoriya-215" kabi nomlar yasaydi
            fake_name = f"{random.choice(prefixes)}-{random.randint(100, 999)}"
            
            # Agar modelingizda description (izoh) maydoni bo'lsa, buni yoqishingiz mumkin:
            # fake_desc = fake.sentence(nb_words=5)

            Group.objects.create(
                name=fake_name,
                # description=fake_desc
            )

        self.stdout.write(self.style.SUCCESS(f"Muvaffaqiyatli! {count} ta fake guruh bazaga qo'shildi."))