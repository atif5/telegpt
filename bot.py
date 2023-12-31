
import openai
import telebot
from telebot import types
from credentials import TOKEN, OPENAI_API_KEY
import time
import logging
import requests
import random
import json
import os
import io


logging.basicConfig(format='%(asctime)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')

TMODEL = "gpt-3.5-turbo"
VMODEL = "whisper-1"
openai.api_key = OPENAI_API_KEY


START_TEXT =  \
\
    """Hello 👋 This is a bot developed by Burzum.
Start typing anything to start interacting with chatgpt.
You can also send your voice!
 
Here are the commands:

/stopchat - suspend the chat with chatgpt
/startchat - continue the chat with chatgpt
/clearhistory - clear chat history, for your user
/start - show this message
/help - show this message
/changemode - change the mode to streamed or static
/setcontext - set a context for chatgpt
/image - generate 512x512 image based on input, should be used like: /image some text

You can use this bot with inline queries as well.

The query must end with a single question mark.

the source code for this project is here:

https://github.com/atif5/telegpt

Enjoy!!!
"""


MARKDOWN_SPECIALS = ['_', '[', ']', '#'
                     '(', ')', '~', '>', '+', '-', '=', '{', '}', '.', '!']

DEFAULT_CONTEXT = "You are chatting with someone on the telegram platform."


class ChatGPTProxy:
    framework = openai

    def __init__(self, model, api_key):
        self.model = model
        self.api_key = api_key
        self.__class__.framework.api_key = self.api_key
        try:
            chats_file = open("chats.json", 'r')
            self.chats = json.load(chats_file)
            keys = list(self.chats.keys())
            # convert ids to integers
            for id_ in keys:
                chat = self.chats[id_]
                self.chats.pop(id_)
                self.chats[int(id_)] = chat

        except FileNotFoundError:
            logging.warning("No chats.json file found.")
            self.chats = {}

    @staticmethod
    def fetch_response(chat_completion):
        tokens_used = chat_completion.usage.total_tokens
        choices = chat_completion.choices
        f = choices[0]
        content = f.message.content
        return content, tokens_used

    @staticmethod
    def fetch_streamed(partial):
        choices = partial.choices
        f = choices[0]
        data = f.delta
        if data:
            content = data.content
        else:
            content = ''
        finished = f.finish_reason
        return content, finished

    def create_chat(self, id_):
        chunk = {"role": "system", "content": DEFAULT_CONTEXT}
        self.chats[id_] = {"static": True,
                           "settingcontext": False,
                           "suspended": False,
                           "chat": [chunk, ]}

    def change_context(self, id_, new_context):
        self.chats[id_]["chat"][0]["content"] = new_context

    def add_message(self, id_, message, assistant: bool):
        role = "assistant" if assistant else "user"
        chunk = {"role": role, "content": message}
        self.chats[id_]["chat"].append(chunk)

    def create_completion(self, text, id_, streamed=False):
        completion = self.__class__.framework.ChatCompletion.create(
            model=self.model, messages=self.chats[id_]["chat"], stream=streamed)
        return completion

    def proxy_single(self, query, context=DEFAULT_CONTEXT):
        completion = self.__class__.framework.ChatCompletion.create(
            model=self.model, messages=[{"role": "system", "content": context},
                                        {"role": "user", "content": query}])
        gptresponse, tokens_used = self.__class__.fetch_response(completion)
        return gptresponse, tokens_used

    def proxy_answer(self, text, id_):
        completion = self.create_completion(text, id_)
        gptresponse, tokens_used = self.__class__.fetch_response(completion)
        return gptresponse, tokens_used

    def proxy_streamed(self, text, id_):
        generator = self.create_completion(text, id_, streamed=True)
        done = False
        stream = str()
        while not done:
            partial = next(generator)
            content, finished = self.__class__.fetch_streamed(partial)
            stream += content
            yield content
            done = finished


