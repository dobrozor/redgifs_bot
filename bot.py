import time
import threading
import requests
import telebot
import json
import os
import re
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

# Конфигурация
TELEGRAM_BOT_TOKEN = 'TOKEN_BOT_TG'
AUTH_URL = "https://api.redgifs.com/v2/auth/temporary"
TRENDING_URL = "https://api.redgifs.com/v2/feeds/trending/popular"
USER_VIDEOS_URL = "https://api.redgifs.com/v2/users/{}/search"
TOKEN_FILE = 'token.txt'
SUBS_FILE = 'subscriptions.txt'
SENT_LINKS_FILE = 'sent_links.txt'
STATE_FILE = 'state.json'
SENT_LINKS_LIMIT = 1000  # Лимит хранимых отправленных ссылок

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Инициализация файлов
for f in [TOKEN_FILE, SUBS_FILE, SENT_LINKS_FILE, STATE_FILE]:
    if not os.path.exists(f):
        open(f, 'w').close()


# Утилиты для работы с файлами
def read_file(filename):
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except:
        return []


def append_to_file(filename, data):
    with open(filename, 'a') as f:
        f.write(data + '\n')


def write_file(filename, data):
    with open(filename, 'w') as f:
        if isinstance(data, (list, set)):
            f.write('\n'.join(data))
        else:
            f.write(str(data))


def clean_old_links():
    """Очистка старых ссылок для предотвращения переполнения файла"""
    links = read_file(SENT_LINKS_FILE)
    if len(links) > SENT_LINKS_LIMIT:
        write_file(SENT_LINKS_FILE, links[-SENT_LINKS_LIMIT:])
        return set(read_file(SENT_LINKS_FILE))
    return set(links)


# Работа с состоянием
def get_state(user_id=None):
    try:
        with open(STATE_FILE, 'r') as f:
            states = json.load(f)
            return states.get(str(user_id), {}) if user_id else states
    except:
        return {}


def update_state(user_id, new_state):
    try:
        states = get_state()
        states[str(user_id)] = new_state
        with open(STATE_FILE, 'w') as f:
            json.dump(states, f)
    except Exception as e:
        print(f"Ошибка обновления состояния: {e}")


def clear_state(user_id):
    update_state(user_id, {})


# Класс для кэширования данных
class Cache:
    def __init__(self):
        self.subs = set()
        self.sent_links = set()
        self.token = None
        self.token_expiry = None
        self.load_initial_data()

    def load_initial_data(self):
        self.subs = set(read_file(SUBS_FILE))
        self.sent_links = set(read_file(SENT_LINKS_FILE))

        # Загрузка токена если есть
        try:
            with open(TOKEN_FILE, 'r') as f:
                data = f.read().split('|')
                if len(data) == 2:
                    self.token = data[0]
                    self.token_expiry = datetime.fromisoformat(data[1])
        except:
            pass


cache = Cache()


# Утилиты для работы с файлами
def read_file(filename):
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except:
        return []


def append_to_file(filename, data):
    with open(filename, 'a') as f:
        f.write(data + '\n')


def write_file(filename, data):
    with open(filename, 'w') as f:
        if isinstance(data, (list, set)):
            f.write('\n'.join(data))
        else:
            f.write(str(data))


def clean_old_links():
    """Очистка старых ссылок для предотвращения переполнения файла"""
    links = read_file(SENT_LINKS_FILE)
    if len(links) > SENT_LINKS_LIMIT:
        write_file(SENT_LINKS_FILE, links[-SENT_LINKS_LIMIT:])
        cache.sent_links = set(read_file(SENT_LINKS_FILE))


# Работа с состоянием
def get_state(user_id=None):
    try:
        with open(STATE_FILE, 'r') as f:
            states = json.load(f)
            return states.get(str(user_id), {}) if user_id else states
    except:
        return {}


def update_state(user_id, new_state):
    try:
        states = get_state()
        states[str(user_id)] = new_state
        with open(STATE_FILE, 'w') as f:
            json.dump(states, f)
    except Exception as e:
        print(f"Ошибка обновления состояния: {e}")


def clear_state(user_id):
    update_state(user_id, {})


