import os
import json
import telebot
from telebot.types import Message, InputFile
import requests
import logging
import datetime

# Cấu hình logging cho ứng dụng
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

with open("config.json", "r") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
LEAKCHECK_API_KEY = config["LEAKCHECK_API_KEY"]
bot = telebot.TeleBot(TELEGRAM_TOKEN)

logging.info("Bot started")

# Hàm gọi API leakcheck.io cho domain/email
def leakcheck_query(query):
    url = f"https://leakcheck.io/api/v2/query/{query}?type=domain"
    headers = {"X-API-Key": LEAKCHECK_API_KEY}
    logging.info(f"[LeakCheck Request] URL: {url} | Headers: {headers}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        logging.info(f"[LeakCheck Response] Status: {response.status_code} | Body: {response.text}")
        if response.status_code == 200:
            data = response.json()
            # Trả về danh sách email nếu có
            emails = set()
            for result in data.get("result", []):
                email = result.get("email")
                if email:
                    emails.add(email)
            return emails
        else:
            logging.error(f"Leakcheck API error: {response.status_code} {response.text}")
            return set()
    except Exception as e:
        logging.error(f"Exception when calling leakcheck: {e}")
        return set()

@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    user_id = message.from_user.id if message.from_user else "unknown"
    logging.info(f"User {user_id} started bot.")
    bot.reply_to(message, "Gửi file domains.txt để bắt đầu tra cứu email trên Leakcheck.io.")

@bot.message_handler(content_types=['document'])
def handle_document(message: Message):
    user_id = message.from_user.id if message.from_user else "unknown"

    if not message.document:
        logging.warning(f"User {user_id} sent message without document.")
        bot.reply_to(message, "Vui lòng gửi file .txt chứa danh sách domain hoặc email.")
        return
    if not message.document.file_name or not message.document.file_name.endswith('.txt'):
        logging.warning(f"User {user_id} sent file with invalid name: {message.document.file_name}")
        bot.reply_to(message, "Vui lòng gửi file .txt chứa danh sách domain hoặc email.")
        return
    file_info = bot.get_file(message.document.file_id)
    if not file_info.file_path:
        logging.error(f"Không thể lấy file từ Telegram cho user {user_id}")
        bot.reply_to(message, "Không thể lấy file từ Telegram. Vui lòng thử lại.")
        return
    file_path = f"/tmp/{message.document.file_name}"
    downloaded_file = bot.download_file(file_info.file_path)
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
        bot.reply_to(message, "Đã tải file thành công!")
    logging.info(f"User {user_id} uploaded file: {file_path}")
    # Đọc file và chia batch
    with open(file_path, "r", encoding="utf-8") as f:
        queries = [line.strip() for line in f if line.strip()]
    # Tạo tên file kết quả theo định dạng /leakcheck/basename_result_now.txt
    now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    base_name = os.path.splitext(message.document.file_name)[0]
    result_dir = "/leakcheck"
    if not os.path.exists(result_dir):
        os.makedirs(result_dir)
    result_file = f"{result_dir}/{base_name}_result_{now}.txt"
    written_emails = set()
    try:
        with open(result_file, "w", encoding="utf-8") as f_result:
            for idx, query in enumerate(queries, 1):
                emails = leakcheck_query(query)
                for email in emails:
                    if email not in written_emails:
                        f_result.write(email + "\n")
                        written_emails.add(email)
                if idx % 10 == 0:
                    bot.send_chat_action(message.chat.id, 'typing')
    finally:
        with open(result_file, "rb") as f:
            bot.send_document(message.chat.id, f, caption="Kết quả email tìm thấy!", reply_to_message_id=message.message_id)
        logging.info(f"Sent result file to user {user_id}")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.infinity_polling() 