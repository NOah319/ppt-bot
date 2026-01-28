# Python yüklü hafif bir Linux kullan
FROM python:3.10-slim

# Sistemi güncelle ve LibreOffice'i yükle
RUN apt-get update && apt-get install -y libreoffice && apt-get clean

# Çalışma klasörünü ayarla
WORKDIR /app

# Dosyaları kopyala
COPY . .

# Kütüphaneleri yükle
RUN pip install -r requirements.txt

# Botu başlat
CMD ["python", "bot.py"]