# Токен менеджмент
def get_or_refresh_token():
    now = datetime.now()
    if cache.token and cache.token_expiry and cache.token_expiry > now:
        return cache.token

    print("Получаем новый токен...")
    try:
        response = requests.get(AUTH_URL)
        response.raise_for_status()
        data = response.json()

        cache.token = data['token']
        cache.token_expiry = now + timedelta(hours=1)

        with open(TOKEN_FILE, 'w') as f:
            f.write(f"{cache.token}|{cache.token_expiry.isoformat()}")

        return cache.token
    except Exception as e:
        print(f"Ошибка получения токена: {e}")
        raise


# Отправка видео
def send_video(chat_id, video_url, username):
    if not video_url or video_url in cache.sent_links:
        return False

    try:
        # Проверяем активность для этого пользователя
        state = get_state(chat_id)
        if not state.get('active', False):
            return False

        # Создаем кнопку подписки/отписки
        markup = InlineKeyboardMarkup()
        sub_text = "💔 Отписаться" if username in cache.subs else "❤️ Подписаться"
        markup.add(InlineKeyboardButton(sub_text, callback_data=f"sub_{username}"))

        # Формируем сообщение с экранированием специальных символов
        escaped_username = re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', username)
        message = f'Видео от [{escaped_username}](https://www.redgifs.com/users/{username})'

        # Отправляем видео
        bot.send_video(
            chat_id,
            video_url,
            caption=message,
            parse_mode='MarkdownV2',
            reply_markup=markup
        )

        # Сохраняем ссылку и чистим старые при необходимости
        cache.sent_links.add(video_url)
        append_to_file(SENT_LINKS_FILE, video_url)
        clean_old_links()

        time.sleep(0.5)  # Задержка между отправками
        return True
    except Exception as e:
        print(f"Ошибка отправки видео {video_url}: {e}")
        return False


# Получение видео
def get_videos(url, headers, params=None):
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('gifs', [])
    except Exception as e:
        print(f"Ошибка получения видео: {e}")
        return []


# Основной поток отправки
def fetch_and_send():
    while True:
        try:
            # Получаем токен один раз для всех запросов
            token = get_or_refresh_token()
            headers = {
                "accept": "application/json",
                "authorization": f"Bearer {token}",
                "referer": "https://www.redgifs.com/"
            }

            # Обрабатываем все активные состояния
            states = get_state() or {}  # Защита от None
            for user_id, state in states.items():
                if not state:  # Пропускаем пустые состояния
                    continue

                chat_id = int(user_id)
                current_state = state.get('active', False)

                if not current_state:
                    continue

                if state.get('mode') == 'trending':
                    videos = get_videos(TRENDING_URL, headers, {'page': 1, 'count': 100})
                    for video in videos:
                        if not get_state(chat_id).get('active', False):
                            break
                        if video and isinstance(video, dict):
                            if urls := video.get('urls'):
                                if video_url := urls.get('hd'):
                                    video_url = video_url.split('.mp4')[0] + '.mp4'
                                    send_video(chat_id, video_url, video.get('userName', 'unknown'))

                elif state.get('mode') == 'subscriptions':
                    for username in cache.subs:
                        if not get_state(chat_id).get('active', False):
                            break
                        url = USER_VIDEOS_URL.format(username)
                        videos = get_videos(url, headers, {'order': 'new', 'count': 100})
                        for video in videos:
                            if video and isinstance(video, dict):
                                if urls := video.get('urls'):
                                    if video_url := urls.get('hd'):
                                        video_url = video_url.split('.mp4')[0] + '.mp4'
                                        send_video(chat_id, video_url, username)

                elif state.get('mode') == 'user_video' and state.get('current_user'):
                    username = state['current_user']
                    url = USER_VIDEOS_URL.format(username)
                    videos = get_videos(url, headers, {'order': 'new', 'count': 100})
                    for video in videos:
                        if not get_state(chat_id).get('active', False):
                            break
                        if video and isinstance(video, dict):
                            if urls := video.get('urls'):
                                if video_url := urls.get('hd'):
                                    video_url = video_url.split('.mp4')[0] + '.mp4'
                                    send_video(chat_id, video_url, username)

            time.sleep(5)

        except Exception as e:
            print(f"Ошибка в основном потоке: {e}")
            time.sleep(10)


