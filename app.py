import os
import re
import sys
import json
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape
from flask import make_response

# ============================================================
# НАСТРОЙКА ПУТЕЙ ДЛЯ РАБОТЫ В .EXE (СОБРАННОМ ПРИЛОЖЕНИИ)
# ============================================================
# sys.frozen == True означает, что программа запущена из .exe (PyInstaller)
if getattr(sys, 'frozen', False):
    # При запуске из .exe все файлы распаковываются во временную папку,
    # путь к которой хранится в sys._MEIPASS
    BASE_DIR = sys._MEIPASS
else:
    # При обычном запуске через python app.py — берём папку, где лежит этот файл
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ============================================================
# КОНФИГУРАЦИЯ ПРИЛОЖЕНИЯ
# ============================================================
app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'templates'),  # папка с HTML-шаблонами
            static_folder=os.path.join(BASE_DIR, 'static'))      # папка с картинками, CSS (иконка темы)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")   # сюда сохраняются работы студентов
app.config["CONTENT_FOLDER"] = os.path.join(BASE_DIR, "content")  # сюда складываем настройки сайта (title.txt, info.txt...)

# Создаём папки, если их ещё нет
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["CONTENT_FOLDER"], exist_ok=True)

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def get_title():
    """Читает заголовок страницы из файла content/title.txt"""
    path = os.path.join(app.config["CONTENT_FOLDER"], "title.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            title = f.read().strip()
            if title:
                return title
    return "Система сдачи работ"  # значение по умолчанию

def get_info():
    """Читает текст из content/info.txt (сырой, без форматирования)"""
    path = os.path.join(app.config["CONTENT_FOLDER"], "info.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def format_info(text):
    """Преобразует текст из info.txt в HTML:
       - экранирует опасные символы (защита от XSS)
       - превращает ссылки вида https://... в кликабельные <a>
       - заменяет переносы строк на <br>
    """
    if not text:
        return ""
    text = escape(text)                     # защита от XSS
    url_pattern = r'(https?://[^\s]+)'      # находим ссылки
    text = re.sub(url_pattern, r'<a href="\1" target="_blank">\1</a>', text)
    text = text.replace("\n", "<br>")       # переносы строк
    return Markup(text)                     # разрешаем вставку HTML в шаблон

def get_content_files():
    """Возвращает список файлов из папки content/files
       Эти файлы отображаются на сайте со ссылкой «Скачать» (инструкции, макеты)
    """
    folder = os.path.join(app.config["CONTENT_FOLDER"], "files")
    if not os.path.exists(folder):
        return []
    files = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            files.append({
                "name": filename,
                "icon": "📌",                      # иконка-эмодзи (📌/📎)
                "url": f"/content-file/{filename}" # ссылка для скачивания
            })
    return files

def get_select_title():
    """Читает текст для подписи выпадающего списка из content/select_title.txt"""
    path = os.path.join(app.config["CONTENT_FOLDER"], "select_title.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "Выберите тип работы"  # значение по умолчанию

def get_topics():
    """Возвращает список папок в UPLOAD_FOLDER — они становятся пунктами выпадающего списка
       Каждая папка = одна категория (тема) для сдачи работ.
    """
    topics = []
    for name in os.listdir(app.config["UPLOAD_FOLDER"]):
        full = os.path.join(app.config["UPLOAD_FOLDER"], name)
        if os.path.isdir(full):
            topics.append(name)
    return topics

def normalize_group(group):
    """Приводит группу к верхнему регистру и проверяет формат БУКВЫ-ЦИФРЫ-ЦИФРА.
       Например: "ИС-24-1" → "ИС-24-1" (остаётся), "ис-24-1" → "ИС-24-1"
       Если формат неверный, возвращает как есть (но в верхнем регистре).
    """
    group = group.strip().upper()
    pattern = r'^[А-ЯЁ]+-\d{2}-\d$'  # русские буквы, дефис, 2 цифры, дефис, 1 цифра
    if re.match(pattern, group):
        return group
    return group

def is_group_format(name):
    """Проверяет, похоже ли имя папки на группу (формат ИС-24-1, М-26-5, ОМД-25-2...).
       Такие папки в корне UPLOAD_FOLDER будут обрабатываться как группы:
       - в выпадающем списке они есть,
       - дополнительные поля (группа) не показываются,
       - файлы сохраняются прямо в эту папку (без вложенных подпапок).
    """
    return re.match(r'^[А-ЯЁ]+-\d{2}-\d$', name) is not None

# ============================================================
# ОСНОВНЫЕ МАРШРУТЫ (СТРАНИЦЫ)
# ============================================================

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Главная страница.
    GET  -> показываем форму
    POST -> обрабатываем отправленные файлы
    """
    if request.method == "POST":
        # --- Получаем данные из формы ---
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            full_name = "Неизвестный"

        selected_topic = request.form.get("topic_select")
        custom_topic = request.form.get("custom_topic")

        # --- Определяем, куда сохранять файлы ---
        if selected_topic == "Другое":
            # Тема "Другое": пользователь сам вводит название подтемы
            base_topic = "Другое"
            sub_topic = (custom_topic or "").strip()
            if not sub_topic:
                sub_topic = "Без_темы"
            sub_topic = secure_filename(sub_topic)[:50]  # убираем опасные символы
            # Папка: uploads/Другое/Название_подтемы/
            topic_folder = os.path.join(app.config["UPLOAD_FOLDER"], base_topic, sub_topic)
            effective_topic_name = sub_topic
            group = None
            participant_number = None

        else:
            base_topic = selected_topic
            # Папка: uploads/Выбранная_тема/
            topic_folder = os.path.join(app.config["UPLOAD_FOLDER"], base_topic)
            effective_topic_name = base_topic

            group = None
            participant_number = None

            # === ГЛАВНАЯ ЛОГИКА: определяем, какие поля показывать ===
            # Если тема сама похожа на группу (например, ИС-24-1) — только ФИО
            if is_group_format(base_topic):
                group = base_topic
                # Файлы сохраняются прямо в uploads/ИС-24-1/ (без вложенной группы)
                pass
            # Категории, которые требуют ввода группы
            elif base_topic in ("Экзамен", "Экзамен-Зачёт", "Экзамен-Зачет", 
                                "Зачёт-Экзамен", "Зачет-Экзамен", "Зачёт", "Зачет", "Практика"):
                group_raw = request.form.get("group", "").strip()
                if not group_raw:
                    group = "БЕЗ_ГРУППЫ"
                else:
                    group = normalize_group(group_raw)
                # Вкладываем папку группы: uploads/Экзамен/ИС-24-1/
                topic_folder = os.path.join(topic_folder, group)
            # Категория "Чемпионат" — требует номер участника
            elif base_topic == "Чемпионат":
                participant_number = request.form.get("participant_number", "").strip()
                if not participant_number:
                    participant_number = "0"
                # Создаём подпапку с номером участника
                topic_folder = os.path.join(topic_folder, f"Участник_{participant_number}")

        # Создаём папку (если её нет)
        os.makedirs(topic_folder, exist_ok=True)

        # --- Сохраняем файлы ---
        files = request.files.getlist("files")
        for file in files:
            if file.filename:
                # Безопасное имя файла (убираем ../ и т.п.)
                original_filename = secure_filename(file.filename)
                name_without_ext, extension = os.path.splitext(original_filename)

                # ФИО без пробелов (для имени файла)
                safe_name = full_name.replace(" ", "_")

                # Формируем префикс: группа или номер участника или тема "Другое"
                prefix = ""
                if group:
                    prefix = group + "_"
                elif participant_number:
                    prefix = f"Участник_{participant_number}_"
                if selected_topic == "Другое":
                    prefix = effective_topic_name + "_"

                # Добавляем дату-время, чтобы имена не пересекались
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                final_filename = f"{prefix}{safe_name}_{name_without_ext}_{timestamp}{extension}"
                save_path = os.path.join(topic_folder, final_filename)
                file.save(save_path)

        # После успешной отправки показываем ту же страницу с флагом success=True
        return render_template("index.html",
                               success=True,
                               title=get_title(),
                               info=format_info(get_info()),
                               content_files=get_content_files(),
                               select_title=get_select_title(),
                               topics=get_topics())

    # GET-запрос: просто показываем форму
    return render_template("index.html",
                           title=get_title(),
                           info=format_info(get_info()),
                           content_files=get_content_files(),
                           select_title=get_select_title(),
                           topics=get_topics())

# ============================================================
# ЗАГОЛОВКИ ДЛЯ ОТКЛЮЧЕНИЯ КЕШИРОВАНИЯ
# ============================================================
@app.after_request
def add_cache_headers(response):
    """Отключает кеширование в браузере, чтобы обновления сразу отображались."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# ============================================================
# МАРШРУТЫ ДЛЯ СКАЧИВАНИЯ ФАЙЛОВ
# ============================================================

@app.route("/download/<topic>/<filename>")
def download_file(topic, filename):
    """Скачивание загруженных студентами файлов (доступно всем, но ссылки только в админке)"""
    safe_topic = secure_filename(topic)
    safe_filename = secure_filename(filename)
    folder = os.path.join(app.config["UPLOAD_FOLDER"], safe_topic)
    return send_from_directory(folder, safe_filename, as_attachment=True)

@app.route("/content-file/<filename>")
def content_file(filename):
    """Скачивание файлов из папки content/files (инструкции, дополнительные материалы)"""
    folder = os.path.join(app.config["CONTENT_FOLDER"], "files")
    return send_from_directory(folder, filename, as_attachment=True)

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    # Ограничение на размер файлов не установлено (можно добавить при необходимости)
    # app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Раскомментировать для ограничения 100 МБ
    # host='0.0.0.0' — делает сервер доступным в локальной сети
    # port=5000 — стандартный порт
    # debug=True — автоматический перезапуск при изменении кода
    port = 5000
    # Проверяем, передан ли порт через командную строку
    if len(sys.argv) > 1 and sys.argv[1].startswith('--port='):
        try:
            port = int(sys.argv[1].split('=')[1])
        except:
            pass
    app.run(host='0.0.0.0', port=port, debug=True)