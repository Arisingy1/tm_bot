import asyncio
import logging
import os
import re
from turtle import update
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from gsheets import append_row

load_dotenv(override=True)

BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

if not BOT_TOKEN:
    exit('Ошибка: Не указан BOT_TOKEN в .env файле')

CONTACT, Q1, Q2, Q3, Q4, Q5 = range(6)

QUESTIONS = [
    '📌 Вопрос 1 из 5\n\n📈 Сколько сотрудников вы планируете нанять в ближайшие 12 месяцев?\n\nПример ответа:\n50',
    '📌 Вопрос 2 из 5\n\n💰 Какая средняя зарплата сотрудника в месяц?\n(Укажите сумму с налогами)\n\nПример ответа:\n120000',
    '📌 Вопрос 3 из 5\n\n⏳ Сколько длится испытательный срок?\n(в месяцах)\n\nПример ответа:\n3',
    '📌 Вопрос 4 из 5\n\n🎯 Сколько в среднем стоит найм и адаптация одного сотрудника?\n(поиск, HR, онбординг, обучение)\n\nПример ответа:\n50000',
    '📌 Вопрос 5 из 5\n\n📉 Какой процент сотрудников увольняется во время испытательного срока?\n\nПример ответа:\n27%'
]

COMPLETED_USERS_FILE = 'completed_users.txt'

def has_user_completed(user_id):
    if not os.path.exists(COMPLETED_USERS_FILE):
        return False
    with open(COMPLETED_USERS_FILE, 'r') as f:
        completed = set(line.strip() for line in f)
    return str(user_id) in completed

def mark_user_completed(user_id):
    with open(COMPLETED_USERS_FILE, 'a') as f:
        f.write(f'{user_id}\n')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if has_user_completed(update.message.from_user.id):
        await update.message.reply_text('👋 Вы уже прошли этот опрос. Спасибо за участие!')
        return ConversationHandler.END

    contact_button = KeyboardButton(text='📱 Поделиться контактом', request_contact=True)
    custom_keyboard = [[contact_button]]
    reply_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        '👋 Добро пожаловать в TalentMind!\n\n'
        'Пройдите короткий опрос из 5 вопросов и получите:\n\n'
        '📊 расчет потерь вашей компании от ошибок найма\n'
        '📈 сводную HR-аналитику в среднем по рынку\n'
        '🎁 участие в нашем розыгрыше!\n\n'
        'Это займет не более 2 минут.\n\n'
        'Для начала, пожалуйста, поделитесь своим контактом, нажав на кнопку ниже.',
        reply_markup=reply_markup
    )
    return CONTACT

async def process_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    if not contact:
        await update.message.reply_text('Пожалуйста, используйте кнопку для отправки контакта.')
        return CONTACT
        
    context.user_data['phone'] = contact.phone_number
    context.user_data['first_name'] = contact.first_name
    context.user_data['last_name'] = contact.last_name or ''

    await update.message.reply_text(
        f'Спасибо, {contact.first_name}!\n\n{QUESTIONS[0]}',
        reply_markup=ReplyKeyboardRemove()
    )
    return Q1

async def process_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q1'] = update.message.text
    await update.message.reply_text(QUESTIONS[1])
    return Q2

async def process_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q2'] = update.message.text
    await update.message.reply_text(QUESTIONS[2])
    return Q3

async def process_q3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q3'] = update.message.text
    await update.message.reply_text(QUESTIONS[3])
    return Q4

async def process_q4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['q4'] = update.message.text
    await update.message.reply_text(QUESTIONS[4])
    return Q5

async def process_q5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q5_answer = update.message.text
    context.user_data['q5'] = q5_answer
    
    processing_msg = await update.message.reply_text('⏳ Отлично! Анализируем данные...')

    def parse_float(val):
        try:
            val = val.replace(',', '.').replace(' ', '').replace(' ', '').strip()
            # Извлекаем первое попавшееся число из строки
            import re
            m = re.search(r'\d+(?:\.\d+)?', val)
            if m:
                return float(m.group(0))
            return 0.0
        except:
            return 0.0

    plan = parse_float(context.user_data.get('q1', '0'))
    salary_rub = parse_float(context.user_data.get('q2', '0'))
    probation = parse_float(context.user_data.get('q3', '0'))
    hiring_cost_rub = parse_float(context.user_data.get('q4', '0'))
    turnover_rate = parse_float(context.user_data.get('q5', '0'))

    # Расчёты
    cost_mistake_rub = (salary_rub * probation) + hiring_cost_rub
    cost_now_rub = plan * (turnover_rate / 100.0) * cost_mistake_rub
    cost_after_rub = plan * ((turnover_rate / 100.0) * 0.70) * cost_mistake_rub
    savings_rub = cost_now_rub - cost_after_rub
    savings_pct = 30.0 if cost_now_rub > 0 else 0.0

    # Форматирование чисел
    def fmt(num):
        return f'{num:,.0f}'.replace(',', ' ')

    comp_now_pct = abs(cost_now_rub - 2500000) / 2500000 * 100
    comp_now = "выше" if cost_now_rub > 2500000 else "ниже"

    comp_mistake_pct = abs(cost_mistake_rub - 250000) / 250000 * 100
    comp_mistake = "выше" if cost_mistake_rub > 250000 else "ниже"

    result_text = (
        f'📊 <b>Ваша персональная HR-аналитика:</b>\n\n'
        f'💸 <b>Стоимость одной ошибки найма:</b>\n'
        f'{fmt(cost_mistake_rub)} ₽\n'
        f'<i>что {comp_mistake} на {comp_mistake_pct:.0f}% чем среднее рыночное значение</i>\n\n'
        f'📉 <b>Текущие годовые потери компании:</b>\n'
        f'{fmt(cost_now_rub)} ₽\n'
        f'<i>что {comp_now} на {comp_now_pct:.0f}% чем среднее рыночное значение</i>\n\n'
    )

    try:
        await processing_msg.delete()
    except Exception:
        pass

    with open('слайд.png', 'rb') as photo:
        await update.message.reply_photo(photo=photo, caption=result_text, parse_mode='HTML')

    try:
        with open('HR-СТАТИСТИКА.pdf', 'rb') as pdf:
            await update.message.reply_document(document=pdf)
    except Exception as e:
        logging.error(f'Ошибка отправки PDF: {e}')

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
        mark_user_completed(update.message.from_user.id)
        await update.message.reply_text(
            '🎉 <b>Спасибо!</b>\n\n'
            'Ваши данные успешно сохранены.\n'
            '🍀 <b>Вы стали участником розыгрыша от TalentMind!</b>\n\n'
            '📌 <b>Условия участия:</b>\n'
            '• Быть подписанным на Telegram-канал TalentMind\n'
            '• Указать корректные контакты\n'
            'Победители будут определены случайным образом, результаты опубликуем в канале. Удачи!',
            parse_mode='HTML'
        )
    except Exception as e:
        import traceback
        logging.error(f'Ошибка при записи в Google табличку: {e}')
        logging.error(traceback.format_exc())
        await update.message.reply_text('Произошла ошибка при сохранении в Google Таблицу.')

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
    app.run_polling()

if __name__ == '__main__':
    main()
