
# TeleGPT
## streamed output and clearing chat history
https://github.com/atif5/telegpt/assets/29068387/468df330-b19b-4934-be0c-76767b233a4c




## setting context
https://github.com/atif5/telegpt/assets/29068387/68f10a56-1bb6-4ca0-956a-5d8ebb7b59cc



ChatGPT for telegram. A simple [bot](https://t.me/ChatGPTNewestBot) for interacting with openai's revolutionary technology ChatGPT through telegram.

## installation
```
git clone https://github.com/atif5/telegpt
cd telegpt
python3 -m pip install -r requirements.txt
```

## usage
in the credentials.py file, replace the `OPENAI_API_KEY` variable with yours. [(You can get it here)](https://platform.openai.com/account/api-keys)

You can also create your own telegram bot and change the `TOKEN` variable. After you manage your credentials, you can start the bot:

```python3 bot.py```

or

```py bot.py``` if you are on windows.

## features
☑ ability to change context

☑ streamed output

☑ keeping chat history

☑ ability to clear history

☐ inline queries

☐ group chat support


## notes
This bot can be used in group chats, however it is not specifically designed to be used in group chats. Every chat is unique to a user, not a chat. In the future I may implement a group chat mode though.

