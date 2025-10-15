import discord
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime, timedelta

from config import BOT_TOKEN, DATABASE_NAME
from database import init_db, get_db_connection

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    init_db() # التأكد من تهيئة قاعدة البيانات عند بدء البوت
    print("Database ensured to be initialized.")
    salary_task.start() # بدء مهمة الرواتب الدورية
    process_investments.start() # بدء مهمة معالجة الاستثمارات الدورية

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("عذرًا، هذا الأمر غير موجود.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"الرجاء توفير جميع المتطلبات لهذا الأمر: {error}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر.")
    else:
        print(f"An error occurred: {error}")
        await ctx.send("حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا.")

# مهمة الرواتب الدورية
@tasks.loop(hours=3) # كل 3 ساعات
async def salary_task():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, last_paid FROM salaries")
        salaries_data = cursor.fetchall()

        for user_data in salaries_data:
            user_id = user_data["user_id"]
            last_paid_str = user_data["last_paid"]
            last_paid = datetime.strptime(last_paid_str, '%Y-%m-%d %H:%M:%S')

            if datetime.now() - last_paid >= timedelta(hours=3):
                # دفع الراتب
                salary_amount = 500.00
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (salary_amount, user_id))
                cursor.execute("UPDATE salaries SET last_paid = ? WHERE user_id = ?", (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
                cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                               (user_id, "salary", salary_amount, "راتب دوري"))
                print(f"Paid salary of {salary_amount} to user {user_id}")

        conn.commit()
    except Exception as e:
        print(f"Error in salary task: {e}")
    finally:
        conn.close()

# أوامر البنك الأساسية

# أوامر إدارة الوزارات (للمسؤولين فقط)
@bot.command(name="تعديل_ميزانية_وزارة", help="يعدل ميزانية وزارة موجودة. (للمسؤولين فقط)")
@commands.has_permissions(administrator=True)
async def update_ministry_budget(ctx, ministry_name: str, amount: float):
    if amount < 0:
        await ctx.send("يجب أن تكون الميزانية موجبة.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO ministries (name, balance) VALUES (?, COALESCE((SELECT balance FROM ministries WHERE name = ?), 0) + ?)", (ministry_name, ministry_name, amount))
        conn.commit()
        cursor.execute("SELECT balance FROM ministries WHERE name = ?", (ministry_name,))
        new_balance = cursor.fetchone()["balance"]
        await ctx.send(f"تم تحديث ميزانية وزارة {ministry_name} بإضافة {amount} ريال. رصيدها الجديد هو: {new_balance} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء تحديث الميزانية: {e}")
        print(f"Error updating ministry budget: {e}")
    finally:
        conn.close()

@bot.command(name="ميزانيات_الوزارات", help="يعرض ميزانيات جميع الوزارات.")
async def list_ministries(ctx):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, balance FROM ministries")
        ministries = cursor.fetchall()
        if not ministries:
            await ctx.send("لا توجد وزارات مسجلة حاليًا.")
            return

        embed = discord.Embed(title="ميزانيات الوزارات", color=discord.Color.blue())
        for ministry in ministries:
            embed.add_field(name=ministry["name"], value=f"{ministry["balance"]} ريال", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء عرض ميزانيات الوزارات: {e}")
        print(f"Error listing ministries: {e}")
    finally:
        conn.close()

# أوامر وزير المالية (صلاحيات خاصة)
@bot.command(name="توزيع_ميزانية_وزارة", help="يوزع مبلغًا من الخزينة العامة إلى وزارة محددة. (لوزير المالية فقط)")
# سيتم تحديد دور وزير المالية لاحقًا، حاليًا للمسؤولين
@commands.has_permissions(administrator=True)
async def distribute_ministry_budget(ctx, ministry_name: str, amount: float):
    if amount <= 0:
        await ctx.send("يجب أن يكون مبلغ التوزيع أكبر من صفر.")
        return

    # هنا يجب أن يكون هناك حساب للخزينة العامة أو حساب وزير المالية
    # حاليًا، نفترض أن الأموال تأتي من مصدر غير محدود للمسؤولين

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM ministries WHERE name = ?", (ministry_name,))
        ministry = cursor.fetchone()
        if not ministry:
            await ctx.send(f"الوزارة {ministry_name} غير موجودة.")
            return

        cursor.execute("UPDATE ministries SET balance = balance + ? WHERE name = ?", (amount, ministry_name))
        # يمكن إضافة سجل للمعاملة هنا إذا كان هناك حساب للخزينة العامة
        conn.commit()
        await ctx.send(f"تم توزيع {amount} ريال على وزارة {ministry_name} بنجاح. رصيدها الجديد هو: {ministry["balance"] + amount} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء توزيع الميزانية: {e}")
        print(f"Error distributing ministry budget: {e}")
    finally:
        conn.close()

@bot.command(name="فتح_حساب", help="يفتح حساب بنكي جديد برصيد مبدئي 1500.")
async def open_account(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            await ctx.send("لديك بالفعل حساب بنكي!")
        else:
            initial_balance = 1500.00
            cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, initial_balance))
            cursor.execute("INSERT INTO salaries (user_id, last_paid) VALUES (?, ?)", (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "deposit", initial_balance, "رصيد مبدئي لفتح الحساب"))
            conn.commit()
            await ctx.send(f"تم فتح حساب بنكي لك بنجاح! رصيدك المبدئي هو {initial_balance} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء فتح الحساب: {e}")
        print(f"Error opening account: {e}")
    finally:
        conn.close()

@bot.command(name="رصيدي", help="يعرض رصيدك الحالي.")
async def balance(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            await ctx.send(f"رصيدك الحالي هو: {user["balance"]} ريال.")
        else:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء استعراض الرصيد: {e}")
        print(f"Error fetching balance: {e}")
    finally:
        conn.close()

@bot.command(name="إيداع", help="يودع مبلغًا في حسابك.")
async def deposit(ctx, amount: float):
    user_id = ctx.author.id
    if amount <= 0:
        await ctx.send("يجب أن يكون مبلغ الإيداع أكبر من صفر.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (user_id, "deposit", amount, "إيداع يدوي"))
        conn.commit()
        await ctx.send(f"تم إيداع {amount} ريال في حسابك. رصيدك الجديد هو: {user["balance"] + amount} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء الإيداع: {e}")
        print(f"Error depositing: {e}")
    finally:
        conn.close()

@bot.command(name="سحب", help="يسحب مبلغًا من حسابك.")
async def withdraw(ctx, amount: float):
    user_id = ctx.author.id
    if amount <= 0:
        await ctx.send("يجب أن يكون مبلغ السحب أكبر من صفر.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        if user["balance"] < amount:
            await ctx.send("رصيدك لا يكفي لإجراء عملية السحب هذه.")
            return

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (user_id, "withdraw", amount, "سحب يدوي"))
        conn.commit()
        await ctx.send(f"تم سحب {amount} ريال من حسابك. رصيدك الجديد هو: {user["balance"] - amount} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء السحب: {e}")
        print(f"Error withdrawing: {e}")
    finally:
        conn.close()

@bot.command(name="تحويل", help="يحول مبلغًا إلى مستخدم آخر.")
async def transfer(ctx, member: discord.Member, amount: float):
    sender_id = ctx.author.id
    receiver_id = member.id

    if amount <= 0:
        await ctx.send("يجب أن يكون مبلغ التحويل أكبر من صفر.")
        return
    if sender_id == receiver_id:
        await ctx.send("لا يمكنك تحويل الأموال إلى نفسك.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
        sender = cursor.fetchone()
        if not sender:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (receiver_id,))
        receiver = cursor.fetchone()
        if not receiver:
            await ctx.send(f"{member.display_name} ليس لديه حساب بنكي.")
            return

        if sender["balance"] < amount:
            await ctx.send("رصيدك لا يكفي لإجراء عملية التحويل هذه.")
            return

        # خصم من المرسل
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (sender_id, "transfer_send", amount, f"تحويل إلى {member.display_name}"))

        # إضافة إلى المستلم
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, receiver_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (receiver_id, "transfer_receive", amount, f"تحويل من {ctx.author.display_name}"))

        conn.commit()
        await ctx.send(f"تم تحويل {amount} ريال إلى {member.display_name} بنجاح.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء التحويل: {e}")
        print(f"Error transferring: {e}")
    finally:
        conn.close()

# أوامر الاستثمار
@bot.command(name="استثمار", help="يبدأ استثمارًا جديدًا بمبلغ ومدة محددة.")
async def invest(ctx, amount: float, days: int):
    user_id = ctx.author.id
    if amount <= 0:
        await ctx.send("يجب أن يكون مبلغ الاستثمار أكبر من صفر.")
        return
    if days <= 0:
        await ctx.send("يجب أن تكون مدة الاستثمار أكبر من صفر يوم.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        if user["balance"] < amount:
            await ctx.send("رصيدك لا يكفي لإجراء هذا الاستثمار.")
            return

        # خصم مبلغ الاستثمار من رصيد المستخدم
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (user_id, "investment_start", -amount, f"بدء استثمار بمبلغ {amount} لمدة {days} أيام"))

        # إضافة الاستثمار إلى جدول الاستثمارات
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)
        # معدل عائد افتراضي (يمكن تعديله لاحقًا)
        return_rate = 0.05 # 5% عائد

        cursor.execute("INSERT INTO investments (user_id, amount, start_date, end_date, return_rate, status) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, amount, start_date.strftime("%Y-%m-%d %H:%M:%S"), end_date.strftime("%Y-%m-%d %H:%M:%S"), return_rate, "active"))
        conn.commit()
        await ctx.send(f"تم بدء استثمار بمبلغ {amount} ريال لمدة {days} أيام. سينتهي الاستثمار في {end_date.strftime("%Y-%m-%d %H:%M:%S")}.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء بدء الاستثمار: {e}")
        print(f"Error starting investment: {e}")
    finally:
        conn.close()

@bot.command(name="استثماراتي", help="يعرض قائمة باستثماراتك الحالية والمنتهية.")
async def my_investments(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT amount, start_date, end_date, return_rate, status FROM investments WHERE user_id = ? ORDER BY status DESC, end_date ASC", (user_id,))
        investments = cursor.fetchall()

        if not investments:
            await ctx.send("ليس لديك أي استثمارات حاليًا.")
            return

        embed = discord.Embed(title="استثماراتك", color=discord.Color.green())
        for inv in investments:
            status_text = "نشط" if inv["status"] == "active" else "منتهي"
            embed.add_field(name=f"مبلغ: {inv["amount"]} ريال",
                            value=f"بدء: {inv["start_date"]}\nانتهاء: {inv["end_date"]}\nعائد: {inv["return_rate"]*100:.0f}%\nالحالة: {status_text}",
                            inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء عرض الاستثمارات: {e}")
        print(f"Error fetching investments: {e}")
    finally:
        conn.close()

# مهمة معالجة الاستثمارات المنتهية
@tasks.loop(minutes=10) # يمكن تعديل التردد حسب الحاجة
async def process_investments():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT investment_id, user_id, amount, return_rate FROM investments WHERE status = ? AND end_date <= ?", ("active", now))
        completed_investments = cursor.fetchall()

        for inv in completed_investments:
            investment_id = inv["investment_id"]
            user_id = inv["user_id"]
            original_amount = inv["amount"]
            return_rate = inv["return_rate"]

            profit = original_amount * return_rate
            total_return = original_amount + profit

            # إضافة العائد إلى رصيد المستخدم
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_return, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "investment_return", total_return, f"عائد استثمار رقم {investment_id} (أصل + ربح)"))

            # تحديث حالة الاستثمار إلى منتهي
            cursor.execute("UPDATE investments SET status = ? WHERE investment_id = ?", ("completed", investment_id))
            print(f"Processed investment {investment_id} for user {user_id}. Returned {total_return} (original: {original_amount}, profit: {profit})")

        conn.commit()
    except Exception as e:
        print(f"Error processing investments: {e}")
    finally:
        conn.close()

# أوامر البطاقات
@bot.command(name="شراء_بطاقة", help="يسمح لك بشراء بطاقة بنكية (silver, gold, platinum).")
async def buy_card(ctx, card_name: str):
    user_id = ctx.author.id
    card_name = card_name.lower()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        cursor.execute("SELECT price, benefits FROM cards WHERE card_name = ?", (card_name,))
        card_info = cursor.fetchone()

        if not card_info:
            await ctx.send("اسم البطاقة غير صحيح. البطاقات المتاحة هي: silver, gold, platinum.")
            return

        card_price = card_info["price"]
        current_card_type = user["card_type"]

        if current_card_type == card_name:
            await ctx.send(f"لديك بالفعل بطاقة {card_name}.")
            return

        # يمكنك إضافة منطق للترقية هنا، مثلاً إذا كان لديه بطاقة فضية ويريد ذهبية
        # حاليًا، نفترض أن كل بطاقة تُشترى بشكل مستقل

        if user["balance"] < card_price:
            await ctx.send(f"رصيدك الحالي ({user["balance"]} ريال) لا يكفي لشراء بطاقة {card_name} بسعر {card_price} ريال.")
            return

        cursor.execute("UPDATE users SET balance = balance - ?, card_type = ? WHERE user_id = ?", (card_price, card_name, user_id))
        cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (user_id, "card_purchase", -card_price, f"شراء بطاقة {card_name}"))
        conn.commit()
        await ctx.send(f"تهانينا! لقد اشتريت بطاقة {card_name} بنجاح بسعر {card_price} ريال. رصيدك الجديد هو: {user["balance"] - card_price} ريال.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء شراء البطاقة: {e}")
        print(f"Error buying card: {e}")
    finally:
        conn.close()

