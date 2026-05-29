import os

code = '''import asyncio
import logging
import os
import re
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from gsheets import append_row

load_dotenv(override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if not BOT_TOKEN:
    exit("Ошибка: Не указан BOT_TOKEN в .env файле")

CONTACT, Q1, Q2, Q3, Q4, Q5 = range(6)

QUESTIONS = [
    "📊 <b>Вопрос 1:</b> План найма за год, чел.\\n(Например: <i>50</i>)",
    "💵 <b>Вопрос 2:</b> Средняя зарплата, ₽/мес с налогами\\n(Например: <i>120000</i>)",
    "⏳ <b>Вопрос 3:</b> Длительность испытательного срока (мес)\\n(Например: <i>3</i>)",
    "🎓 <b>Вопрос 4:</b> Стоимость найма и обучения одного сотрудника, ₽\\n(Например: <i>80000</i>)",
    "📉 <b>Вопрос 5:</b> Текущая доля увольнений на ИС, %\\n(Например: <i>27</i> или <i>27%</i>)"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact_button = KeyboardButton(text="📱 Поделиться контактом", request_contact=True)
    custom_keyboard = [[contact_button]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "Привет! 👋\\nЧтобы участвовать в розыгрыше, ответьте на наши вопросы.\\n\\nДля начала, пожалуйста, поделитесь контактом, нажав на кнопку ниже.",
        reply_markup=reply_markup
    )
    return CONTACT

async def process_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Пожалуйста, нажмите на специальную кнопку «📱 Поделиться контактом» внизу экрана.")
        return CONTACT
        
    context.user_data['phone'] = contact.phone_number
    context.user_data['first_name'] = contact.first_name
    context.user_data['last_name'] = contact.last_name or ""

    await update.message.reply_text(
        f"Спасибо, {contact.first_name}! Теперь ответьте на 5 коротких вопросов.\\n\\n{QUESTIONS[0]}",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='HTML'
    )
    return Q1

async def process_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q1'] = update.message.text
    await update.message.reply_text(QUESTIONS[1], parse_mode='HTML')
    return Q2

async def process_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q2'] = update.message.text
    await update.message.reply_text(QUESTIONS[2], parse_mode='HTML')
    return Q3

async def process_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q3'] = update.message.text
    await update.message.reply_text(QUESTIONS[3], parse_mode='HTML')
    return Q4

async def process_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q4'] = update.message.text
    await update.message.reply_text(QUESTIONS[4], parse_mode='HTML')
    return Q5

async def process_q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q5_answer = update.message.text
    context.user_data['q5'] = q5_answer
    
    await update.message.reply_text("⏳ Считаем результаты...")

    # Умная функция извлечения чисел из текста (понимает "120 000", "27%", "доля 27 %")
    def parse_float(val):
        try:
            match = re.search(r'\d+(?:[.,\s]\d+)*', str(val))
            if match:
                clean_val = match.group(0).replace(',', '.').replace(' ', '').strip()
                return float(clean_val)
            return 0.0
        except:
            return 0.0

    def parse_money(val):
        v = parse_float(val)
        # Если ввели 120 вместо 120000, программа сама поймет что это тысячи
        if 0 < v < 1000:
            return v * 1000
        return v

    plan = parse_float(context.user_data.get('q1', '0'))
    salary_rub = parse_money(context.user_data.get('q2', '0'))
    probation = parse_float(context.user_data.get('q3', '0'))
    hiring_cost_rub = parse_money(context.user_data.get('q4', '0'))
    turnover_rate = parse_float(context.user_data.get('q5', '0'))

    # Математика по вашим формулам
    cost_mistake_rub = (salary_rub * probation) + hiring_cost_rub
    cost_now_rub = plan * (turnover_rate / 100.0) * cost_mistake_rub
    cost_after_rub = plan * ((turnover_rate / 100.0) * 0.70) * cost_mistake_rub
    
    savings_rub = cost_now_rub - cost_after_rub
    
    # Экономия в % всегда будет 30% исходя из формулы (100% - 30%), но на всякий случай проверяем что есть затраты
    savings_pct = 30.0 if cost_now_rub > 0 else 0.0

    # Форматирование чисел для красивого вывода с пробелами (например 1 200 000 ₽)
    def fmt(num):
        return f"{num:,.0f}".replace(',', ' ')

    result_text = (
        f"📊 <b>Ваши результаты:</b>\\n\\n"
        f"❗️ <b>Цена кадровой ошибки на 1 сотрудника:</b> {fmt(cost_mistake_rub)} ₽\\n"
        f"📉 <b>Годовые затраты «сейчас»:</b> {fmt(cost_now_rub)} ₽\\n"
        f"✅ <b>Годовые затраты «после внедрения»:</b> {fmt(cost_after_rub)} ₽\\n\\n"
        f"💰 <b>Ваша экономия:</b> {fmt(savings_rub)} ₽ ({savings_pct:,.0f}%)"
    )

    await update.message.reply_text(result_text, parse_mode='HTML')

    row_data = [
        context.user_data.get('phone'),
        context.user_data.get('first_name'),
        context.user_data.get('last_name'),
        context.user_data.get('q1'),
        context.user_data.get('q2'),
        context.user_data.get('q3'),
        context.user_data.get('q4'),
        context.user_data.get('q5'),
        cost_mistake_rub,
        cost_now_rub,
        cost_after_rub,
        savings_rub
    ]

    try:
        await append_row(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_URL, row_data)
        await update.message.reply_text("✅ Спасибо! Ваши данные успешно сохранены, вы участвуете в розыгрыше.")
    except Exception as e:
        import traceback
        logging.error(f"Ошибка при записи в Google табличку: {e}")
        logging.error(traceback.format_exc())
        await update.message.reply_text("Произошла ошибка при сохранении в Google Таблицу.")

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Опрос отменен.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CONTACT: [MessageHandler(filters.CONTACT, process_contact),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, process_contact)],
            Q1: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_q1)],
            Q2: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_q2)],
            Q3: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_q3)],
            Q4: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_q4)],
            Q5: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_q5)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    
    print("Бот успешно запущен и готов к работе!")
    app.run_polling()

if __name__ == '__main__':
    main()
'''

with open("main.py", "w", encoding="utf-8") as f:
    f.write(code)
