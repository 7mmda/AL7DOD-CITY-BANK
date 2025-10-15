import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN") # يقرأ التوكن من المتغيرات البيئية أو يستخدم القيمة الافتراضية

DATABASE_NAME = os.getenv("DATABASE_NAME", "bank_data.db") # يقرأ اسم قاعدة البيانات من المتغيرات البيئية
DATABASE_PATH = os.path.join(os.getcwd(), DATABASE_NAME) # المسار الكامل لقاعدة البيانات
CURRENCY = "ريال الحدود"

