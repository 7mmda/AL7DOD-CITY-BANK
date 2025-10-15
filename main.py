import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import sqlite3
from datetime import datetime, timedelta

from config import BOT_TOKEN, DATABASE_NAME
from database import init_db, get_db_connection

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

CURRENCY = "ريال الحدود"

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
    init_db()
    print("Database ensured to be initialized.")
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
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, last_paid FROM salaries")
        salaries_data = cursor.fetchall()

        for user_data in salaries_data:
            user_id = user_data["user_id"]
            last_paid_str = user_data["last_paid"]
            last_paid = datetime.strptime(last_paid_str, 
'%Y-%m-%d %H:%M:%S')

            if datetime.now() - last_paid >= timedelta(hours=3):
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

@tasks.loop(minutes=10)
async def process_investments():
    """مهمة معالجة الاستثمارات المنتهية"""
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

            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_return, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "investment_return", total_return, f"عائد استثمار رقم {investment_id} (أصل + ربح)"))
            cursor.execute("UPDATE investments SET status = ? WHERE investment_id = ?", ("completed", investment_id))
            print(f"Processed investment {investment_id} for user {user_id}. Returned {total_return}")

        conn.commit()
    except Exception as e:
        print(f"Error processing investments: {e}")
    finally:
        conn.close()

# ============= القوائم التفاعلية =============

