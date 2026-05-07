from dashscope import Generation
from config.settings import Settings
s = Settings()
response = Generation.call(
    model='deepseek-v4-pro',
    messages=[{'role': 'user', 'content': '你好，请自我介绍'}],
    api_key=s.dashscope_api_key
)

print(f'Status Code: {response.status_code}')
if response.status_code == 200:
    print(f'Result: {response.output.choices[0].message.content}')
else:
    print(f'Error: {response.code} - {response.message}')