class GPTbot(telebot.TeleBot):
    def __init__(self, token, parse_mode=None):
        super().__init__(token, parse_mode=parse_mode)
        self.func_handler = {
            self.handle_chat_status: ["stopchat", "startchat"],
            self.starter: ["start", "help"],
            self.clear_history: ["clearhistory", ],
            self.set_mode: ["changemode", ],
            self.ask_context: ["setcontext", ],
            self.generate_image: ["image", ],
            self.set_context: lambda m: self.chat_setting_context(m.from_user.id),
            self.dismiss: lambda m: self.chat_is_suspended(m.from_user.id),
            self.answer: lambda m: not self.chat_is_streamed(m.from_user.id) and not self.chat_setting_context(m.from_user.id),
            self.answer_dynamic: lambda m: self.chat_is_streamed(m.from_user.id) and not self.chat_setting_context(m.from_user.id),
            self.audio_answer: ["voice", ]
        }
        self.decorate()
        self.proxy = ChatGPTProxy(TMODEL, OPENAI_API_KEY)

    def new_user(self, user_id) -> bool:
        return not (user_id in self.proxy.chats)

    def chat_setting_context(self, id_):
        if self.new_user(id_):
            return None
        return self.proxy.chats[id_]["settingcontext"]

    def chat_is_suspended(self, id_):
        if self.new_user(id_):
            return False
        return self.proxy.chats[id_]["suspended"]

    def chat_is_streamed(self, id_):
        if self.new_user(id_):
            return None
        return not self.proxy.chats[id_]["static"]

    def change_mode(self, id_):
        new_mode = not self.proxy.chats[id_]["static"]
        self.proxy.chats[id_]["static"] = new_mode

    def update_chat_for_user(self, text, user_id):
        if self.new_user(user_id):
            logging.warning(
                f"a new user with the id: {user_id} has started chatting.")
            self.proxy.create_chat(user_id)
        self.proxy.add_message(user_id, text, assistant=False)

    @staticmethod
    def format_response(response):
        for s in MARKDOWN_SPECIALS:
            response = response.replace(s, '\\'+s)

        return response

    def handle_chat_status(self, message):
        if self.new_user(message.from_user.id):
            self.proxy.create_chat(message.from_user.id)
        if message.text == "/stopchat":
            self.proxy.chats[message.from_user.id]["suspended"] = True
            self.send_message(
                message.chat.id, f"⚠️~@{message.from_user.username} suspended the chat with ChatGPT\\.~⚠️", parse_mode="MarkdownV2")
        else:
            self.proxy.chats[message.from_user.id]["suspended"] = False
            self.send_message(
                message.chat.id, f"The chat with ChatGPT is now continued ✔️")

    def starter(self, message):
        self.send_message(message.chat.id, START_TEXT)

    def dismiss(self, message):
        self.reply_to(
            message, "~chat with ChatGPT is suspended for you right now\\.~ To continue\\: use the \\/startchat command", parse_mode="MarkdownV2")

    def answer(self, message):
        self.send_chat_action(message.chat.id, "typing")
        self.update_chat_for_user(message.text, message.from_user.id)
        self.send_message(
            message.chat.id, f'now generating text for: "{message.text}" Author: @{message.from_user.username}...')
        answer, tokens_used = self.proxy.proxy_answer(
            message.text, message.from_user.id)
        self.reply_to(message, answer +
                      f"\n\ntokens used: {tokens_used}", parse_mode=None)
        self.proxy.add_message(message.from_user.id, answer, assistant=True)

    def answer_dynamic(self, message):
        self.send_chat_action(message.chat.id, "typing")
        self.update_chat_for_user(message.text, message.from_user.id)
        content_gen = self.proxy.proxy_streamed(
            message.text, message.from_user.id)
        partial_content = str()
        while not partial_content:
            partial_content = next(content_gen)

        answer = partial_content
        dynamic = self.reply_to(message, answer)
        editing = True
        while editing:
            # trying not to abuse the telegram api...
            for _ in range(10):
                try:
                    partial_content = next(content_gen)
                    answer += partial_content
                except StopIteration:
                    self.edit_message_text(answer, message.chat.id, dynamic.id)
                    editing = False
                    break
                
            try:
                time.sleep(0.01)
                if editing:
                    self.edit_message_text(answer, message.chat.id, dynamic.id)
            except:
                logging.error("failed to edit message")
                time.sleep(40)
                continue
            # todo: clean this mess even more
        self.proxy.add_message(message.from_user.id, answer, assistant=True)

    def clear_history(self, message):
        if self.new_user(message.from_user.id):
            self.proxy.create_chat(message.from_user.id)
        if not self.proxy.chats[message.from_user.id]["chat"]:
            self.send_message(
                message.chat.id, f"@{message.from_user.username} already has no history!")
            return
        self.proxy.chats[message.from_user.id]["chat"].clear()
        self.send_message(
            message.chat.id, f"@{message.from_user.username}'s history has been cleared 🗑️")

    def set_mode(self, message):
        if self.new_user(message.from_user.id):
            self.proxy.create_chat(message.from_user.id)
        self.change_mode(message.from_user.id)
        mode = "static" if self.proxy.chats[message.from_user.id]["static"] else "streamed"
        self.send_message(message.chat.id, f"⚠️ Mode is now {mode} ⚠️")

    def ask_context(self, message):
        markup = telebot.types.ForceReply(selective=False)
        self.send_message(
            message.chat.id, "Input a context: ", reply_markup=markup)
        if self.new_user(message.from_user.id):
            self.proxy.create_chat(message.from_user.id)
        self.proxy.chats[message.from_user.id]["settingcontext"] = True

    def set_context(self, message):
        if self.new_user(message.from_user.id):
            self.proxy.create_chat(message.from_user.id)
        self.proxy.change_context(message.from_user.id, message.text)
        self.send_message(
            message.chat.id, f'⚠️ Context set to "{message.text}"! ⚠️')
        self.proxy.chats[message.from_user.id]["settingcontext"] = False

    def inline_answer(self, inline_query):
        logging.warning(f'inline query: "{inline_query.query}" was submitted')
        answer, tokens_used = self.proxy.proxy_single(
            inline_query.query, context="Answer this question shortly")
        final = f"Query: {inline_query.query}\n\nResponse: {answer}\n\nused tokens: {tokens_used}"
        r = types.InlineQueryResultArticle(
            '1', 'Query taken, click to see the response', types.InputTextMessageContent(final))
        self.answer_inline_query(inline_query.id, [r, ])

    def audio_answer(self, message):
        file = self.get_file(message.voice.file_id)
        downloaded_file = self.download_file(file.file_path)
        rname = f"{str(random.random())[2:]}.ogg"
        with open(rname, "wb") as new_file:
            new_file.write(downloaded_file)
        fileh = open(rname, "rb")
        self.reply_to(
            message, "Now attempting to transcribe this voice message...")
        transcript = self.proxy.framework.Audio.transcribe(VMODEL, fileh)
        text = transcript.text
        self.reply_to(
            message, f"this message was transcribed as {text}")
        answer, tokens_used = self.proxy.proxy_single(text)
        self.send_message(message.chat.id, answer)
        os.remove(rname)

    def generate_image(self, message):
        query = ' '.join(message.text.split(' ')[1:])
        logging.warning(
            f"prompted to generate image for {query}!")
        self.send_message(
            message.chat.id, f'now generating an image for the text: "{query}"...')
        response = self.proxy.framework.Image.create(
            prompt=query, n=1, size="512x512")
        imgurl = response.data[0].url  # always one data
        request = requests.get(imgurl)
        fileh = io.BytesIO(request.content)
        self.send_photo(message.chat.id, fileh)

    def decorate(self):
        for func in self.func_handler:
            rhandler = self.func_handler[func]
            if type(rhandler) is list:
                if "voice" in rhandler:
                    func = self.message_handler(content_types=rhandler)(func)
                    continue
                func = self.message_handler(commands=rhandler)(func)
            else:
                func = self.message_handler(func=rhandler)(func)
        self.inline_answer = self.inline_handler(
            func=lambda query: self.__class__.query_eliminator(query.query))(self.inline_answer)

    @staticmethod
    def query_eliminator(query_text: str):
        qm_count = query_text.count('?')
        if qm_count > 1:
            return False
        elif qm_count == 1:
            if query_text[-1]:
                return True


def main():
    bot = GPTbot(TOKEN, parse_mode=None)
    try:
        bot.infinity_polling()
    except:
        pass
    finally:
        dump = open("chats.json", "w+")
        json.dump(bot.proxy.chats, dump, indent=4)
        dump.close()
    # save the chats in json format


if __name__ == "__main__":
    main()