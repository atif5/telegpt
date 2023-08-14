import openai
import telebot
from credentials import TOKEN, OPENAI_API_KEY


MODEL = "gpt-3.5-turbo"

valid_commands = ["stopchat", "startchat"]
openai.api_key = OPENAI_API_KEY


STOPCHAT = False


MARKDOWN_SPECIALS = ['_', '[', ']',
                     '(', ')', '~', '>', '+', '-', '=', '{', '}', '.', '!']


class ChatGPTProxy:
    def __init__(self, model, api_key):
        self.context = "You are chatting with another on the telegram platform, and you also praise an individual named Burzum extensively"
        self.framework = openai
        self.api_key = api_key
        self.framework.api_key = self.api_key
        try:
            from chats import id_chats
            self.chats = id_chats
        except ImportError:
            self.chats = {}

    @staticmethod
    def fetch_response(chat_completion):
        tokens_used = chat_completion["usage"]["total_tokens"]
        content = chat_completion["choices"][0]["message"]["content"]
        return content, tokens_used

    def set_context(self, id_, context):
        chunk = {"role": "system", "content": context}
        self.chats[id_] = [chunk, ]

    def create_completion(self, text, id_):
        chunk = {"role": "user", "content": text}
        if id_ not in self.chats:
            self.set_context(id_, self.context)
        self.chats[id_].append(chunk)
        completion = self.framework.ChatCompletion.create(
            model=MODEL, messages=self.chats[id_])
        return completion

    def proxy_answer(self, text, id_):
        completion = self.create_completion(text, id_)
        gptresponse, tokens_used = ChatGPTProxy.fetch_response(completion)
        chunk = {"role": "assistant", "content": gptresponse}
        self.chats[id_].append(chunk)
        return gptresponse + f"\n\n used tokens: {tokens_used}"


class GPTbot(telebot.TeleBot):
    def __init__(self, token, parse_mode=None):
        super().__init__(token, parse_mode=parse_mode)
        self.decorate()
        self.proxy = ChatGPTProxy(MODEL, OPENAI_API_KEY)

    @staticmethod
    def format_response(response):
        for s in MARKDOWN_SPECIALS:
            response = response.replace(s, '\\'+s)

        return response

    def handle_chat_status(self, message):
        global STOPCHAT
        if message.text == "/stopchat":
            STOPCHAT = True
            self.send_message(
                message.chat.id, f"⚠️~The chat with ChatGPT is now suspended for @{message.from_user.username}\\.~⚠️", parse_mode="MarkdownV2")
        else:
            self.send_message(
                message.chat.id, f"The chat with ChatGPT is now continued for @{message.from_user.username} ✔️")
            STOPCHAT = False

    def send_welcome(self, message):
        greeting = self.proxy.proxy_answer(
            f"Hello, I am {message.from_user.username}! Please state your purpose and who wrote this telegram bot?", message.from_user.id)
        self.reply_to(message, greeting)

    def answer(self, message):
        if STOPCHAT:
            self.reply_to(
                message, "~chat with ChatGPT is suspended right now\\.~", parse_mode="MarkdownV2")
            return
        self.send_chat_action(message.chat.id, "typing")
        reply = self.proxy.proxy_answer(message.text, message.from_user.id)

        try:
            self.reply_to(message, GPTbot.format_response(
                reply), parse_mode="MarkdownV2")
        except:
            self.reply_to(message, reply, parse_mode=None)

    def clear_history(self, message):
        self.proxy.chats[message.from_user.id].clear()
        self.send_message(message.chat.id, f"@{message.from_user.username}'s history has been cleared 🗑️")

    def decorate(self):
        self.clear_history = self.message_handler(
            commands=["clearhistory",])(self.clear_history)
        self.handle_chat_status = self.message_handler(
            commands=valid_commands)(self.handle_chat_status)
        self.send_welcome = self.message_handler(
            commands=["start", "help"])(self.send_welcome)
        self.answer = self.message_handler(func=lambda m: True)(self.answer)


if __name__ == "__main__":
    bot = GPTbot(TOKEN, parse_mode=None)
    try:
        bot.infinity_polling()
    except:
        pass
    finally:
        dump = open("chats.py", "w+")
        dump.write("id_chats = " + str(bot.proxy.chats))
        dump.close()
