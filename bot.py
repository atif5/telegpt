import openai
import telebot
from credentials import TOKEN, OPENAI_API_KEY
import time
import logging


logging.basicConfig(format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')

MODEL = "gpt-3.5-turbo"
openai.api_key = OPENAI_API_KEY


START_TEXT =  \
\
    """Hello 👋 This is a bot developed by Burzum.
Start typing anything to start interacting with chatgpt.
 
Here are the commands:

/stopchat - suspend the chat with chatgpt
/startchat - continue the chat with chatgpt
/clearhistory - clear chat history, for your user
/start - show this message
/help - show this message
/changemode - change the mode to streamed or static
/setcontext - set a context for chatgpt

the source code for this project is here:

https://github.com/atif5/telegpt

Enjoy!!!
"""


MARKDOWN_SPECIALS = ['_', '[', ']',
                     '(', ')', '~', '>', '+', '-', '=', '{', '}', '.', '!']


class ChatGPTProxy:
    framework = openai

    def __init__(self, model, api_key):
        self.context = "You are chatting with another on the telegram platform."
        self.api_key = api_key
        self.__class__.framework.api_key = self.api_key
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

    @staticmethod
    def fetch_streamed(partial):
        data = partial["choices"][0]["delta"]
        if data:
            content = partial["choices"][0]["delta"]["content"]
        else:
            content = ''
        finished = partial["choices"][0]["finish_reason"]
        return content, finished

    def set_context(self, id_):
        chunk = {"role": "system", "content": self.context}
        self.chats[id_] = [chunk, ]

    def change_context(self, id_, new_context):
        self.context = new_context
        if not self.chats[id_]:
            self.set_context(id_)
        chunk = {"role": "system", "content": new_context}
        self.chats[id_][0] = chunk

    def create_completion(self, text, id_, streamed=False):
        chunk = {"role": "user", "content": text}
        if id_ not in self.chats or (not self.chats[id_]):
            self.set_context(id_)
        self.chats[id_].append(chunk)
        completion = self.__class__.framework.ChatCompletion.create(
            model=MODEL, messages=self.chats[id_], stream=streamed)
        return completion

    def proxy_answer(self, text, id_):
        completion = self.create_completion(text, id_)
        gptresponse, tokens_used = self.__class__.fetch_response(completion)
        chunk = {"role": "assistant", "content": gptresponse}
        self.chats[id_].append(chunk)
        return gptresponse + f"\n\n used tokens: {tokens_used}"

    def proxy_streamed(self, generator, id_):
        done = False
        stream = str()
        while not done:
            partial = next(generator)
            content, finished = self.__class__.fetch_streamed(partial)
            stream += content
            yield content
            done = bool(finished)
        chunk = {"role": "assistant", "content": stream}
        self.chats[id_].append(chunk)


class GPTbot(telebot.TeleBot):
    def __init__(self, token, streamed=True, parse_mode=None):
        super().__init__(token, parse_mode=parse_mode)
        self.streamed = streamed
        self.func_handler = {
            self.handle_chat_status: ["stopchat", "startchat"],
            self.starter: ["start", "help"],
            self.clear_history: ["clearhistory", ],
            self.set_mode: ["changemode", ],
            self.ask_context: ["setcontext", ],
            self.set_context: lambda m: self.setting_context,
            self.dismiss: lambda m: self.chat_stopped,
            self.answer: lambda m: not self.streamed and not self.chat_stopped and not self.setting_context,
            self.answer_dynamic: lambda m: self.streamed and not self.chat_stopped and not self.setting_context,
        }
        self.decorate()
        self.proxy = ChatGPTProxy(MODEL, OPENAI_API_KEY)
        self.chat_stopped = False
        self.setting_context = False

    def change_mode(self):
        new_mode = not self.streamed
        self.streamed = new_mode

    @staticmethod
    def format_response(response):
        for s in MARKDOWN_SPECIALS:
            response = response.replace(s, '\\'+s)

        return response

    def handle_chat_status(self, message):
        if message.text == "/stopchat":
            self.chat_stopped = True
            self.send_message(
                message.chat.id, f"⚠️~@{message.from_user.username} suspended the chat with ChatGPT\\.~⚠️", parse_mode="MarkdownV2")
        else:
            self.send_message(
                message.chat.id, f"The chat with ChatGPT is now continued ✔️")
            self.chat_stopped = False

    def starter(self, message):
        self.send_message(message.chat.id, START_TEXT)

    def dismiss(self, message):
        self.reply_to(
            message, "~chat with ChatGPT is suspended right now\\.~ To continue\\: use the \\/startchat command", parse_mode="MarkdownV2")

    def answer(self, message):
        self.send_chat_action(message.chat.id, "typing")
        self.send_message(
            message.chat.id, f'now generating text for: "{message.text}" Author: @{message.from_user.username}...')
        answer = self.proxy.proxy_answer(
            message.text, message.from_user.id)
        answer = self.__class__.format_response(answer)
        self.reply_to(message, answer, parse_mode="MarkdownV2")

    def answer_dynamic(self, message):
        self.send_chat_action(message.chat.id, "typing")
        completion = self.proxy.create_completion(
            message.text, message.from_user.id, streamed=True)
        content_gen = self.proxy.proxy_streamed(
            completion, message.from_user.id)
        partial_content = str()
        while not partial_content:
            partial_content = next(content_gen)

        answer = partial_content
        dynamic = self.reply_to(message, answer)
        edit_count = 0
        while True:
            try:
                # trying not to abuse the telegram api...
                for _ in range(10):
                    partial_content = next(content_gen)
                    answer += partial_content
                try:
                    time.sleep(0.01)
                    self.edit_message_text(answer, message.chat.id, dynamic.id)
                except:
                    logging.error(f"failed to edit message")
                    time.sleep(40)
                    continue
                else:
                    edit_count += 1
            except StopIteration:
                self.edit_message_text(answer, message.chat.id, dynamic.id)
                return

    def clear_history(self, message):
        self.proxy.chats[message.from_user.id].clear()
        self.send_message(
            message.chat.id, f"@{message.from_user.username}'s history has been cleared 🗑️")

    def set_mode(self, message):
        self.change_mode()
        mode = "streamed" if self.streamed else "static"
        self.send_message(message.chat.id, f"⚠️ Mode is now {mode} ⚠️")

    def ask_context(self, message):
        markup = telebot.types.ForceReply(selective=False)
        self.send_message(
            message.chat.id, "Input a context: ", reply_markup=markup)
        self.setting_context = True

    def set_context(self, message):
        self.proxy.change_context(message.from_user.id, message.text)
        self.send_message(
            message.chat.id, f'⚠️ Context set to "{message.text}"! ⚠️')
        self.setting_context = False

    def decorate(self):
        for func in self.func_handler:
            rhandler = self.func_handler[func]
            if type(rhandler) is list:
                func = self.message_handler(commands=rhandler)(func)
            else:
                func = self.message_handler(func=rhandler)(func)


if __name__ == "__main__":
    bot = GPTbot(TOKEN, parse_mode=None, streamed=False)
    try:
        bot.infinity_polling()
    except:
        pass
    finally:
        dump = open("chats.py", "w+")
        dump.write("id_chats = " + str(bot.proxy.chats))
        dump.close()
