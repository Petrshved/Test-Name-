import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
    JobQueue
)
import sqlite3
import re
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_IDS = [1143847626, 835835917]  # Замените на ваш реальный ID

delivery1 = 500
delivery2 = 3000


# Состояния для ConversationHandler
(
    ENTER_TRACKING_NUMBER, ENTER_CONTENTS, ENTER_ORIGIN, ENTER_DESTINATION,
    ENTER_SHIPPING_DATE, ENTER_ARRIVAL_DATE, ENTER_WEIGHT, ENTER_CARGO_COST,
    ENTER_DELIVERY_COST, EDIT_PARCEL_CHOICE, EDIT_PARCEL_FIELD, DELETE_PARCEL,
    MANAGE_STAGES, ENTER_STAGE_UPDATE, ENTER_CLIENT_ORIGIN, ENTER_CLIENT_DESTINATION,
    ENTER_CLIENT_WEIGHT, ENTER_PACKAGE_TYPE, CONFIRM_ORDER  # Состояния до 18
) = range(19)  # Обновлено до 19

# Функция для подключения к базе данных
def get_db_connection():
    conn = sqlite3.connect('parcels.db')
    conn.row_factory = sqlite3.Row
    return conn

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Создание таблицы parcels
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parcels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT NOT NULL UNIQUE,
            contents TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            shipping_date TEXT NOT NULL,
            arrival_date TEXT NOT NULL,
            weight REAL NOT NULL,
            cargo_cost REAL NOT NULL,
            delivery_cost REAL NOT NULL,
            profit REAL NOT NULL,
            current_stage TEXT DEFAULT 'Принята на складе',
            status TEXT DEFAULT 'active', 
            client_contact TEXT NOT NULL,
            delivery_type TEXT NOT NULL
        )
    ''')
    
    # Создание таблицы parcel_stages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parcel_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parcel_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(parcel_id) REFERENCES parcels(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:  # Используйте `in` для проверки наличия user_id в списке ADMIN_IDS
        keyboard = [
            ["Добавить посылку", "Просмотреть посылку"],
            ["Редактировать посылку", "Удалить посылку"],
            ["📦 Текущие посылки", "🗄️ Архив"],
            ["🛃 Обновить этап", "📮 Отследить посылку"]
        ]
    else:
        keyboard = [
            ["📮 Отследить посылку","📦 Рассчитать стоимость"],
            ["🚀 Оформить заказ"]      
        ]
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        await main_menu(update, context)
        return ConversationHandler.END
    await main_menu(update, context)  # Показываем меню администратору
    await update.message.reply_text("Введите номер отслеживания посылки:")
    return ENTER_TRACKING_NUMBER

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
#     if update.effective_user.id != ADMIN_ID:
#         await main_menu(update, context)
#         return ConversationHandler.END
#     await update.message.reply_text("Введите номер отслеживания посылки:")
#     return ENTER_TRACKING_NUMBER

# Переименованная функция для клиентского ввода содержимого
async def client_enter_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['contents'] = update.message.text
    await update.message.reply_text(f"Содержимое посылки сохранено: {context.user_data['contents']}\n"
                                   "Откуда отправляется посылка?")
    return ENTER_CLIENT_ORIGIN  # Возвращаем следующее состояние

async def start_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Что хотите заказать?\n"
        "Если вам нужен выкуп товара с платформы, пришлите ссылку на товар с указанием конкретных характеристик.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_CONTENTS  # Переход к вводу содержимого

async def enter_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['contents'] = update.message.text
    await update.message.reply_text(f"Содержимое посылки сохранено: {context.user_data['contents']}\n"
                                   "Откуда отправляется посылка?")
    return ENTER_CLIENT_ORIGIN

async def enter_client_origin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['origin'] = update.message.text
    await update.message.reply_text("🏁 Введите город назначения:")
    return ENTER_CLIENT_DESTINATION

async def enter_client_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['destination'] = update.message.text
    await update.message.reply_text("⚖️ Введите вес посылки (кг):")
    return ENTER_CLIENT_WEIGHT


async def enter_client_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text)
        if weight <= 0:
            raise ValueError
        context.user_data['weight'] = weight
        
        keyboard = [["🚛 Стандартная (7 дней)", "✈️ Срочная (3 дня)"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "🚚 Выберите тип доставки:",
            reply_markup=reply_markup
        )
        return ENTER_PACKAGE_TYPE  # Возвращаем допустимое состояние
    except ValueError:
        await update.message.reply_text("❌ Некорректный вес! Введите число больше 0.")
        return ENTER_CLIENT_WEIGHT  # Возвращаем текущее состояние для повторного ввода

async def calculate_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delivery_type = update.message.text
    weight = context.user_data['weight']
    
    if "Стандартная" in delivery_type:
        base_cost = weight * delivery1
    elif "Срочная" in delivery_type:
        base_cost = weight * delivery2
    else:
        await update.message.reply_text("❌ Неверный тип доставки. Попробуйте снова.")
        return ENTER_PACKAGE_TYPE
    
    context.user_data['delivery_cost'] = base_cost
    context.user_data['delivery_type'] = delivery_type
    
    await update.message.reply_text(
        f"✅ Предварительный расчет:\n"
        f"• Откуда: {context.user_data['origin']}\n"
        f"• Куда: {context.user_data['destination']}\n"
        f"• Вес: {weight} кг\n"
        f"• Тип: {delivery_type}\n"
        f"💸 Стоимость: {base_cost} руб.\n\n"
        "Всё правильно?",
        reply_markup=ReplyKeyboardMarkup([["✅ Да", "❌ Нет"]], resize_keyboard=True)
    )
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Да":
        # Проверка наличия всех полей
        required_fields = ['contents', 'origin', 'destination', 'weight', 'delivery_cost', 'delivery_type']
        for field in required_fields:
            if field not in context.user_data:
                await update.message.reply_text(f"❌ Ошибка: отсутствует поле {field}.")
                return CONFIRM_ORDER
        
        # Генерация трек-номера
        tracking_number = f"TRACK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Сохранение в БД
        conn = get_db_connection()
        try:
            # В функции confirm_order замените INSERT-запрос на:
            conn.execute('''
                INSERT INTO parcels (
                    tracking_number, contents, origin, destination, weight, 
                    delivery_cost, status, current_stage, client_contact, delivery_type,
                    shipping_date, arrival_date, cargo_cost, profit
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'На модерации', ?, ?, ?, ?, ?, ?)
            ''', (
                tracking_number,
                context.user_data['contents'],
                context.user_data['origin'],
                context.user_data['destination'],
                context.user_data['weight'],
                context.user_data['delivery_cost'],
                "Контакт клиента",  # client_contact
                context.user_data.get('delivery_type', 'Стандартная'),  # delivery_type
                datetime.now().strftime('%Y-%m-%d'),  # shipping_date
                (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),  # arrival_date
                0.0,  # cargo_cost (значение по умолчанию)
                context.user_data['delivery_cost'] * 0.2  # profit (20% от delivery_cost)
            ))
            conn.commit()
            
            await update.message.reply_text(
                f"🎉 Заказ создан!\n"
                f"📦 Номер отслеживания: {tracking_number}\n"
                f"💸 Стоимость доставки: {context.user_data['delivery_cost']} руб.\n"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        finally:
            conn.close()
    else:
        context.user_data.clear()
        await update.message.reply_text("❌ Заказ отменен.")
    
    await main_menu(update, context)
    return ConversationHandler.END

async def update_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите номер отслеживания:")
    return MANAGE_STAGES

async def process_tracking_for_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tracking_number'] = update.message.text
    keyboard = [["Принята на складе", "В пути"], ["На таможне", "Доставлена"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выберите новый этап:", reply_markup=reply_markup)
    return ENTER_STAGE_UPDATE

async def save_stage_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_stage = update.message.text
    tracking_number = context.user_data['tracking_number']
    
    conn = get_db_connection()
    try:
        # Обновляем текущий этап
        parcel = conn.execute('SELECT id FROM parcels WHERE tracking_number = ?', (tracking_number,)).fetchone()
        conn.execute('''
            UPDATE parcels 
            SET current_stage = ? 
            WHERE tracking_number = ?
        ''', (new_stage, tracking_number))
        
        # Добавляем в историю
        conn.execute('''
            INSERT INTO parcel_stages (parcel_id, stage)
            VALUES (?, ?)
        ''', (parcel['id'], new_stage))
        
        conn.commit()
        await update.message.reply_text(f"✅ Этап обновлен: {new_stage}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()
    
    await main_menu(update, context)
    return ConversationHandler.END

# Обработка номера отслеживания
async def enter_tracking_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tracking_number = update.message.text.strip()
    
    # Проверка уникальности номера
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM parcels WHERE tracking_number = ?', (tracking_number,))
    if cursor.fetchone():
        await update.message.reply_text("❌ Этот номер уже используется! Введите другой:")
        conn.close()
        return ENTER_TRACKING_NUMBER
    conn.close()
    
    context.user_data['tracking_number'] = tracking_number
    await update.message.reply_text("Введите содержимое посылки:")
    return ENTER_CONTENTS

# Обработка содержимого посылки
async def enter_contents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['contents'] = update.message.text
    await update.message.reply_text(f"Содержимое посылки сохранено: {context.user_data['contents']}\n"
                                   "Откуда отправляется посылка?")
    return ENTER_ORIGIN

# Обработка места отправления
async def enter_origin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['origin'] = update.message.text
    await update.message.reply_text(f"Место отправления сохранено: {context.user_data['origin']}\n"
                                   "Куда отправляется посылка?")
    return ENTER_DESTINATION

# Обработка места назначения
async def enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['destination'] = update.message.text
    await update.message.reply_text(f"Место назначения сохранено: {context.user_data['destination']}\n"
                                   "Введите дату отправки (в формате ГГГГ-ММ-ДД):")
    return ENTER_SHIPPING_DATE

# Обработка даты отправки
async def enter_shipping_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date = update.message.text
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        await update.message.reply_text("❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД")
        return ENTER_SHIPPING_DATE
    context.user_data['shipping_date'] = date
    await update.message.reply_text(f"Дата отправки сохранена: {context.user_data['shipping_date']}\n"
                                   "Введите дату прибытия (в формате ГГГГ-ММ-ДД):")
    return ENTER_ARRIVAL_DATE

# Обработка даты прибытия
async def enter_arrival_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date = update.message.text
    if not re.match(r'\d{4}-\d{2}-\d{2}', date):
        await update.message.reply_text("❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД")
        return ENTER_ARRIVAL_DATE
    context.user_data['arrival_date'] = date
    await update.message.reply_text(f"Дата прибытия сохранена: {context.user_data['arrival_date']}\n"
                                   "Введите вес посылки (в кг):")
    return ENTER_WEIGHT

# Обработка веса посылки
async def enter_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        weight = float(update.message.text)
        context.user_data['weight'] = weight
        await update.message.reply_text(f"Вес посылки: {weight} кг\nВведите стоимость груза:")
        return ENTER_CARGO_COST
    except ValueError:
        await update.message.reply_text("❌ Введите число в формате 10.5")
        return ENTER_WEIGHT

# Обработка стоимости груза
async def enter_cargo_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        cargo_cost = float(update.message.text)
        context.user_data['cargo_cost'] = cargo_cost
        await update.message.reply_text(f"Стоимость груза: {cargo_cost} руб.\nВведите стоимость доставки:")
        return ENTER_DELIVERY_COST
    except ValueError:
        await update.message.reply_text("❌ Введите число в формате 1500.75")
        return ENTER_CARGO_COST

# Обработка стоимости доставки и расчет прибыли
async def enter_delivery_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        delivery_cost = float(update.message.text)
        profit = delivery_cost * 0.2
        context.user_data['delivery_cost'] = delivery_cost
        context.user_data['profit'] = profit

        # Сохранение посылки в базу данных
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO parcels (tracking_number, contents, origin, destination, shipping_date, arrival_date, weight, cargo_cost, delivery_cost, profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            context.user_data['tracking_number'],
            context.user_data['contents'],
            context.user_data['origin'],
            context.user_data['destination'],
            context.user_data['shipping_date'],
            context.user_data['arrival_date'],
            context.user_data['weight'],
            context.user_data['cargo_cost'],
            context.user_data['delivery_cost'],
            context.user_data['profit']
        ))
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"Посылка успешно добавлена!\n"
            f"Номер для отслеживания: {context.user_data['tracking_number']}\n"
            f"Прибыль: {profit} руб."
        )
        await main_menu(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Введите число в формате 1500.75")
        return ENTER_DELIVERY_COST

# Просмотр информации о посылке
async def view_parcel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите номер отслеживания посылки:")
    return ENTER_TRACKING_NUMBER

# Обработка номера отслеживания и вывод информации о посылке
async def enter_tracking_number_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tracking_number = update.message.text

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM parcels WHERE tracking_number = ?', (tracking_number,))
    parcel = cursor.fetchone()
    conn.close()

    if parcel:
        await update.message.reply_text(
            f"Информация о посылке:\n"
            f"Номер: {parcel['tracking_number']}\n"
            f"Содержимое: {parcel['contents']}\n"
            f"Откуда: {parcel['origin']}\n"
            f"Куда: {parcel['destination']}\n"
            f"Дата отправки: {parcel['shipping_date']}\n"
            f"Дата прибытия: {parcel['arrival_date']}\n"
            f"Вес: {parcel['weight']} кг\n"
            f"Стоимость груза: {parcel['cargo_cost']} руб.\n"
            f"Стоимость доставки: {parcel['delivery_cost']} руб.\n"
            f"Прибыль: {parcel['profit']} руб."
        )
    else:
        await update.message.reply_text("Посылка с таким номером не найдена.")

    await main_menu(update, context)
    return ConversationHandler.END

# Редактирование посылки
async def edit_parcel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📦 Введите номер отслеживания посылки:",
        reply_markup=ReplyKeyboardRemove()
    )
    return EDIT_PARCEL_CHOICE

# Обработка номера посылки
async def edit_parcel_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tracking_number = update.message.text.strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM parcels WHERE tracking_number = ?', (tracking_number,))
    parcel = cursor.fetchone()
    conn.close()

    if not parcel:
        await update.message.reply_text("❌ Посылка не найдена!")
        await main_menu(update, context)
        return ConversationHandler.END

    context.user_data['tracking_number'] = tracking_number
    
    keyboard = [
        ["Содержимое", "Откуда", "Вес"],
        ["Куда", "Дата отправки", "Стоимость груза"],
        ["Дата прибытия", "Стоимость доставки", "Отмена"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "✏️ Выберите поле для редактирования:",
        reply_markup=reply_markup
    )
    return EDIT_PARCEL_FIELD

# Обработка выбора поля
async def edit_parcel_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    fields = {
        "Содержимое": "contents",
        "Откуда": "origin",
        "Куда": "destination",
        "Дата отправки": "shipping_date",
        "Дата прибытия": "arrival_date",
        "Вес": "weight",
        "Стоимость груза": "cargo_cost",
        "Стоимость доставки": "delivery_cost"
    }

    if choice == "Отмена":
        await main_menu(update, context)
        return ConversationHandler.END

    if choice not in fields:
        await update.message.reply_text("⚠️ Неверный выбор! Попробуйте снова:")
        return EDIT_PARCEL_FIELD

    context.user_data['edit_field'] = fields[choice]
    await update.message.reply_text(
        f"✍️ Введите новое значение для '{choice}':",
        reply_markup=ReplyKeyboardRemove()
    )
    return ENTER_ARRIVAL_DATE  # Состояние для ввода значения

# Обработка нового значения
async def edit_parcel_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_value = update.message.text.strip()
    tracking_number = context.user_data.get('tracking_number')
    field = context.user_data.get('edit_field')

    if not all([tracking_number, field]):
        await update.message.reply_text("❌ Сессия устарела! Начните заново.")
        await main_menu(update, context)
        return ConversationHandler.END

    # Валидация числовых полей
    if field in ['weight', 'cargo_cost', 'delivery_cost']:
        try:
            new_value = float(new_value)
        except ValueError:
            await update.message.reply_text("❌ Введите число!")
            return

    # Если редактируется стоимость доставки, пересчитываем прибыль
    if field == 'delivery_cost':
        profit = new_value * 0.2
        conn = get_db_connection()
        try:
            conn.execute(f"UPDATE parcels SET {field} = ?, profit = ? WHERE tracking_number = ?", 
                        (new_value, profit, tracking_number))
            conn.commit()
            await update.message.reply_text(f"✅ Данные успешно обновлены! Новая прибыль: {profit} руб.")
        except sqlite3.Error as e:
            await update.message.reply_text(f"❌ Ошибка базы данных: {str(e)}")
        finally:
            conn.close()
    else:
        conn = get_db_connection()
        try:
            conn.execute(f"UPDATE parcels SET {field} = ? WHERE tracking_number = ?", 
                        (new_value, tracking_number))
            conn.commit()
            await update.message.reply_text("✅ Данные успешно обновлены!")
        except sqlite3.Error as e:
            await update.message.reply_text(f"❌ Ошибка базы данных: {str(e)}")
        finally:
            conn.close()

    # Очистка временных данных
    context.user_data.pop('tracking_number', None)
    context.user_data.pop('edit_field', None)
    
    await main_menu(update, context)
    return ConversationHandler.END

# Удаление посылки
async def delete_parcel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите номер отслеживания посылки, которую хотите удалить:")
    return DELETE_PARCEL

# Обработка удаления посылки
async def delete_parcel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tracking_number = update.message.text

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM parcels WHERE tracking_number = ?', (tracking_number,))
    conn.commit()
    conn.close()

    await update.message.reply_text("Посылка успешно удалена!")
    await main_menu(update, context)
    return ConversationHandler.END

# Команда /cancel для отмены текущего диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    await main_menu(update, context)
    return ConversationHandler.END

# Новые обработчики для этапов
async def track_parcel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите номер отслеживания для просмотра статуса:")
    return ENTER_TRACKING_NUMBER

async def show_parcel_stages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tracking_number = update.message.text
    conn = get_db_connection()
    
    # Получаем посылку и её этапы
    parcel = conn.execute('SELECT * FROM parcels WHERE tracking_number = ?', (tracking_number,)).fetchone()
    if not parcel:
        await update.message.reply_text("Посылка не найдена.")
        conn.close()
        return ConversationHandler.END
    
    stages = conn.execute('''
        SELECT stage, timestamp 
        FROM parcel_stages 
        WHERE parcel_id = ? 
        ORDER BY timestamp DESC
    ''', (parcel['id'],)).fetchall()
    
    response = [
        f"📦 Посылка {tracking_number}",
        f"Текущий статус: {parcel['current_stage']}",
        "\nИстория перемещений:"
    ]
    
    for idx, stage in enumerate(stages, 1):
        response.append(f"{idx}. {stage['stage']} - {stage['timestamp']}")
    
    await update.message.reply_text("\n".join(response))
    conn.close()
    await main_menu(update, context)
    return ConversationHandler.END

# Для админов: обновление этапа
async def update_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите номер отслеживания:")
    return MANAGE_STAGES

async def process_tracking_for_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tracking_number'] = update.message.text
    keyboard = [["Принята на складе", "В пути"], ["На таможне", "Доставлена"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выберите новый этап:", reply_markup=reply_markup)
    return ENTER_STAGE_UPDATE

async def save_stage_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_stage = update.message.text
    tracking_number = context.user_data['tracking_number']
    
    conn = get_db_connection()
    try:
        # Обновляем текущий этап
        parcel = conn.execute('SELECT id FROM parcels WHERE tracking_number = ?', (tracking_number,)).fetchone()
        conn.execute('''
            UPDATE parcels 
            SET current_stage = ? 
            WHERE tracking_number = ?
        ''', (new_stage, tracking_number))
        
        # Добавляем в историю
        conn.execute('''
            INSERT INTO parcel_stages (parcel_id, stage)
            VALUES (?, ?)
        ''', (parcel['id'], new_stage))
        
        conn.commit()
        await update.message.reply_text(f"✅ Этап обновлен: {new_stage}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()
    
    await main_menu(update, context)
    return ConversationHandler.END

async def show_active_parcels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM parcels WHERE status = "active"')
    parcels = cursor.fetchall()
    
    if not parcels:
        await update.message.reply_text("Нет активных посылок.")
        return
    
    response = ["Активные посылки:\n"]
    for parcel in parcels:
        response.append(
            f"📦 {parcel['tracking_number']} - {parcel['current_stage']}\n"
            f"От: {parcel['origin']} ➔ К: {parcel['destination']}\n"
        )
    
    await update.message.reply_text("\n".join(response))
    conn.close()

async def show_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM parcels WHERE status = "archived"')
    parcels = cursor.fetchall()
    
    if not parcels:
        await update.message.reply_text("Архив пуст.")
        return
    
    response = ["Архив доставленных посылок:\n"]
    for parcel in parcels:
        response.append(
            f"📦 {parcel['tracking_number']}\n"
            f"Дата доставки: {parcel['arrival_date']}\n"
        )
    
    await update.message.reply_text("\n".join(response))
    conn.close()

# 4. Обновить обработчик сохранения этапа
async def save_stage_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_stage = update.message.text
    tracking_number = context.user_data['tracking_number']
    
    conn = get_db_connection()
    try:
        # Если этап "Доставлена" - помечаем как архив
        if new_stage == "Доставлена":
            conn.execute('''
                UPDATE parcels 
                SET current_stage = ?, status = 'archived'
                WHERE tracking_number = ?
            ''', (new_stage, tracking_number))
        else:
            conn.execute('''
                UPDATE parcels 
                SET current_stage = ?
                WHERE tracking_number = ?
            ''', (new_stage, tracking_number))
        
        # Добавляем в историю
        parcel = conn.execute('SELECT id FROM parcels WHERE tracking_number = ?', (tracking_number,)).fetchone()
        conn.execute('''
            INSERT INTO parcel_stages (parcel_id, stage)
            VALUES (?, ?)
        ''', (parcel['id'], new_stage))
        
        conn.commit()
        await update.message.reply_text(f"✅ Этап обновлен: {new_stage}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()
    
    await main_menu(update, context)
    return ConversationHandler.END

def main() -> None:
    # Инициализация базы данных
    init_db()

    # Создание Application и передача токена вашего бота
    application = ApplicationBuilder().token("7074000750:AAHDufsK-50S50rgQCCWkk7iXB20fbP9hBc").build()

    # Создание ConversationHandler для управления диалогом добавления посылки
    add_parcel_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Добавить посылку$") & filters.User(ADMIN_IDS), start)],  # Новая точка входа
        states={
            ENTER_TRACKING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tracking_number)],
            ENTER_CONTENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_contents)],
            ENTER_ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_origin)],
            ENTER_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_destination)],
            ENTER_SHIPPING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_shipping_date)],
            ENTER_ARRIVAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_arrival_date)],
            ENTER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_weight)],
            ENTER_CARGO_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_cargo_cost)],
            ENTER_DELIVERY_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_delivery_cost)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Создание ConversationHandler для управления диалогом просмотра посылки
    view_parcel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Просмотреть посылку$"), view_parcel)],
        states={
            ENTER_TRACKING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tracking_number_view)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Создание ConversationHandler для управления диалогом редактирования посылки
    edit_parcel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Редактировать посылку$"), edit_parcel)],
        states={
            EDIT_PARCEL_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_parcel_choice)],
            EDIT_PARCEL_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_parcel_field)],
            ENTER_ARRIVAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_parcel_value)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Создание ConversationHandler для управления диалогом удаления посылки
    delete_parcel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Удалить посылку$"), delete_parcel)],
        states={
            DELETE_PARCEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_parcel_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    client_order_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚀 Оформить заказ$"), start_calculation)],
        states={
            ENTER_CONTENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_enter_contents)],
            ENTER_CLIENT_ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_client_origin)],
            ENTER_CLIENT_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_client_destination)],
            ENTER_CLIENT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_client_weight)],
            ENTER_PACKAGE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, calculate_cost)],
            CONFIRM_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_order)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )



    # Новые ConversationHandler для этапов
    stage_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🛃 Обновить этап$"), update_stage)],
        states={
            MANAGE_STAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_tracking_for_stage)],
            ENTER_STAGE_UPDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_stage_update)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    track_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📮 Отследить посылку$"), track_parcel)],
        states={
            ENTER_TRACKING_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, show_parcel_stages)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрация всех ConversationHandler в диспетчере
    application.add_handler(add_parcel_conv_handler)
    application.add_handler(view_parcel_conv_handler)
    application.add_handler(edit_parcel_conv_handler)
    application.add_handler(delete_parcel_conv_handler)
    application.add_handler(stage_conv_handler)  # Новый обработчик
    application.add_handler(track_conv_handler)  # Новый обработчик
    application.add_handler(MessageHandler(filters.Regex("^📦 Текущие посылки$"), show_active_parcels))
    application.add_handler(MessageHandler(filters.Regex("^🗄️ Архив$"), show_archive))
    application.add_handler(client_order_conv_handler)

    # Команда /start для вызова главного меню
    application.add_handler(CommandHandler('start', start))

    # Команда /cancel для отмены любого диалога
    application.add_handler(CommandHandler('cancel', cancel))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()