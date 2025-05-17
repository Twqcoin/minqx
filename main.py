from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import psycopg2
import os
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

# المتغيرات
TOKEN = os.getenv('TELEGRAM_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

# رموز وإيموجيز للواجهة
EMOJI = {
    'welcome': '✨',
    'user': '👤',
    'id': '🆔',
    'referral': '📨',
    'leaderboard': '🏆',
    'balance': '💰',
    'point': '⭐',
    'medal': ['🥇', '🥈', '🥉', '🎖️', '🎖️', '🎖️', '🎖️', '🎖️', '🎖️', '🎖️'],
    'confetti': '🎉',
    'link': '🔗',
    'error': '⚠️',
    'social': '🌐'
}

# روابط المنصات الاجتماعية
SOCIAL_LINKS = {
    'facebook': 'https://www.facebook.com/khamisalrajab?mibextid=ZbWKwL',
    'tiktok': 'https://www.tiktok.com/@khamis_alrajab?_t=ZS-8wR56ZUugEx&_r=1',
    'youtube': 'https://youtube.com/@missionx_offici?si=4A549AkxABu523zi',
    'telegram': 'https://t.me/MissionX_offici',
    'instagram': 'https://www.instagram.com/missionx_offic?igsh=MWZlMHcyaGZleXlubw==',
    'x': 'https://x.com/MissionX_Offici?t=ZIfH_PyfA-WmFyJ9JzVQCA&s=09'
}

# 1. دوال اتصال قاعدة البيانات
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في الاتصال بقاعدة البيانات: {e}")
        return None

def init_database():
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False
            
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    welcome_bonus_received BOOLEAN DEFAULT FALSE
                )
            """)
            
            c.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id SERIAL PRIMARY KEY,
                    referred_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    referred_by BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (referred_user_id)
                )
            """)
            
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_referrals_by ON referrals(referred_by)
            """)
            
            conn.commit()
            print(f"{EMOJI['confetti']} تم تهيئة قاعدة البيانات بنجاح")
            return True
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في تهيئة قاعدة البيانات: {e}")
        return False
    finally:
        if conn:
            conn.close()

# 2. دوال التعامل مع قاعدة البيانات
def user_exists(user_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False
            
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
            return c.fetchone() is not None
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في التحقق من المستخدم: {e}")
        return False
    finally:
        if conn:
            conn.close()

def add_user(user_id, username, first_name=None):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False
            
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name)
                RETURNING welcome_bonus_received
            """, (user_id, username, first_name))
            
            result = c.fetchone()
            welcome_bonus_received = result[0] if result else True
            conn.commit()
            
            if not welcome_bonus_received:
                c.execute("""
                    UPDATE users 
                    SET balance = balance + 100,
                        welcome_bonus_received = TRUE
                    WHERE user_id = %s
                """, (user_id,))
                conn.commit()
            return True
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في إضافة مستخدم: {e}")
        return False
    finally:
        if conn:
            conn.close()

def add_referral(referred_user_id, referred_by):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return False
            
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM referrals WHERE referred_user_id = %s", (referred_user_id,))
            if c.fetchone():
                return False
                
            if not user_exists(referred_by):
                return False
                
            c.execute("""
                INSERT INTO referrals (referred_user_id, referred_by)
                VALUES (%s, %s)
                RETURNING id
            """, (referred_user_id, referred_by))
            
            if c.fetchone():
                c.execute("""
                    UPDATE users 
                    SET balance = balance + 10 
                    WHERE user_id = %s
                """, (referred_by,))
                conn.commit()
                print(f"{EMOJI['confetti']} تم تسجيل إحالة: {referred_user_id} بواسطة {referred_by}")
                return True
        return False
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في تسجيل الإحالة: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_leaderboard():
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None
            
        with conn.cursor() as c:
            c.execute("""
                SELECT 
                    u.user_id,
                    COALESCE(u.username, u.first_name, 'مستخدم ' || u.user_id::TEXT) as display_name,
                    (SELECT COUNT(*) FROM referrals r WHERE r.referred_by = u.user_id) as referral_count,
                    u.balance
                FROM users u
                ORDER BY referral_count DESC, u.balance DESC
                LIMIT 10
            """)
            return c.fetchall()
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في جلب المتصدرين: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_user_balance(user_id):
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None
            
        with conn.cursor() as c:
            c.execute("""
                SELECT balance FROM users WHERE user_id = %s
            """, (user_id,))
            result = c.fetchone()
            return result[0] if result else 0
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في جلب الرصيد: {e}")
        return None
    finally:
        if conn:
            conn.close()

