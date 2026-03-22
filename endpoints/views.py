from rest_framework import generics
from .models import Computer
from .serializers import ComputerSerializer

class ComputerRegisterView(generics.CreateAPIView):
    """
    Yangi kompyuterni (agentni) ro'yxatdan o'tkazish yoki mavjudini yangilash.
    Agent ishga tushganda birinchi shu endpointga POST so'rov yuboradi.
    """
    queryset = Computer.objects.all()
    serializer_class = ComputerSerializer