# قائمة الأعضاء الرئيسية
class MemberMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 فتح حساب", style=discord.ButtonStyle.green, custom_id="open_account")
    async def open_account_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                await interaction.response.send_message("لديك بالفعل حساب بنكي!", ephemeral=True)
            else:
                initial_balance = 1500.00
                cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, initial_balance))
                cursor.execute("INSERT INTO salaries (user_id, last_paid) VALUES (?, ?)", (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                               (user_id, "deposit", initial_balance, "رصيد مبدئي لفتح الحساب"))
                conn.commit()
                await interaction.response.send_message(f"✅ تم فتح حساب بنكي لك بنجاح!\n💵 رصيدك المبدئي: **{initial_balance} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

    @discord.ui.button(label="💳 رصيدي", style=discord.ButtonStyle.primary, custom_id="check_balance")
    async def check_balance_button(self, interaction: discord.Interaction, button: Button):
        user_id = interaction.user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance, card_type FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if user:
                embed = discord.Embed(title="💳 رصيدك الحالي", color=discord.Color.blue())
                embed.add_field(name="المبلغ", value=f"**{user['balance']} {CURRENCY}**", inline=False)
                embed.add_field(name="نوع البطاقة", value=f"**{user['card_type'].capitalize()}**", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي. استخدم زر **فتح حساب** أولاً.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
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
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT amount, start_date, end_date, return_rate, status FROM investments WHERE user_id = ? ORDER BY status DESC, end_date ASC", (user_id,))
            investments = cursor.fetchall()

            if not investments:
                await interaction.response.send_message("❌ ليس لديك أي استثمارات حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="📊 استثماراتك", color=discord.Color.green())
            for inv in investments:
                status_text = "🟢 نشط" if inv["status"] == "active" else "✅ منتهي"
                embed.add_field(name=f"💰 {inv['amount']} {CURRENCY}",
                                value=f"📅 بدء: {inv['start_date']}\n📅 انتهاء: {inv['end_date']}\n📈 عائد: {inv['return_rate']*100:.0f}%\n{status_text}",
                                inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

    @discord.ui.button(label="💎 البطاقات", style=discord.ButtonStyle.secondary, custom_id="cards")
    async def cards_button(self, interaction: discord.Interaction, button: Button):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT card_name, price, benefits FROM cards ORDER BY price ASC")
            cards = cursor.fetchall()

            if not cards:
                await interaction.response.send_message("❌ لا توجد بطاقات متاحة حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="💎 البطاقات البنكية المتاحة", description="اختر البطاقة التي تناسبك!", color=discord.Color.purple())
            for card in cards:
                embed.add_field(name=f"{card['card_name'].capitalize()} - {card['price']} {CURRENCY}", value=card['benefits'], inline=False)
            
            view = BuyCardView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
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

    @discord.ui.button(label="📋 ميزانيات الوزارات", style=discord.ButtonStyle.primary, custom_id="view_ministries")
    async def view_ministries_button(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, "وزير المالية") and not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط لوزير المالية!", ephemeral=True)
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, balance FROM ministries")
            ministries = cursor.fetchall()
            if not ministries:
                await interaction.response.send_message("❌ لا توجد وزارات مسجلة حاليًا.", ephemeral=True)
                return

            embed = discord.Embed(title="🏛️ ميزانيات الوزارات", color=discord.Color.blue())
            for ministry in ministries:
                embed.add_field(name=ministry["name"], value=f"**{ministry['balance']} {CURRENCY}**", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

    @discord.ui.button(label="💰 سحب من وزارة", style=discord.ButtonStyle.danger, custom_id="withdraw_ministry")
    async def withdraw_ministry_button(self, interaction: discord.Interaction, button: Button):
        if not has_role(interaction.user, "وزير المالية") and not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط لوزير المالية!", ephemeral=True)
            return
        await interaction.response.send_modal(WithdrawMinistryModal())

# قائمة الإدارة
class AdminMenuView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💵 إعطاء أموال", style=discord.ButtonStyle.green, custom_id="give_money")
    async def give_money_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(GiveMoneyModal())

    @discord.ui.button(label="💸 سحب أموال", style=discord.ButtonStyle.danger, custom_id="take_money")
    async def take_money_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(TakeMoneyModal())

    @discord.ui.button(label="🏛️ إدارة الوزارات", style=discord.ButtonStyle.primary, custom_id="manage_ministries")
    async def manage_ministries_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        await interaction.response.send_modal(ManageMinistryModal())

    @discord.ui.button(label="👥 أغنى الناس", style=discord.ButtonStyle.secondary, custom_id="richest_people")
    async def richest_people_button(self, interaction: discord.Interaction, button: Button):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذا الخيار متاح فقط للإدارة!", ephemeral=True)
            return
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
            richest = cursor.fetchall()
            
            if not richest:
                await interaction.response.send_message("❌ لا توجد بيانات متاحة.", ephemeral=True)
                return

            embed = discord.Embed(title="👑 أغنى 10 أشخاص في السيرفر", color=discord.Color.gold())
            for i, user_data in enumerate(richest, 1):
                user = await bot.fetch_user(user_data["user_id"])
                embed.add_field(name=f"{i}. {user.name}", value=f"**{user_data['balance']} {CURRENCY}**", inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

# ============= Modals (نماذج الإدخال) =============

class TransferModal(discord.ui.Modal, title="💸 تحويل أموال"):
    user_id_input = discord.ui.TextInput(label="ID المستخدم المستلم", placeholder="أدخل ID المستخدم", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        sender_id = interaction.user.id
        try:
            receiver_id = int(self.user_id_input.value)
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال قيم صحيحة!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ أكبر من صفر.", ephemeral=True)
            return
        if sender_id == receiver_id:
            await interaction.response.send_message("❌ لا يمكنك تحويل الأموال إلى نفسك.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
            sender = cursor.fetchone()
            if not sender:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي.", ephemeral=True)
                return

            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (receiver_id,))
            receiver = cursor.fetchone()
            if not receiver:
                await interaction.response.send_message("❌ المستلم ليس لديه حساب بنكي.", ephemeral=True)
                return

            if sender["balance"] < amount:
                await interaction.response.send_message("❌ رصيدك لا يكفي لإجراء هذا التحويل.", ephemeral=True)
                return

            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (sender_id, "transfer_send", amount, f"تحويل إلى {receiver_id}"))

            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, receiver_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (receiver_id, "transfer_receive", amount, f"تحويل من {sender_id}"))

            conn.commit()
            await interaction.response.send_message(f"✅ تم تحويل **{amount} {CURRENCY}** بنجاح!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class InvestModal(discord.ui.Modal, title="📈 بدء استثمار"):
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)
    days_input = discord.ui.TextInput(label="عدد الأيام", placeholder="أدخل عدد الأيام", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            amount = float(self.amount_input.value)
            days = int(self.days_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال قيم صحيحة!", ephemeral=True)
            return

        if amount <= 0 or days <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ والمدة أكبر من صفر.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي.", ephemeral=True)
                return

            if user["balance"] < amount:
                await interaction.response.send_message("❌ رصيدك لا يكفي لإجراء هذا الاستثمار.", ephemeral=True)
                return

            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "investment_start", -amount, f"بدء استثمار بمبلغ {amount} لمدة {days} أيام"))

            start_date = datetime.now()
            end_date = start_date + timedelta(days=days)
            return_rate = 0.05

            cursor.execute("INSERT INTO investments (user_id, amount, start_date, end_date, return_rate, status) VALUES (?, ?, ?, ?, ?, ?)",
                           (user_id, amount, start_date.strftime("%Y-%m-%d %H:%M:%S"), end_date.strftime("%Y-%m-%d %H:%M:%S"), return_rate, "active"))
            conn.commit()
            await interaction.response.send_message(f"✅ تم بدء استثمار بمبلغ **{amount} {CURRENCY}** لمدة **{days} أيام**.\n📅 سينتهي في: {end_date.strftime('%Y-%m-%d %H:%M:%S')}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class DistributeBudgetModal(discord.ui.Modal, title="🏛️ توزيع ميزانية"):
    ministry_name_input = discord.ui.TextInput(label="اسم الوزارة", placeholder="مثال: الداخلية", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.ministry_name_input.value
        try:
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال مبلغ صحيح!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ أكبر من صفر.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO ministries (name, balance) VALUES (?, COALESCE((SELECT balance FROM ministries WHERE name = ?), 0) + ?)", (ministry_name, ministry_name, amount))
            conn.commit()
            cursor.execute("SELECT balance FROM ministries WHERE name = ?", (ministry_name,))
            new_balance = cursor.fetchone()["balance"]
            await interaction.response.send_message(f"✅ تم توزيع **{amount} {CURRENCY}** على وزارة **{ministry_name}**.\n💰 رصيدها الجديد: **{new_balance} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class WithdrawMinistryModal(discord.ui.Modal, title="💰 سحب من وزارة"):
    ministry_name_input = discord.ui.TextInput(label="اسم الوزارة", placeholder="مثال: الداخلية", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.ministry_name_input.value
        try:
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال مبلغ صحيح!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ أكبر من صفر.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM ministries WHERE name = ?", (ministry_name,))
            ministry = cursor.fetchone()
            if not ministry:
                await interaction.response.send_message(f"❌ الوزارة **{ministry_name}** غير موجودة.", ephemeral=True)
                return

            if ministry["balance"] < amount:
                await interaction.response.send_message(f"❌ رصيد الوزارة لا يكفي. الرصيد الحالي: **{ministry['balance']} {CURRENCY}**", ephemeral=True)
                return

            cursor.execute("UPDATE ministries SET balance = balance - ? WHERE name = ?", (amount, ministry_name))
            conn.commit()
            cursor.execute("SELECT balance FROM ministries WHERE name = ?", (ministry_name,))
            new_balance = cursor.fetchone()["balance"]
            await interaction.response.send_message(f"✅ تم سحب **{amount} {CURRENCY}** من وزارة **{ministry_name}**.\n💰 رصيدها الجديد: **{new_balance} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class GiveMoneyModal(discord.ui.Modal, title="💵 إعطاء أموال"):
    user_id_input = discord.ui.TextInput(label="ID المستخدم", placeholder="أدخل ID المستخدم", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id_input.value)
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال قيم صحيحة!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ أكبر من صفر.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                await interaction.response.send_message("❌ المستخدم ليس لديه حساب بنكي.", ephemeral=True)
                return

            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "admin_give", amount, f"إعطاء من الإدارة بواسطة {interaction.user.name}"))
            conn.commit()
            await interaction.response.send_message(f"✅ تم إعطاء **{amount} {CURRENCY}** للمستخدم <@{user_id}>", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class TakeMoneyModal(discord.ui.Modal, title="💸 سحب أموال"):
    user_id_input = discord.ui.TextInput(label="ID المستخدم", placeholder="أدخل ID المستخدم", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ", placeholder="أدخل المبلغ", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id_input.value)
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال قيم صحيحة!", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ يجب أن يكون المبلغ أكبر من صفر.", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                await interaction.response.send_message("❌ المستخدم ليس لديه حساب بنكي.", ephemeral=True)
                return

            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "admin_take", -amount, f"سحب من الإدارة بواسطة {interaction.user.name}"))
            conn.commit()
            await interaction.response.send_message(f"✅ تم سحب **{amount} {CURRENCY}** من المستخدم <@{user_id}>", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

class ManageMinistryModal(discord.ui.Modal, title="🏛️ إدارة الوزارات"):
    ministry_name_input = discord.ui.TextInput(label="اسم الوزارة", placeholder="مثال: الداخلية", required=True)
    amount_input = discord.ui.TextInput(label="المبلغ (+ للإضافة، - للسحب)", placeholder="مثال: 5000 أو -2000", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        ministry_name = self.ministry_name_input.value
        try:
            amount = float(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال مبلغ صحيح!", ephemeral=True)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO ministries (name, balance) VALUES (?, COALESCE((SELECT balance FROM ministries WHERE name = ?), 0) + ?)", (ministry_name, ministry_name, amount))
            conn.commit()
            cursor.execute("SELECT balance FROM ministries WHERE name = ?", (ministry_name,))
            new_balance = cursor.fetchone()["balance"]
            
            action = "إضافة" if amount > 0 else "سحب"
            await interaction.response.send_message(f"✅ تم {action} **{abs(amount)} {CURRENCY}** {'إلى' if amount > 0 else 'من'} وزارة **{ministry_name}**.\n💰 رصيدها الجديد: **{new_balance} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

# قائمة شراء البطاقات
class BuyCardView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🥈 فضية (5000)", style=discord.ButtonStyle.secondary, custom_id="buy_silver")
    async def buy_silver(self, interaction: discord.Interaction, button: Button):
        await self.buy_card(interaction, "silver")

    @discord.ui.button(label="🥇 ذهبية (15000)", style=discord.ButtonStyle.primary, custom_id="buy_gold")
    async def buy_gold(self, interaction: discord.Interaction, button: Button):
        await self.buy_card(interaction, "gold")

    @discord.ui.button(label="💎 بلاتينيوم (50000)", style=discord.ButtonStyle.success, custom_id="buy_platinum")
    async def buy_platinum(self, interaction: discord.Interaction, button: Button):
        await self.buy_card(interaction, "platinum")

    async def buy_card(self, interaction: discord.Interaction, card_name: str):
        user_id = interaction.user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                await interaction.response.send_message("❌ ليس لديك حساب بنكي.", ephemeral=True)
                return

            cursor.execute("SELECT price, benefits FROM cards WHERE card_name = ?", (card_name,))
            card_info = cursor.fetchone()

            if not card_info:
                await interaction.response.send_message("❌ البطاقة غير متاحة.", ephemeral=True)
                return

            card_price = card_info["price"]
            current_card_type = user["card_type"]

            if current_card_type == card_name:
                await interaction.response.send_message(f"❌ لديك بالفعل بطاقة {card_name}.", ephemeral=True)
                return

            if user["balance"] < card_price:
                await interaction.response.send_message(f"❌ رصيدك الحالي ({user['balance']} {CURRENCY}) لا يكفي لشراء بطاقة {card_name} بسعر {card_price} {CURRENCY}.", ephemeral=True)
                return

            cursor.execute("UPDATE users SET balance = balance - ?, card_type = ? WHERE user_id = ?", (card_price, card_name, user_id))
            cursor.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                           (user_id, "card_purchase", -card_price, f"شراء بطاقة {card_name}"))
            conn.commit()
            await interaction.response.send_message(f"✅ تهانينا! لقد اشتريت بطاقة **{card_name}** بنجاح بسعر **{card_price} {CURRENCY}**.\n💳 رصيدك الجديد: **{user['balance'] - card_price} {CURRENCY}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
        finally:
            conn.close()

# ============= أوامر لإظهار القوائم =============

@bot.command(name="بنك")
async def bank_menu(ctx):
    """عرض قائمة البنك الرئيسية للأعضاء"""
    embed = discord.Embed(
        title="🏦 بنك الحدود",
        description=f"مرحبًا بك في **بنك الحدود**!\nالعملة الرسمية: **{CURRENCY}** 💰\n\nاختر الخدمة المناسبة من القائمة أدناه:",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url="https://i.imgur.com/your_bank_logo.png")  # يمكنك تغيير الرابط لشعار البنك
    view = MemberMenuView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="وزير_المالية")
async def finance_minister_menu(ctx):
    """عرض قائمة وزير المالية"""
    if not has_role(ctx.author, "وزير المالية") and not is_admin(ctx.author):
        await ctx.send("❌ هذا الأمر متاح فقط لوزير المالية!")
        return
    
    embed = discord.Embed(
        title="🏛️ لوحة تحكم وزير المالية",
        description="إدارة ميزانيات الوزارات والخزينة العامة",
        color=discord.Color.blue()
    )
    view = FinanceMinisterMenuView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="ادارة")
async def admin_menu(ctx):
    """عرض قائمة الإدارة"""
    if not is_admin(ctx.author):
        await ctx.send("❌ هذا الأمر متاح فقط للإدارة!")
        return
    
    embed = discord.Embed(
        title="⚙️ لوحة التحكم الإدارية",
        description="صلاحيات كاملة لإدارة البنك والأموال",
        color=discord.Color.red()
    )
    view = AdminMenuView()
    await ctx.send(embed=embed, view=view)

# ============= تشغيل البوت =============
if BOT_TOKEN == "YOUR_BOT_TOKEN":
    print("الرجاء تحديث ملف config.py بتوكن البوت الخاص بك.")
else:
    bot.run(BOT_TOKEN)