# 3. دوال أوامر البوت
async def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    print(f"{EMOJI['user']} بدء تشغيل من {user.username or user.id}")
    
    is_new_user = not user_exists(user.id)
    
    if not add_user(user.id, user.username, user.first_name):
        await update.message.reply_text(f"{EMOJI['error']} حدث خطأ في التسجيل")
        return
    
    if is_new_user:
        await update.message.reply_text(
            f"{EMOJI['confetti']} مبروك! لقد حصلت على 100 نقطة ترحيبية!",
            parse_mode='Markdown'
        )
    
    if context.args and context.args[0].isdigit():
        referral_id = int(context.args[0])
        if referral_id != user.id:
            if add_referral(user.id, referral_id):
                await update.message.reply_text(f"{EMOJI['confetti']} تم تسجيل إحالتك بنجاح وحصلت على {EMOJI['point']}10 نقاط!")
    
    welcome_message = f"""
{EMOJI['welcome']} *مرحباً {user.first_name or 'صديقي العزيز'}!* {EMOJI['welcome']}

{EMOJI['user']} *اسمك:* {user.first_name or 'لاعب جديد'}
{EMOJI['id']} *رقمك:* `{user.id}`

{EMOJI['confetti']} *لقد حصلت على 100 نقطة ترحيبية!*

{EMOJI['link']} استخدم /referral لدعوة الأصدقاء
{EMOJI['leaderboard']} استخدم /leaderboard لرؤية المتصدرين
{EMOJI['balance']} استخدم /balance لمعرفة رصيدك

{EMOJI['social']} *تابعنا على المنصات الاجتماعية:*
🔗 [فيسبوك]({SOCIAL_LINKS['facebook']})
🐦 [إكس (تويتر)]({SOCIAL_LINKS['x']})
🎵 [تيك توك]({SOCIAL_LINKS['tiktok']})
🎥 [يوتيوب]({SOCIAL_LINKS['youtube']})
📢 [تلجرام]({SOCIAL_LINKS['telegram']})
📸 [إنستجرام]({SOCIAL_LINKS['instagram']})
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown', disable_web_page_preview=True)

async def leaderboard(update: Update, context: CallbackContext):
    leaderboard_data = get_leaderboard()
    
    if not leaderboard_data:
        await update.message.reply_text(f"{EMOJI['leaderboard']} لا يوجد بيانات متاحة حالياً!")
        return
    
    leaderboard_text = f"{EMOJI['leaderboard']} *أفضل 10 لاعبين:*\n\n"
    
    for i, (user_id, display_name, referral_count, balance) in enumerate(leaderboard_data, 1):
        medal = EMOJI['medal'][i-1] if i <= 3 else f"{i}."
        leaderboard_text += (
            f"{medal} *{display_name}*\n"
            f"   {EMOJI['point']} {referral_count or 0} إحالة\n"
            f"   {EMOJI['balance']} {balance or 0} نقطة\n\n"
        )
    
    leaderboard_text += f"{EMOJI['link']} استخدم /referral لزيادة نقاطك!"
    await update.message.reply_text(leaderboard_text, parse_mode='Markdown')

async def referral(update: Update, context: CallbackContext):
    user = update.message.from_user
    link = f"https://t.me/MissionxX_bot?start={user.id}"
    balance = get_user_balance(user.id) or 0
    
    referral_message = f"""
{EMOJI['link']} *رابط الإحالة الخاص بك:*
`{link}`

