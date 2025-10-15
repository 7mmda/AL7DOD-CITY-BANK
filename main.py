import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import os
import psycopg2
from datetime import datetime, timedelta
from urllib.parse import urlparse

from config import BOT_TOKEN, DATABASE_URL, CURRENCY
from database import init_db, get_db_connection

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============= دوال مساعدة =============
def has_role(member, role_name):
    """تحقق من وجود دور معين لدى العضو"""
    return discord.utils.get(member.roles, name=role_name) is not None

def is_admin(member):
    """تحقق من صلاحيات الإدارة"""
    return member.guild_permissions.administrator

# ============= أحداث البوت =============
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        init_db() # التأكد من تهيئة قاعدة البيانات عند بدء البوت
        print("Database ensured to be initialized.")
    except Exception as e:
        print(f"Error initializing database: {e}")
    salary_task.start()
    process_investments.start()
    print("Bot is ready!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"الرجاء توفير جميع المتطلبات لهذا الأمر: {error}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("ليس لديك الصلاحيات الكافية لاستخدام هذا الأمر.")
    else:
        print(f"An error occurred: {error}")
        await ctx.send("حدث خطأ غير متوقع. الرجاء المحاولة لاحقًا.")

# ============= مهام دورية =============
@tasks.loop(hours=3)
async def salary_task():
    """مهمة دفع الرواتب كل 3 ساعات"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, last_paid FROM salaries")
        salaries_data = cursor.fetchall()

        for user_data in salaries_data:
            user_id = user_data[0] # user_id
            last_paid = user_data[1] # last_paid is already datetime object from psycopg2

            if datetime.now() - last_paid >= timedelta(hours=3):
                salary_amount = 500.00
                cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (salary_amount, user_id))
                cursor.execute("UPDATE salaries SET last_paid = %s WHERE user_id = %s", (datetime.now(), user_id))
                cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                               (user_id, "salary", salary_amount, "راتب دوري"))
                print(f"Paid salary of {salary_amount} to user {user_id}")

        conn.commit()
    except Exception as e:
        print(f"Error in salary task: {e}")
    finally:
        if conn:
            conn.close()

@tasks.loop(minutes=10)
async def process_investments():
    """مهمة معالجة الاستثمارات المنتهية"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("SELECT investment_id, user_id, amount, return_rate FROM investments WHERE status = %s AND end_date <= %s", ("active", now))
        completed_investments = cursor.fetchall()

        for inv in completed_investments:
            investment_id = inv[0] # investment_id
            user_id = inv[1] # user_id
            original_amount = inv[2] # amount
            return_rate = inv[3] # return_rate

            profit = float(original_amount) * float(return_rate)
            total_return = float(original_amount) + profit

            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (total_return, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (user_id, "investment_return", total_return, f"عائد استثمار رقم {investment_id} (أصل + ربح)"))
            cursor.execute("UPDATE investments SET status = %s WHERE investment_id = %s", ("completed", investment_id))
            print(f"Processed investment {investment_id} for user {user_id}. Returned {total_return}")

        conn.commit()
    except Exception as e:
        print(f"Error processing investments: {e}")
    finally:
        if conn:
            conn.close()

# ============= القوائم التفاعلية =============

# قائمة الأعضاء الرئيسية
class MemberMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 فتح حساب", style=discord.ButtonStyle.green, custom_id="open_account")
    async def open_account_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            if user:
                await interaction.response.send_message("لديك بالفعل حساب بنكي!", ephemeral=True)
            else:
                initial_balance = 1500.00
                cursor.execute("INSERT INTO users (user_id, balance) VALUES (%s, %s)", (user_id, initial_balance))
                cursor.execute("INSERT INTO salaries (user_id, last_paid) VALUES (%s, %s)", (user_id, datetime.now()))
                cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                               (user_id, "deposit", initial_balance, "رصيد مبدئي لفتح الحساب"))
                conn.commit()
                await interaction.response.send_message(f"✅ تم فتح حساب بنكي لك بنجاح!\n💵 رصيدك المبدئي: **{initial_balance} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @discord.ui.button(label="💳 رصيدي", style=discord.ButtonStyle.primary, custom_id="check_balance")
    async def check_balance_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT balance, card_type FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            if user:
                embed = discord.Embed(title="💳 رصيدك الحالي", color=discord.Color.blue())
                embed.add_field(name="المبلغ", value=f"**{user[0]} {CURRENCY}**", inline=False)
                embed.add_field(name="نوع البطاقة", value=f"**{user[1].capitalize()}**", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي. استخدم زر **فتح حساب** أولاً.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @discord.ui.button(label="💸 تحويل", style=discord.ButtonStyle.primary, custom_id="transfer")
    async def transfer_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TransferModal())

    @discord.ui.button(label="📈 استثمار", style=discord.ButtonStyle.primary, custom_id="invest")
    async def invest_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(InvestModal())

    @discord.ui.button(label="📊 استثماراتي", style=discord.ButtonStyle.secondary, custom_id="my_investments")
    async def my_investments_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT amount, start_date, end_date, return_rate, status FROM investments WHERE user_id = %s ORDER BY status DESC, end_date ASC", (user_id,))
            investments = cursor.fetchall()

            if not investments:
                await interaction.response.send_message("❌ ليس لديك أي استثمارات حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="📊 استثماراتك", color=discord.Color.green())
            for inv in investments:
                status_text = "🟢 نشط" if inv[4] == "active" else "✅ منتهي"
                embed.add_field(name=f"💰 {inv[0]} {CURRENCY}",
                                value=f"📅 بدء: {inv[1]}\n📅 انتهاء: {inv[2]}\n📈 عائد: {float(inv[3])*100:.0f}%\n{status_text}",
                                inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @discord.ui.button(label="💎 البطاقات", style=discord.ButtonStyle.secondary, custom_id="cards")
    async def cards_button(self, interaction: discord.Interaction, button: Button):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT card_name, price, benefits FROM cards ORDER BY price ASC")
            cards = cursor.fetchall()

            if not cards:
                await interaction.response.send_message("❌ لا توجد بطاقات متاحة حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="💎 البطاقات البنكية المتاحة", description="اختر البطاقة التي تناسبك!", color=discord.Color.purple())
            for card in cards:
                embed.add_field(name=f"{card[0].capitalize()} - {card[1]} {CURRENCY}", value=card[2], inline=False)
            
            view = BuyCardView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

# قائمة وزير المالية
class FinanceMinisterMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏛️ توزيع ميزانية", style=discord.ButtonStyle.green, custom_id="distribute_budget")
    async def distribute_budget_button(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, "وزير المالية") and not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط لوزير المالية!", ephemeral=True)
            return
        await interaction.response.send_modal(DistributeBudgetModal())

    @discord.ui.button(label="📊 ميزانيات الوزارات", style=discord.ButtonStyle.primary, custom_id="view_ministry_budgets")
    async def view_ministry_budgets_button(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, "وزير المالية") and not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط لوزير المالية!", ephemeral=True)
            return
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name, balance FROM ministries")
            ministries = cursor.fetchall()

            if not ministries:
                await interaction.response.send_message("❌ لا توجد وزارات مسجلة حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="📊 ميزانيات الوزارات", color=discord.Color.gold())
            for ministry in ministries:
                embed.add_field(name=ministry[0], value=f"**{ministry[1]} {CURRENCY}**", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

    @discord.ui.button(label="💸 سحب من وزارة", style=discord.ButtonStyle.red, custom_id="withdraw_from_ministry")
    async def withdraw_from_ministry_button(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, "وزير المالية") and not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط لوزير المالية!", ephemeral=True)
            return
        await interaction.response.send_modal(WithdrawFromMinistryModal())

# قائمة الإدارة
class AdminMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 إعطاء مال", style=discord.ButtonStyle.green, custom_id="give_money_admin")
    async def give_money_admin_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(GiveMoneyModal())

    @discord.ui.button(label="💸 سحب مال", style=discord.ButtonStyle.red, custom_id="take_money_admin")
    async def take_money_admin_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(TakeMoneyModal())

    @discord.ui.button(label="🏛️ إنشاء وزارة", style=discord.ButtonStyle.primary, custom_id="create_ministry_admin")
    async def create_ministry_admin_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(CreateMinistryModal())

    @discord.ui.button(label="📊 أغنى الناس", style=discord.ButtonStyle.blurple, custom_id="richest_users_admin")
    async def richest_users_admin_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
            richest_users = cursor.fetchall()

            if not richest_users:
                await interaction.response.send_message("❌ لا يوجد مستخدمون في البنك حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="👑 أغنى 10 مستخدمين", color=discord.Color.gold())
            for i, user_data in enumerate(richest_users):
                user_id = user_data[0]
                balance = user_data[1]
                user_obj = bot.get_user(user_id) or await bot.fetch_user(user_id)
                username = user_obj.display_name if user_obj else f"المستخدم {user_id}"
                embed.add_field(name=f"{i+1}. {username}", value=f"**{balance} {CURRENCY}**", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

# ============= Modals =============

class TransferModal(discord.ui.Modal, title="تحويل الأموال"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="معرف المستخدم (ID) المستلم", custom_id="recipient_id", placeholder="أدخل ID المستخدم المستلم"))
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ للتحويل"))

    async def on_submit(self, interaction: discord.Interaction):
        recipient_id = int(self.children[0].value)
        amount = float(self.children[1].value)
        sender_id = interaction.user.id

        if amount <= 0:
            await interaction.response.send_message("❌ لا يمكن تحويل مبلغ صفر أو أقل.", ephemeral=True)
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (sender_id,))
            sender_balance = cursor.fetchone()

            if not sender_balance or sender_balance[0] < amount:
                await interaction.response.send_message("❌ رصيدك غير كافٍ لإجراء هذا التحويل.", ephemeral=True)
                return
            
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (recipient_id,))
            recipient_exists = cursor.fetchone()
            if not recipient_exists:
                await interaction.response.send_message("❌ المستخدم المستلم غير موجود في البنك.", ephemeral=True)
                return

            # خصم من المرسل
            cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, sender_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (sender_id, "transfer_send", -amount, f"تحويل إلى {recipient_id}"))

            # إضافة للمستلم
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, recipient_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (recipient_id, "transfer_receive", amount, f"استلام من {sender_id}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم تحويل **{amount} {CURRENCY}** إلى المستخدم <@{recipient_id}> بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء التحويل: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class InvestModal(discord.ui.Modal, title="بدء استثمار جديد"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ للاستثمار"))
        self.add_item(discord.ui.TextInput(label="عدد الأيام", custom_id="days", placeholder="أدخل عدد أيام الاستثمار (مثال: 7)"))

    async def on_submit(self, interaction: discord.Interaction):
        amount = float(self.children[0].value)
        days = int(self.children[1].value)
        user_id = interaction.user.id

        if amount <= 0 or days <= 0:
            await interaction.response.send_message("❌ المبلغ وعدد الأيام يجب أن يكونا أكبر من صفر.", ephemeral=True)
            return
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
            user_balance = cursor.fetchone()

            if not user_balance or user_balance[0] < amount:
                await interaction.response.send_message("❌ رصيدك غير كافٍ لإجراء هذا الاستثمار.", ephemeral=True)
                return
            
            # خصم مبلغ الاستثمار من الرصيد
            cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, user_id))
            
            # حساب تاريخ الانتهاء والعائد (مثال: 5% عائد)
            end_date = datetime.now() + timedelta(days=days)
            return_rate = 0.05 # 5% عائد

            cursor.execute("INSERT INTO investments (user_id, amount, end_date, return_rate, status) VALUES (%s, %s, %s, %s, %s)",
                           (user_id, amount, end_date, return_rate, "active"))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (user_id, "investment_start", -amount, f"بدء استثمار لمدة {days} يوم"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم بدء استثمار بمبلغ **{amount} {CURRENCY}** لمدة **{days} يوم** بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء الاستثمار: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class BuyCardModal(discord.ui.Modal, title="شراء بطاقة"): 
    def __init__(self, card_name):
        super().__init__()
        self.card_name = card_name
        self.add_item(discord.ui.TextInput(label=f"تأكيد شراء بطاقة {card_name.capitalize()}", custom_id="confirm", placeholder="اكتب \"تأكيد\" للشراء"))

    async def on_submit(self, interaction: discord.Interaction):
        confirmation = self.children[0].value
        user_id = interaction.user.id

        if confirmation.lower() != "تأكيد":
            await interaction.response.send_message("❌ لم يتم تأكيد الشراء.", ephemeral=True)
            return
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT price FROM cards WHERE card_name = %s", (self.card_name,))
            card_price = cursor.fetchone()
            if not card_price:
                await interaction.response.send_message("❌ البطاقة غير موجودة.", ephemeral=True)
                return
            card_price = card_price[0]

            cursor.execute("SELECT balance, card_type FROM users WHERE user_id = %s", (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي. يرجى فتح حساب أولاً.", ephemeral=True)
                return
            
            user_balance = user_data[0]
            current_card_type = user_data[1]

            if user_balance < card_price:
                await interaction.response.send_message("❌ رصيدك غير كافٍ لشراء هذه البطاقة.", ephemeral=True)
                return
            
            # خصم سعر البطاقة وتحديث نوع البطاقة
            cursor.execute("UPDATE users SET balance = balance - %s, card_type = %s WHERE user_id = %s", (card_price, self.card_name, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (user_id, "card_purchase", -card_price, f"شراء بطاقة {self.card_name}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم شراء بطاقة **{self.card_name.capitalize()}** بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء شراء البطاقة: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class BuyCardView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="شراء فضية", style=discord.ButtonStyle.blurple, custom_id="buy_silver_card"))
        self.add_item(discord.ui.Button(label="شراء ذهبية", style=discord.ButtonStyle.gold, custom_id="buy_gold_card"))
        self.add_item(discord.ui.Button(label="شراء بلاتينيوم", style=discord.ButtonStyle.grey, custom_id="buy_platinum_card"))

    @discord.ui.button(label="شراء فضية", style=discord.ButtonStyle.blurple, custom_id="buy_silver_card")
    async def buy_silver_card_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(BuyCardModal("silver"))

    @discord.ui.button(label="شراء ذهبية", style=discord.ButtonStyle.gold, custom_id="buy_gold_card")
    async def buy_gold_card_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(BuyCardModal("gold"))

    @discord.ui.button(label="شراء بلاتينيوم", style=discord.ButtonStyle.grey, custom_id="buy_platinum_card")
    async def buy_platinum_card_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(BuyCardModal("platinum"))

class DistributeBudgetModal(discord.ui.Modal, title="توزيع ميزانية لوزارة"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="اسم الوزارة", custom_id="ministry_name", placeholder="أدخل اسم الوزارة"))
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ لتوزيعه"))

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.children[0].value
        amount = float(self.children[1].value)

        if amount <= 0:
            await interaction.response.send_message("❌ لا يمكن توزيع مبلغ صفر أو أقل.", ephemeral=True)
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # التحقق من وجود الوزارة
            cursor.execute("SELECT ministry_id FROM ministries WHERE name = %s", (ministry_name,))
            ministry_exists = cursor.fetchone()
            if not ministry_exists:
                await interaction.response.send_message("❌ الوزارة غير موجودة.", ephemeral=True)
                return
            
            # إضافة المبلغ لميزانية الوزارة
            cursor.execute("UPDATE ministries SET balance = balance + %s WHERE name = %s", (amount, ministry_name))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (interaction.user.id, "ministry_budget_distribution", amount, f"توزيع ميزانية لوزارة {ministry_name}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم توزيع **{amount} {CURRENCY}** على وزارة **{ministry_name}** بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء توزيع الميزانية: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class WithdrawFromMinistryModal(discord.ui.Modal, title="سحب أموال من وزارة"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="اسم الوزارة", custom_id="ministry_name", placeholder="أدخل اسم الوزارة"))
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ للسحب"))

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.children[0].value
        amount = float(self.children[1].value)

        if amount <= 0:
            await interaction.response.send_message("❌ لا يمكن سحب مبلغ صفر أو أقل.", ephemeral=True)
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # التحقق من وجود الوزارة ورصيدها
            cursor.execute("SELECT balance FROM ministries WHERE name = %s", (ministry_name,))
            ministry_balance = cursor.fetchone()

            if not ministry_balance:
                await interaction.response.send_message("❌ الوزارة غير موجودة.", ephemeral=True)
                return
            
            if ministry_balance[0] < amount:
                await interaction.response.send_message("❌ رصيد الوزارة غير كافٍ لإجراء هذا السحب.", ephemeral=True)
                return
            
            # خصم المبلغ من ميزانية الوزارة
            cursor.execute("UPDATE ministries SET balance = balance - %s WHERE name = %s", (amount, ministry_name))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (interaction.user.id, "ministry_withdraw", -amount, f"سحب من وزارة {ministry_name}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم سحب **{amount} {CURRENCY}** من وزارة **{ministry_name}** بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء السحب من الوزارة: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class GiveMoneyModal(discord.ui.Modal, title="إعطاء أموال لمستخدم"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="معرف المستخدم (ID)", custom_id="user_id", placeholder="أدخل ID المستخدم"))
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ لإعطائه"))

    async def on_submit(self, interaction: discord.Interaction):
        target_user_id = int(self.children[0].value)
        amount = float(self.children[1].value)

        if amount <= 0:
            await interaction.response.send_message("❌ لا يمكن إعطاء مبلغ صفر أو أقل.", ephemeral=True)
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # التحقق من وجود المستخدم
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (target_user_id,))
            user_exists = cursor.fetchone()
            if not user_exists:
                await interaction.response.send_message("❌ المستخدم غير موجود في البنك.", ephemeral=True)
                return
            
            # إضافة المبلغ للمستخدم
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, target_user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (target_user_id, "admin_give", amount, f"إعطاء من الإدارة بواسطة {interaction.user.id}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم إعطاء **{amount} {CURRENCY}** للمستخدم <@{target_user_id}> بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إعطاء الأموال: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class TakeMoneyModal(discord.ui.Modal, title="سحب أموال من مستخدم"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="معرف المستخدم (ID)", custom_id="user_id", placeholder="أدخل ID المستخدم"))
        self.add_item(discord.ui.TextInput(label="المبلغ", custom_id="amount", placeholder="أدخل المبلغ للسحب"))

    async def on_submit(self, interaction: discord.Interaction):
        target_user_id = int(self.children[0].value)
        amount = float(self.children[1].value)

        if amount <= 0:
            await interaction.response.send_message("❌ لا يمكن سحب مبلغ صفر أو أقل.", ephemeral=True)
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # التحقق من وجود المستخدم ورصيده
            cursor.execute("SELECT balance FROM users WHERE user_id = %s", (target_user_id,))
            user_balance = cursor.fetchone()

            if not user_balance:
                await interaction.response.send_message("❌ المستخدم غير موجود في البنك.", ephemeral=True)
                return
            
            if user_balance[0] < amount:
                await interaction.response.send_message("❌ رصيد المستخدم غير كافٍ لإجراء هذا السحب.", ephemeral=True)
                return
            
            # خصم المبلغ من المستخدم
            cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (amount, target_user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (%s, %s, %s, %s)",
                           (target_user_id, "admin_take", -amount, f"سحب من الإدارة بواسطة {interaction.user.id}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم سحب **{amount} {CURRENCY}** من المستخدم <@{target_user_id}> بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء سحب الأموال: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

class CreateMinistryModal(discord.ui.Modal, title="إنشاء وزارة جديدة"): 
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.TextInput(label="اسم الوزارة", custom_id="ministry_name", placeholder="أدخل اسم الوزارة الجديدة"))

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.children[0].value

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("INSERT INTO ministries (name, balance) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING RETURNING ministry_id", (ministry_name, 0.00))
            ministry_id = cursor.fetchone()

            if ministry_id:
                conn.commit()
                await interaction.response.send_message(f"✅ تم إنشاء وزارة **{ministry_name}** بنجاح!", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ الوزارة **{ministry_name}** موجودة بالفعل.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ أثناء إنشاء الوزارة: {e}", ephemeral=True)
        finally:
            if conn:
                conn.close()

# ============= أوامر البوت =============

@bot.command(name="bank")
async def bank_command(ctx):
    await ctx.send("مرحبًا بك في بنك AL7DOD CITY!", view=MemberMenuView())

@bot.command(name="finmin")
async def finance_minister_command(ctx):
    if not has_role(ctx.author, "وزير المالية") and not is_admin(ctx.author):
        await ctx.send("❌ ليس لديك الصلاحيات الكافية للوصول إلى قائمة وزير المالية.", ephemeral=True)
        return
    await ctx.send("قائمة وزير المالية:", view=FinanceMinisterMenuView())

@bot.command(name="adminpanel")
async def admin_panel_command(ctx):
    if not is_admin(ctx.author):
        await ctx.send("❌ ليس لديك الصلاحيات الكافية للوصول إلى لوحة تحكم الإدارة.", ephemeral=True)
        return
    await ctx.send("لوحة تحكم الإدارة:", view=AdminMenuView())

# تشغيل البوت
if __name__ == '__main__':
    bot.run(BOT_TOKEN)

