from django.db import models
from utils.models import BaseModel
from .choices import BuildingNumber, Floor

class Group(BaseModel):
    name = models.CharField(max_length=300)
    building = models.IntegerField(
        choices=BuildingNumber.choices,
        verbose_name="Bino", null=True
    )
    floor = models.IntegerField(
        choices=Floor.choices,
        verbose_name="Qavat", null=True
    )
    room_number = models.CharField(max_length=5, null=True)

    def __str__(self):
        return f"{self.get_building_display()} - {self.room_number} ({self.get_floor_display()})"

class Computer(BaseModel):
    # Asosiy ishonchli identifikator
    bios_uuid = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Qo'shimcha tarmoq ma'lumotlari
    mac_address = models.CharField(max_length=50, blank=True, null=True)
    hostname = models.CharField(max_length=150, blank=True, null=True)
    
    # Qurilma xususiyatlari (Hardware Specs)
    cpu_info = models.CharField(max_length=255, blank=True, null=True)  # Masalan: "Intel Core i7-12700H"
    ram_gb = models.FloatField(blank=True, null=True)                   # Masalan: 16.0
    storage_info = models.CharField(max_length=255, blank=True, null=True) # Masalan: "512 GB SSD"
    
    # Guruhga biriktirish
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='computers')
    
    # Holat monitoringi
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.hostname or 'Unknown'} ({self.bios_uuid})"