{EMOJI['balance']} *رصيدك الحالي:* {balance} {EMOJI['point']}

{EMOJI['confetti']} *معلومات الإحالة:*
- ستحصل على {EMOJI['point']}10 نقاط لكل صديق ينضم عبر الرابط
- كلما زاد عدد الإحالات، ارتفع ترتيبك في لوحة المتصدرين {EMOJI['leaderboard']}

{EMOJI['social']} *تابعنا على المنصات الاجتماعية:*
🔗 [فيسبوك]({SOCIAL_LINKS['facebook']})
🐦 [إكس (تويتر)]({SOCIAL_LINKS['x']})
🎵 [تيك توك]({SOCIAL_LINKS['tiktok']})
🎥 [يوتيوب]({SOCIAL_LINKS['youtube']})
📢 [تلجرام]({SOCIAL_LINKS['telegram']})
📸 [إنستجرام]({SOCIAL_LINKS['instagram']})
"""
    await update.message.reply_text(referral_message, parse_mode='Markdown', disable_web_page_preview=True)

async def balance(update: Update, context: CallbackContext):
    user = update.message.from_user
    balance = get_user_balance(user.id)
    
    if balance is None:
        await update.message.reply_text(f"{EMOJI['error']} حدث خطأ في جلب الرصيد")
        return
    
    balance_message = f"""
{EMOJI['balance']} *رصيدك الحالي:* {balance} {EMOJI['point']}

{EMOJI['link']} استخدم /referral لكسب المزيد من النقاط
{EMOJI['leaderboard']} استخدم /leaderboard لرؤية ترتيبك

{EMOJI['social']} *تابعنا على المنصات الاجتماعية:*
🔗 [فيسبوك]({SOCIAL_LINKS['facebook']})
🐦 [إكس (تويتر)]({SOCIAL_LINKS['x']})
🎵 [تيك توك]({SOCIAL_LINKS['tiktok']})
🎥 [يوتيوب]({SOCIAL_LINKS['youtube']})
📢 [تلجرام]({SOCIAL_LINKS['telegram']})
📸 [إنستجرام]({SOCIAL_LINKS['instagram']})
"""
    await update.message.reply_text(balance_message, parse_mode='Markdown', disable_web_page_preview=True)

async def error_handler(update: object, context: CallbackContext) -> None:
    print(f"{EMOJI['error']} حدث خطأ: {context.error}")
    if update and hasattr(update, 'message'):
        await update.message.reply_text(f"{EMOJI['error']} حدث خطأ غير متوقع. يرجى المحاولة لاحقًا.")

# 4. الدالة الرئيسية
def main():
    print(f"{EMOJI['welcome']} بدء تشغيل البوت...")
    
    if not TOKEN or not DATABASE_URL:
        print(f"{EMOJI['error']} يرجى تعيين المتغيرات البيئية")
        return
    
    if not init_database():
        print(f"{EMOJI['error']} فشل في تهيئة قاعدة البيانات")
        return
    
    try:
        app = Application.builder() \
            .token(TOKEN) \
            .concurrent_updates(True) \
            .build()
        
        app.add_error_handler(error_handler)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("referral", referral))
        app.add_handler(CommandHandler("leaderboard", leaderboard))
        app.add_handler(CommandHandler("balance", balance))
        
        print(f"{EMOJI['confetti']} البوت يعمل الآن...")
        app.run_polling(
            poll_interval=2.0,
            timeout=20,
            drop_pending_updates=True
        )
        
    except Exception as e:
        print(f"{EMOJI['error']} خطأ في التشغيل الرئيسي: {e}")
    finally:
        print(f"{EMOJI['error']} إيقاف البوت...")

if __name__ == "__main__":
    main()
