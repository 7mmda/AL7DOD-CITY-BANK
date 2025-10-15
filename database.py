import psycopg2
from urllib.parse import urlparse
from config import DATABASE_URL

def get_db_connection():
    url = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # جدول المستخدمين (الحسابات البنكية)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            balance NUMERIC(15, 2) DEFAULT 1500.00,
            card_type VARCHAR(50) DEFAULT 'basic'
        )
    """)

    # جدول البطاقات (لتحديد أسعار وميزات البطاقات)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            card_name VARCHAR(50) PRIMARY KEY,
            price NUMERIC(15, 2) NOT NULL,
            benefits TEXT
        )
    """)

    # إضافة أنواع البطاقات الافتراضية إذا لم تكن موجودة
    cursor.execute("INSERT INTO cards (card_name, price, benefits) VALUES (
        'silver', 5000.00, 'خصم 5% على رسوم التحويل، زيادة 1% في عائد الاستثمار'
    ) ON CONFLICT (card_name) DO NOTHING;")
    cursor.execute("INSERT INTO cards (card_name, price, benefits) VALUES (
        'gold', 15000.00, 'خصم 10% على رسوم التحويل، زيادة 2% في عائد الاستثمار، سحب يومي أعلى'
    ) ON CONFLICT (card_name) DO NOTHING;")
    cursor.execute("INSERT INTO cards (card_name, price, benefits) VALUES (
        'platinum', 50000.00, 'خصم 15% على رسوم التحويل، زيادة 3% في عائد الاستثمار، سحب يومي أعلى بكثير، دعم VIP'
    ) ON CONFLICT (card_name) DO NOTHING;")

    # جدول الوزارات (ميزانيات الوزارات)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ministries (
            ministry_id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            balance NUMERIC(15, 2) DEFAULT 0.00
        )
    """)

    # جدول المعاملات (للسحب، الإيداع، التحويلات)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            type VARCHAR(50) NOT NULL,
            amount NUMERIC(15, 2) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # جدول الاستثمارات
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            investment_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount NUMERIC(15, 2) NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            return_rate NUMERIC(5, 2),
            status VARCHAR(50) DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # جدول الرواتب (لتتبع آخر راتب تم دفعه)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salaries (
            user_id BIGINT PRIMARY KEY,
            last_paid TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")