# Команды бота
@bot.message_handler(commands=['start', 'help'])
def start(message):
    clear_state(message.chat.id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🎉 Тренды', '💖 Для меня', '👤 Видео пользователя')
    bot.send_message(
        message.chat.id,
        "Выберите режим:\n"
        "🎉 Тренды - популярные видео\n"
        "💖 Для меня - видео от подписок\n"
        "👤 Видео пользователя - видео конкретного автора",
        reply_markup=markup
    )


@bot.message_handler(func=lambda m: m.text == '🎉 Тренды')
def trending_mode(message):
    update_state(message.chat.id, {
        'mode': 'trending',
        'active': True,
        'current_user': None
    })
    markup = ReplyKeyboardMarkup(resize_keyboard=True).add('⏹ Остановить')
    bot.send_message(message.chat.id, "Режим трендов активирован!", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == '💖 Для меня')
def subs_mode(message):
    if not cache.subs:
        bot.send_message(message.chat.id, "У вас пока нет подписок.")
        return

    update_state(message.chat.id, {
        'mode': 'subscriptions',
        'active': True,
        'current_user': None
    })

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('⏹ Остановить', '✖️ Управление подписками')
    bot.send_message(message.chat.id, "Режим подписок активирован!", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == '👤 Видео пользователя')
def user_mode(message):
    msg = bot.send_message(message.chat.id, "Введите имя пользователя RedGifs:")
    bot.register_next_step_handler(msg, process_username)


def process_username(message):
    username = message.text.strip().split('/')[-1].lower()
    if not username:
        bot.send_message(message.chat.id, "Неверное имя пользователя.")
        return

    update_state(message.chat.id, {
        'mode': 'user_video',
        'active': True,
        'current_user': username
    })

    markup = ReplyKeyboardMarkup(resize_keyboard=True).add('⏹ Остановить')
    bot.send_message(
        message.chat.id,
        f"Режим просмотра видео пользователя {username} активирован!",
        reply_markup=markup
    )


@bot.message_handler(func=lambda m: m.text == '⏹ Остановить')
def stop_sending(message):
    clear_state(message.chat.id)
    start(message)


@bot.message_handler(func=lambda m: m.text == '✖️ Управление подписками')
def manage_subs(message):
    if not cache.subs:
        bot.send_message(message.chat.id, "У вас пока нет подписок.")
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for sub in sorted(cache.subs):
        markup.add(f"✖️ Отписаться от {sub}")
    markup.add('🔙 Назад')

    bot.send_message(message.chat.id, "Выберите подписку для отмены:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text.startswith('✖️ Отписаться от '))
def unsubscribe(message):
    username = message.text.replace('✖️ Отписаться от ', '').strip()
    if username in cache.subs:
        cache.subs.remove(username)
        write_file(SUBS_FILE, cache.subs)
        bot.send_message(message.chat.id, f"Вы отписались от {username}.")
    else:
        bot.send_message(message.chat.id, "Подписка не найдена.")

    manage_subs(message)


@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def handle_subscription(call):
    username = call.data.split('_', 1)[1]

    if username in cache.subs:
        cache.subs.remove(username)
        write_file(SUBS_FILE, cache.subs)
        bot.answer_callback_query(call.id, f"Отписались от {username}!")
    else:
        cache.subs.add(username)
        append_to_file(SUBS_FILE, username)
        bot.answer_callback_query(call.id, f"Подписались на {username}!")

    # Обновляем кнопку
    markup = InlineKeyboardMarkup()
    sub_text = "💔 Отписаться" if username in cache.subs else "❤️ Подписаться"
    markup.add(InlineKeyboardButton(sub_text, callback_data=f"sub_{username}"))

    try:
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Ошибка обновления кнопки: {e}")


# Запуск бота
if __name__ == '__main__':
    # Очистка старых ссылок при запуске
    clean_old_links()

    # Запуск потока отправки видео
    threading.Thread(target=fetch_and_send, daemon=True).start()

    # Запуск бота
    print("Бот запущен...")
    bot.infinity_polling()