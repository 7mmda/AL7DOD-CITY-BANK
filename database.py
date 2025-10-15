import sqlite3
from config import DATABASE_PATH

def init_db():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10) # زيادة المهلة إلى 10 ثواني
    cursor = conn.cursor()

    # جدول المستخدمين (الحسابات البنكية)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 1500.00,
            card_type TEXT DEFAULT 'basic' -- basic, silver, gold, platinum
        )
    ''')

    # جدول البطاقات (لتحديد أسعار وميزات البطاقات)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            card_name TEXT PRIMARY KEY,
            price REAL NOT NULL,
            benefits TEXT
        )
    ''')

    # إضافة أنواع البطاقات الافتراضية إذا لم تكن موجودة
    cursor.execute("INSERT OR IGNORE INTO cards (card_name, price, benefits) VALUES (
        'silver', 5000.00, 'خصم 5% على رسوم التحويل، زيادة 1% في عائد الاستثمار'
    )")
    cursor.execute("INSERT OR IGNORE INTO cards (card_name, price, benefits) VALUES (
        'gold', 15000.00, 'خصم 10% على رسوم التحويل، زيادة 2% في عائد الاستثمار، سحب يومي أعلى'
    )")
    cursor.execute("INSERT OR IGNORE INTO cards (card_name, price, benefits) VALUES (
        'platinum', 50000.00, 'خصم 15% على رسوم التحويل، زيادة 3% في عائد الاستثمار، سحب يومي أعلى بكثير، دعم VIP'
    )")

    # جدول الوزارات (ميزانيات الوزارات)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ministries (
            ministry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            balance REAL DEFAULT 0.00
        )
    """)

    # جدول المعاملات (للسحب، الإيداع، التحويلات)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT NOT NULL, -- deposit, withdraw, transfer_send, transfer_receive, salary, ministry_budget
            amount REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # جدول الاستثمارات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS investments (
            investment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL NOT NULL,
            start_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_date DATETIME,
            return_rate REAL,
            status TEXT DEFAULT 'active', -- active, completed, cancelled
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # جدول الرواتب (لتتبع آخر راتب تم دفعه)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salaries (
            user_id INTEGER PRIMARY KEY,
            last_paid DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    conn.commit()
    conn.close()

# دالة لفتح اتصال بقاعدة البيانات
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10) # زيادة المهلة إلى 10 ثواني
    conn.row_factory = sqlite3.Row # لتمكين الوصول إلى الأعمدة بالاسم
    return conn

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")

