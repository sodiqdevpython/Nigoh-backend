from django.db import models

class BuildingNumber(models.IntegerChoices):
    FIRST = 1, "A"
    SECOND = 2, "B"
    THIRD = 3, "C"
    FOURTH = 4, "D"


class Floor(models.IntegerChoices):
    BASEMENT = -1, "Pastki qavat"
    FIRST = 1, "1-qavat"
    SECOND = 2, "2-qavat"
    THIRD = 3, "3-qavat"
    FOURTH = 4, "4-qavat"