# Kichik va tezkor Python imijidan foydalanamiz
FROM python:3.11-slim

# Ishchi papkani belgilash
WORKDIR /app

# Python uchun kerakli muhit o'zgaruvchilari
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Kutubxonalarni o'rnatish
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Loyiha fayllarini ko'chirish
COPY . /app/