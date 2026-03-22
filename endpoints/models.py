from django.db import models
from utils.models import BaseModel

class Group(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Computer(BaseModel):
    # Asosiy ishonchli identifikator
    bios_uuid = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Qo'shimcha tarmoq ma'lumotlari
    mac_address = models.CharField(max_length=50, blank=True, null=True)
    hostname = models.CharField(max_length=150, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    # Qurilma xususiyatlari (Hardware Specs)
    cpu_info = models.CharField(max_length=255, blank=True, null=True)  # Masalan: "Intel Core i7-12700H"
    ram_gb = models.FloatField(blank=True, null=True)                   # Masalan: 16.0
    storage_info = models.CharField(max_length=255, blank=True, null=True) # Masalan: "512 GB SSD"
    last_boot_time = models.DateTimeField(blank=True, null=True)        # Qachon yongani
    
    # Guruhga biriktirish
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='computers')
    
    # Holat monitoringi
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname or 'Unknown'} ({self.bios_uuid})"