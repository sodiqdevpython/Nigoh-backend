import random
from django.core.management.base import BaseCommand
from faker import Faker
from endpoints.models import Computer

class Command(BaseCommand):
    help = 'Bazaga soxta kompyuterlar kiritish'

    def add_arguments(self, parser):
        parser.add_argument('count', type=int, nargs='?', default=50)

    def handle(self, *args, **kwargs):
        count = kwargs['count']
        fake = Faker() 
        
        self.stdout.write(self.style.WARNING(f"{count} ta kompyuter kiritish boshlandi..."))

        for _ in range(count):
            # Faqat sizning modelingizda borligi aniq bo'lgan ma'lumotlarni yasaymiz
            fake_hostname = f"PC-{fake.word().upper()}-{random.randint(10, 99)}"
            fake_uuid = str(fake.uuid4())
            
            # Agar sizning modelingizda mac_address bo'lsa, buni yoqib qo'yishingiz mumkin:
            # fake_mac = fake.mac_address()
            
            # Bazaga saqlaymiz (faqat aniq mavjud maydonlar bilan)
            Computer.objects.create(
                hostname=fake_hostname,
                bios_uuid=fake_uuid,
                # mac_address=fake_mac,  <-- Agar modelingizda bo'lsa izohdan chiqaring
                is_online=random.choice([True, False])
            )

        self.stdout.write(self.style.SUCCESS(f"Muvaffaqiyatli! {count} ta fake kompyuter bazaga qo'shildi."))