@bot.command(name="بطاقتي", help="يعرض نوع بطاقتك الحالية ومميزاتها.")
async def my_card(ctx):
    user_id = ctx.author.id
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT card_type FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            await ctx.send("ليس لديك حساب بنكي. استخدم أمر `.فتح_حساب` لفتح حساب.")
            return

        card_type = user["card_type"]
        if card_type == "basic":
            await ctx.send("ليس لديك بطاقة مميزة حاليًا. يمكنك شراء بطاقة باستخدام أمر `.شراء_بطاقة`.")
            return

        cursor.execute("SELECT price, benefits FROM cards WHERE card_name = ?", (card_type,))
        card_info = cursor.fetchone()

        if card_info:
            embed = discord.Embed(title=f"بطاقتك الحالية: {card_type.capitalize()}", color=discord.Color.gold())
            embed.add_field(name="السعر", value=f"{card_info["price"]} ريال", inline=True)
            embed.add_field(name="المميزات", value=card_info["benefits"], inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("حدث خطأ في جلب معلومات بطاقتك.")
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء عرض بطاقتك: {e}")
        print(f"Error fetching card info: {e}")
    finally:
        conn.close()

@bot.command(name="البطاقات_المتاحة", help="يعرض قائمة بالبطاقات المتاحة وأسعارها ومميزاتها.")
async def available_cards(ctx):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT card_name, price, benefits FROM cards ORDER BY price ASC")
        cards = cursor.fetchall()

        if not cards:
            await ctx.send("لا توجد بطاقات متاحة حاليًا.")
            return

        embed = discord.Embed(title="البطاقات البنكية المتاحة", description="اختر البطاقة التي تناسبك لفتح مميزات إضافية!", color=discord.Color.purple())
        for card in cards:
            embed.add_field(name=f"{card["card_name"].capitalize()} ({card["price"]} ريال)", value=card["benefits"], inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"حدث خطأ أثناء عرض البطاقات المتاحة: {e}")
        print(f"Error listing available cards: {e}")
    finally:
        conn.close()

# تشغيل البوت
if BOT_TOKEN == "YOUR_BOT_TOKEN":
    print("الرجاء تحديث ملف config.py بتوكن البوت الخاص بك.")
else:
    bot.run(BOT_TOKEN)

